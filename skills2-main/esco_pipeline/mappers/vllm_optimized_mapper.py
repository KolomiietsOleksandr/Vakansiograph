"""VLLMOptimizedMapper — per-skill mapping optimized for local vLLM inference.

Instead of batching many skills + many global candidates into huge prompts
(which causes truncation and stalls on small models), this mapper sends
**one skill + ~10 focused candidates** per LLM call.  vLLM's continuous
batching handles hundreds of tiny concurrent requests efficiently.
"""

import json
import logging

from rapidfuzz import fuzz, process

from esco_pipeline.config import Settings
from esco_pipeline.esco_interface import ESCOIndexInterface
from esco_pipeline.llm_client import LLMClient
from esco_pipeline.mappers.base import BaseMapper
from esco_pipeline.mappers.embedding_mapper import EmbeddingMapper
from esco_pipeline.mappers.fuzzy_mapper import FuzzyMapper
from esco_pipeline.models import ESCOMapping
from esco_pipeline.prompts import VLLM_OPT_SYSTEM_MESSAGE, VLLM_SKILL_MAPPING_PROMPT
from esco_pipeline.utils import DiskCache, hash_key, normalize_text

logger = logging.getLogger(__name__)


class VLLMOptimizedMapper(BaseMapper):
    """Maps each skill independently with a tiny, focused prompt."""

    def __init__(
        self,
        esco_index: ESCOIndexInterface,
        config: Settings,
        fuzzy_mapper: FuzzyMapper,
        embedding_mapper: EmbeddingMapper,
        llm_client: LLMClient | None = None,
    ):
        self._index = esco_index
        self._config = config
        self._fuzzy = fuzzy_mapper
        self._embedding = embedding_mapper
        self._llm = llm_client or LLMClient(config)
        self._cache = DiskCache(config.cache_dir)
        self._total_token_usage: dict = {}

    def name(self) -> str:
        return "vllm_optimized"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def map_skills(self, skill_strings: list[str]) -> dict[str, ESCOMapping | None]:
        results: dict[str, ESCOMapping | None] = {s: None for s in skill_strings}
        accumulated = {"input": 0, "output": 0, "total": 0}

        unique_skills = list(dict.fromkeys(skill_strings))
        top_k = self._config.vllm_candidates_per_skill // 2 or 5

        # ---- Step 1: batch embedding search (one call for all skills) ----
        non_empty = [s for s in unique_skills if s.strip()]
        logger.info("vllm_opt: embedding search for %d unique skills (top_k=%d)...", len(non_empty), top_k)
        embedding_results = self._index.batch_search_by_embedding(non_empty, top_k=top_k)

        # ---- Step 2: fuzzy top-k per skill + merge with embedding hits ----
        all_labels = self._index.get_all_labels()
        label_list = list(all_labels.keys())

        per_skill_candidates: dict[str, list[str]] = {}  # skill -> list of URIs

        for skill in unique_skills:
            uris: dict[str, None] = {}  # ordered set via dict keys

            # Fuzzy top-k
            normalized = normalize_text(skill)
            if normalized:
                fuzzy_hits = process.extract(
                    normalized, label_list, scorer=fuzz.token_sort_ratio, limit=top_k,
                )
                for matched_label, score, _ in fuzzy_hits:
                    if score >= self._config.fuzzy_threshold * 0.7:  # lower bar — LLM decides
                        uri = all_labels[matched_label]
                        uris[uri] = None

            # Embedding top-k
            for uri, score in embedding_results.get(skill, []):
                uris[uri] = None

            # Cap at configured limit
            per_skill_candidates[skill] = list(uris)[: self._config.vllm_candidates_per_skill]

        # ---- Step 3: check cache, build prompts for uncached skills ----
        cached_raw: dict[str, dict] = {}
        uncached: list[tuple[str, str, str]] = []  # (skill, prompt, cache_key)

        for skill in unique_skills:
            candidate_uris = per_skill_candidates.get(skill, [])
            if not candidate_uris:
                logger.debug("vllm_opt: no candidates for '%s', skipping LLM", skill)
                continue

            cache_key = hash_key("vllm_opt", skill, sorted(candidate_uris))
            cached = self._cache.get(cache_key)
            if cached is not None:
                cached_raw[skill] = cached
            else:
                candidates_text = self._format_skill_candidates(candidate_uris)
                prompt = VLLM_SKILL_MAPPING_PROMPT.format(
                    skill=skill,
                    candidates=candidates_text,
                )
                uncached.append((skill, prompt, cache_key))

        logger.info(
            "vllm_opt: %d/%d skills cached, %d to process concurrently",
            len(cached_raw), len(unique_skills), len(uncached),
        )

        # ---- Step 4: fire all uncached prompts concurrently ----
        #   max_tokens=512  — response is ~80-100 tokens; low cap = less KV cache per req
        #                     → vLLM can run MORE concurrent requests on GPU
        #   system_message   — identical across all requests → vLLM prefix-caches it
        if uncached:
            prompts = [item[1] for item in uncached]
            llm_results = self._llm.generate_json_batch(
                prompts,
                max_concurrent=self._config.llm_max_concurrent,
                max_tokens=512,
                system_message=VLLM_OPT_SYSTEM_MESSAGE,
            )
            for (skill, _prompt, cache_key), (raw, token_usage) in zip(uncached, llm_results):
                self._cache.set(cache_key, raw)
                cached_raw[skill] = raw
                for k in ("input", "output", "total"):
                    accumulated[k] += token_usage.get(k, 0)

        # ---- Step 5: parse results ----
        for skill in unique_skills:
            raw = cached_raw.get(skill)
            if raw is None:
                continue
            mapping = self._parse_single(skill, raw, per_skill_candidates.get(skill, []))
            if mapping is not None:
                results[skill] = mapping

        # Copy results to duplicate skill strings
        for skill in skill_strings:
            if results.get(skill) is None and skill in results:
                pass  # already None
            elif skill not in results:
                # Shouldn't happen, but be safe
                results[skill] = None

        self._total_token_usage = accumulated
        logger.info(
            "vllm_opt: done. Mapped %d/%d skills. Tokens: %s",
            sum(1 for v in results.values() if v is not None),
            len(skill_strings),
            accumulated,
        )
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_skill_candidates(self, uris: list[str]) -> str:
        """Format candidates for a single skill prompt."""
        lines = []
        for idx, uri in enumerate(uris, start=1):
            skill = self._index.get_skill(uri)
            if skill is None:
                continue
            alt = ", ".join(skill.alt_labels) if skill.alt_labels else ""
            line = f"- [{idx}] {skill.preferred_label}"
            if alt:
                line += f" | {alt}"
            lines.append(line)
        return "\n".join(lines) if lines else "(no candidates)"

    def _parse_single(
        self, skill: str, raw: dict, candidate_uris: list[str],
    ) -> ESCOMapping | None:
        """Parse a single-skill LLM response."""
        if not isinstance(raw, dict):
            return None

        esco_id = raw.get("esco_id")
        if esco_id is None:
            return None

        # Resolve candidate index to URI
        if isinstance(esco_id, int):
            idx = esco_id
        elif isinstance(esco_id, str) and esco_id.isdigit():
            idx = int(esco_id)
        else:
            logger.warning("vllm_opt: unexpected esco_id type for '%s': %r", skill, esco_id)
            return None

        if idx < 1 or idx > len(candidate_uris):
            logger.warning("vllm_opt: esco_id %d out of range for '%s' (have %d candidates)", idx, skill, len(candidate_uris))
            return None

        uri = candidate_uris[idx - 1]  # 1-indexed

        if not self._index.uri_exists(uri):
            logger.warning("vllm_opt: URI %s doesn't exist for skill '%s'", uri, skill)
            return None

        esco_label = raw.get("esco_label", "")
        confidence = float(raw.get("confidence", 0.0))
        reasoning = raw.get("reasoning", "")

        return ESCOMapping(
            raw_skill=skill,
            esco_uri=uri,
            esco_label=esco_label,
            confidence=confidence,
            method=self.name(),
            details={"reasoning": reasoning},
        )
