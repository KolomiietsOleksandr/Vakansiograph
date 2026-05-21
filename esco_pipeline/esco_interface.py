import csv
import json
import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from google import genai
from google.genai.errors import ClientError
from google.genai import types
from rapidfuzz import process, fuzz
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed, before_sleep_log

from esco_pipeline.utils import DiskCache, hash_key

logger = logging.getLogger(__name__)


@dataclass
class ESCOSkill:
    uri: str
    preferred_label: str
    alt_labels: list[str] = field(default_factory=list)
    description: str = ""
    skill_type: str = ""


class ESCOIndexInterface(ABC):
    @abstractmethod
    def get_skill(self, uri: str) -> ESCOSkill | None: ...

    @abstractmethod
    def get_all_labels(self) -> dict[str, str]: ...

    @abstractmethod
    def uri_exists(self, uri: str) -> bool: ...

    @abstractmethod
    def search_by_embedding(self, text: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Returns list of (uri, similarity_score) tuples."""
        ...

    def compute_embedding_similarity(self, text: str, uri: str) -> float:
        """Compute embedding similarity between text and a skill URI. Default: 0."""
        return 0.0

    def batch_search_by_embedding(self, texts: list[str], top_k: int = 5) -> dict[str, list[tuple[str, float]]]:
        """Batch version of search_by_embedding. Default: calls search_by_embedding per text."""
        return {text: self.search_by_embedding(text, top_k) for text in texts}

    @abstractmethod
    def get_parent(self, uri: str) -> ESCOSkill | None: ...

    @abstractmethod
    def get_children(self, uri: str) -> list[ESCOSkill]: ...

    @abstractmethod
    def get_siblings(self, uri: str) -> list[ESCOSkill]: ...


class MockESCOIndex(ESCOIndexInterface):
    """Loads ESCO skills from a JSON file for testing and development."""

    def __init__(self, json_path: str | Path):
        self._skills: dict[str, ESCOSkill] = {}
        self._labels: dict[str, str] = {}  # label_lowercase -> uri
        self._load(Path(json_path))

    def _load(self, path: Path) -> None:
        with open(path) as f:
            data = json.load(f)
        for item in data:
            skill = ESCOSkill(
                uri=item["uri"],
                preferred_label=item["preferred_label"],
                alt_labels=item.get("alt_labels", []),
                description=item.get("description", ""),
                skill_type=item.get("skill_type", ""),
            )
            self._skills[skill.uri] = skill

        # Build label index
        for skill in self._skills.values():
            self._labels[skill.preferred_label.lower()] = skill.uri
            for label in skill.alt_labels:
                if label:
                    self._labels[label.lower()] = skill.uri

    def get_skill(self, uri: str) -> ESCOSkill | None:
        return self._skills.get(uri)

    def get_all_labels(self) -> dict[str, str]:
        return dict(self._labels)

    def uri_exists(self, uri: str) -> bool:
        return uri in self._skills

    def search_by_embedding(self, text: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Falls back to fuzzy string matching since mock has no embeddings."""
        labels = list(self._labels.keys())
        if not labels:
            return []
        results = process.extract(
            text.lower(), labels, scorer=fuzz.token_sort_ratio, limit=top_k
        )
        output = []
        for label, score, _ in results:
            uri = self._labels[label]
            output.append((uri, score / 100.0))
        return output

    def get_parent(self, uri: str) -> ESCOSkill | None:
        return None

    def get_children(self, uri: str) -> list[ESCOSkill]:
        return []

    def get_siblings(self, uri: str) -> list[ESCOSkill]:
        return []


class ESCOIndex(ESCOIndexInterface):
    """Loads ESCO skills from official CSV dataset files."""

    BATCH_SIZE = 100

    def __init__(self, data_dir: str | Path, language: str = "en", gemini_api_key: str = "", cache_dir: str = ".cache", embedding_title_weight: float = 0.6):
        self._data_dir = Path(data_dir)
        self._lang = language
        self._csv_dir = self._data_dir / f"ESCO dataset - v1.2.1 - classification - {language} - csv"

        self._skills: dict[str, ESCOSkill] = {}
        self._labels: dict[str, str] = {}
        self._parent_map: dict[str, str] = {}
        self._children_map: dict[str, list[str]] = defaultdict(list)

        self._embedding_matrix: np.ndarray | None = None
        self._desc_embedding_matrix: np.ndarray | None = None
        self._embedding_uris: list[str] = []
        self._uri_to_emb_idx: dict[str, int] = {}
        self._genai_client: genai.Client | None = None
        self._query_emb_cache = DiskCache(cache_dir)
        self._embedding_title_weight: float = embedding_title_weight

        self._load_skills()
        self._load_skill_groups()
        self._load_hierarchy()
        self._init_embeddings(gemini_api_key)

    def _load_skills(self) -> None:
        path = self._csv_dir / f"skills_{self._lang}.csv"
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uri = row["conceptUri"]
                alt_labels_raw = row.get("altLabels", "")
                alt_labels = [l.strip() for l in alt_labels_raw.split("\n") if l.strip()]

                skill = ESCOSkill(
                    uri=uri,
                    preferred_label=row["preferredLabel"],
                    alt_labels=alt_labels,
                    description=row.get("description", ""),
                    skill_type=row.get("skillType", ""),
                )
                self._skills[uri] = skill
                self._labels[skill.preferred_label.lower()] = uri
                for label in alt_labels:
                    self._labels[label.lower()] = uri

        logger.info("Loaded %d skills from %s", len(self._skills), path.name)

    def _load_skill_groups(self) -> None:
        path = self._csv_dir / f"skillGroups_{self._lang}.csv"
        count = 0
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uri = row["conceptUri"]
                if uri in self._skills:
                    continue
                self._skills[uri] = ESCOSkill(
                    uri=uri,
                    preferred_label=row["preferredLabel"],
                    description=row.get("description", ""),
                    skill_type="group",
                )
                count += 1
        logger.info("Loaded %d skill groups from %s", count, path.name)

    def _load_hierarchy(self) -> None:
        path = self._csv_dir / f"broaderRelationsSkillPillar_{self._lang}.csv"
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                child_uri = row["conceptUri"]
                parent_uri = row["broaderUri"]
                self._parent_map[child_uri] = parent_uri
                self._children_map[parent_uri].append(child_uri)

        logger.info(
            "Loaded %d hierarchy relations from %s",
            len(self._parent_map),
            path.name,
        )

    def _init_embeddings(self, gemini_api_key: str) -> None:
        if not gemini_api_key:
            logger.info("No Gemini API key provided; embedding search will fall back to fuzzy matching")
            return

        self._genai_client = genai.Client(api_key=gemini_api_key)
        cache_path = self._data_dir / f".embeddings_cache_{self._lang}.npz"
        desc_cache_path = self._data_dir / f".embeddings_cache_{self._lang}_desc.npz"

        if cache_path.exists():
            data = np.load(cache_path, allow_pickle=True)
            self._embedding_matrix = data["matrix"]
            self._embedding_uris = data["uris"].tolist()
            self._uri_to_emb_idx = {uri: i for i, uri in enumerate(self._embedding_uris)}
            logger.info("Loaded cached label embeddings: %d vectors", len(self._embedding_uris))
        else:
            self._compute_and_cache_embeddings(cache_path)

        if desc_cache_path.exists():
            data = np.load(desc_cache_path, allow_pickle=True)
            self._desc_embedding_matrix = data["matrix"]
            logger.info("Loaded cached description embeddings: %d vectors", self._desc_embedding_matrix.shape[0])
        else:
            self._compute_and_cache_desc_embeddings(desc_cache_path)

    MAX_RPM = 3000

    def _compute_and_cache_embeddings(self, cache_path: Path) -> None:
        skill_items = [
            (uri, skill.preferred_label)
            for uri, skill in self._skills.items()
            if skill.skill_type != "group"
        ]
        uris = [uri for uri, _ in skill_items]
        labels = [label for _, label in skill_items]
        total = len(labels)

        logger.info("Computing embeddings for %d skills (this may take a while)...", total)

        all_embeddings: list[list[float]] = []
        request_times: deque[float] = deque()

        for i in range(0, total, self.BATCH_SIZE):
            # Sliding window rate limit: only sleep when approaching the limit
            if len(request_times) >= self.MAX_RPM:
                oldest = request_times.popleft()
                wait = 60.0 - (time.monotonic() - oldest)
                if wait > 0:
                    logger.info("Rate limit: waiting %.1fs", wait)
                    time.sleep(wait)

            batch = labels[i : i + self.BATCH_SIZE]
            response = self._embed_batch(batch)
            request_times.append(time.monotonic())

            for emb in response.embeddings:
                all_embeddings.append(emb.values)

            done = min(i + self.BATCH_SIZE, total)
            if (i // self.BATCH_SIZE) % 50 == 0:
                logger.info("  embedded %d / %d", done, total)

        self._embedding_matrix = np.array(all_embeddings, dtype=np.float32)
        self._embedding_uris = uris
        self._uri_to_emb_idx = {uri: i for i, uri in enumerate(uris)}

        # Normalize for cosine similarity
        norms = np.linalg.norm(self._embedding_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._embedding_matrix /= norms

        np.savez(cache_path, matrix=self._embedding_matrix, uris=np.array(uris))
        logger.info("Cached embeddings to %s", cache_path)

    def _compute_and_cache_desc_embeddings(self, cache_path: Path) -> None:
        skill_items = [
            (uri, skill.description or skill.preferred_label)
            for uri, skill in self._skills.items()
            if skill.skill_type != "group"
        ]
        # Use same URI order as label embeddings
        uri_order = self._embedding_uris
        desc_by_uri = {uri: desc for uri, desc in skill_items}
        descriptions = [desc_by_uri.get(uri, "") for uri in uri_order]
        total = len(descriptions)

        logger.info("Computing description embeddings for %d skills...", total)

        all_embeddings: list[list[float]] = []
        request_times: deque[float] = deque()

        for i in range(0, total, self.BATCH_SIZE):
            if len(request_times) >= self.MAX_RPM:
                oldest = request_times.popleft()
                wait = 60.0 - (time.monotonic() - oldest)
                if wait > 0:
                    logger.info("Rate limit: waiting %.1fs", wait)
                    time.sleep(wait)

            batch = descriptions[i : i + self.BATCH_SIZE]
            response = self._embed_batch(batch)
            request_times.append(time.monotonic())

            for emb in response.embeddings:
                all_embeddings.append(emb.values)

            done = min(i + self.BATCH_SIZE, total)
            if (i // self.BATCH_SIZE) % 50 == 0:
                logger.info("  embedded %d / %d descriptions", done, total)

        self._desc_embedding_matrix = np.array(all_embeddings, dtype=np.float32)

        norms = np.linalg.norm(self._desc_embedding_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._desc_embedding_matrix /= norms

        np.savez(cache_path, matrix=self._desc_embedding_matrix)
        logger.info("Cached description embeddings to %s", cache_path)

    @retry(
        retry=retry_if_exception(lambda e: isinstance(e, ClientError) and e.code == 429),
        wait=wait_fixed(30),
        stop=stop_after_attempt(5),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _embed_batch(self, texts: list[str]):
        return self._genai_client.models.embed_content(
            model="gemini-embedding-001",
            contents=texts,
        )

    # --- Interface methods ---

    def get_skill(self, uri: str) -> ESCOSkill | None:
        return self._skills.get(uri)

    def get_all_labels(self) -> dict[str, str]:
        return dict(self._labels)

    def uri_exists(self, uri: str) -> bool:
        return uri in self._skills

    def search_by_embedding(self, text: str, top_k: int = 5) -> list[tuple[str, float]]:
        if self._embedding_matrix is None or self._genai_client is None:
            return self._fuzzy_fallback(text, top_k)

        query_vec = self._get_query_embedding(text)

        title_sim = self._embedding_matrix @ query_vec

        if self._desc_embedding_matrix is not None:
            desc_sim = self._desc_embedding_matrix @ query_vec
            w = self._embedding_title_weight
            similarities = w * title_sim + (1 - w) * desc_sim
        else:
            similarities = title_sim

        top_indices = np.argsort(similarities)[::-1][:top_k]

        return [
            (self._embedding_uris[i], float(similarities[i]))
            for i in top_indices
        ]

    def compute_embedding_similarity(self, text: str, uri: str) -> float:
        """Compute combined embedding similarity between text and a skill URI."""
        if self._embedding_matrix is None or self._genai_client is None:
            return 0.0

        idx = self._uri_to_emb_idx.get(uri)
        if idx is None:
            return 0.0
        query_vec = self._get_query_embedding(text)

        title_sim = float(self._embedding_matrix[idx] @ query_vec)

        if self._desc_embedding_matrix is not None:
            desc_sim = float(self._desc_embedding_matrix[idx] @ query_vec)
            w = self._embedding_title_weight
            return w * title_sim + (1 - w) * desc_sim

        return title_sim

    def _get_query_embedding(self, text: str) -> np.ndarray:
        cache_key = hash_key("query_embedding", text)
        cached = self._query_emb_cache.get(cache_key)
        if cached is not None:
            return np.array(cached, dtype=np.float32)

        response = self._genai_client.models.embed_content(
            model="gemini-embedding-001",
            contents=text,
        )
        query_vec = np.array(response.embeddings[0].values, dtype=np.float32)
        query_vec /= np.linalg.norm(query_vec) or 1.0
        self._query_emb_cache.set(cache_key, query_vec.tolist())
        return query_vec

    def batch_get_query_embeddings(self, texts: list[str]) -> dict[str, np.ndarray]:
        """Get query embeddings for multiple texts, batching uncached API calls."""
        result: dict[str, np.ndarray] = {}
        uncached: list[str] = []

        for text in texts:
            cache_key = hash_key("query_embedding", text)
            cached = self._query_emb_cache.get(cache_key)
            if cached is not None:
                result[text] = np.array(cached, dtype=np.float32)
            else:
                uncached.append(text)

        if uncached and self._genai_client is not None:
            logger.info("Batch-embedding %d uncached query texts (%d cached)", len(uncached), len(result))
            for i in range(0, len(uncached), self.BATCH_SIZE):
                batch = uncached[i : i + self.BATCH_SIZE]
                response = self._embed_batch(batch)
                for text_item, emb in zip(batch, response.embeddings):
                    vec = np.array(emb.values, dtype=np.float32)
                    norm = np.linalg.norm(vec)
                    if norm > 0:
                        vec /= norm
                    result[text_item] = vec
                    cache_key = hash_key("query_embedding", text_item)
                    self._query_emb_cache.set(cache_key, vec.tolist())

        return result

    def batch_search_by_embedding(self, texts: list[str], top_k: int = 5) -> dict[str, list[tuple[str, float]]]:
        """Search by embedding for multiple texts at once using matrix multiply."""
        if self._embedding_matrix is None or self._genai_client is None:
            return {text: self._fuzzy_fallback(text, top_k) for text in texts}

        embeddings = self.batch_get_query_embeddings(texts)
        # Build query matrix from texts that got embeddings
        ordered_texts = [t for t in texts if t in embeddings]
        if not ordered_texts:
            return {text: [] for text in texts}

        query_matrix = np.stack([embeddings[t] for t in ordered_texts])  # (N, D)

        title_sim = query_matrix @ self._embedding_matrix.T  # (N, M)

        if self._desc_embedding_matrix is not None:
            desc_sim = query_matrix @ self._desc_embedding_matrix.T
            w = self._embedding_title_weight
            similarities = w * title_sim + (1 - w) * desc_sim
        else:
            similarities = title_sim

        results: dict[str, list[tuple[str, float]]] = {}
        for i, text in enumerate(ordered_texts):
            top_indices = np.argsort(similarities[i])[::-1][:top_k]
            results[text] = [
                (self._embedding_uris[j], float(similarities[i, j]))
                for j in top_indices
            ]

        # Fill in any texts that didn't get embeddings
        for text in texts:
            if text not in results:
                results[text] = []

        return results

    def _fuzzy_fallback(self, text: str, top_k: int) -> list[tuple[str, float]]:
        labels = list(self._labels.keys())
        if not labels:
            return []
        results = process.extract(
            text.lower(), labels, scorer=fuzz.token_sort_ratio, limit=top_k
        )
        return [(self._labels[label], score / 100.0) for label, score, _ in results]

    def get_parent(self, uri: str) -> ESCOSkill | None:
        parent_uri = self._parent_map.get(uri)
        if parent_uri is None:
            return None
        return self._skills.get(parent_uri)

    def get_children(self, uri: str) -> list[ESCOSkill]:
        child_uris = self._children_map.get(uri, [])
        return [self._skills[u] for u in child_uris if u in self._skills]

    def get_siblings(self, uri: str) -> list[ESCOSkill]:
        parent_uri = self._parent_map.get(uri)
        if parent_uri is None:
            return []
        return [
            self._skills[u]
            for u in self._children_map.get(parent_uri, [])
            if u != uri and u in self._skills
        ]
