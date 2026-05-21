import json
import logging
from itertools import islice

from esco_pipeline.config import Settings
from esco_pipeline.enrichment import GraphEnrichment
from esco_pipeline.esco_interface import ESCOIndexInterface
from esco_pipeline.llm_client import LLMClient
from esco_pipeline.mappers.base import BaseMapper
from esco_pipeline.mappers.embedding_mapper import EmbeddingMapper
from esco_pipeline.mappers.fuzzy_mapper import FuzzyMapper
from esco_pipeline.models import ESCOMapping, Vacancy
from esco_pipeline.prompts import DIRECT_MAPPING_PROMPT, DIRECT_WITH_CONTEXT_PROMPT, MAPPING_PROMPT, RESCORE_WITH_CONTEXT_PROMPT
from esco_pipeline.utils import DiskCache, hash_key

logger = logging.getLogger(__name__)


def _batched(iterable, n):
    it = iter(iterable)
    while chunk := list(islice(it, n)):
        yield chunk


class LLMMapper(BaseMapper):
    def __init__(
        self,
        esco_index: ESCOIndexInterface,
        config: Settings,
        fuzzy_mapper: FuzzyMapper,
        embedding_mapper: EmbeddingMapper,
        mode: str = "direct",
        llm_client: LLMClient | None = None,
    ):
        self._index = esco_index
        self._config = config
        self._fuzzy = fuzzy_mapper
        self._embedding = embedding_mapper
        self._mode = mode
        self._enrichment = GraphEnrichment(esco_index, config.embedding_sibling_threshold)
        self._cache = DiskCache(config.cache_dir)
        self._llm = llm_client or LLMClient(config)
        self._last_token_usage: dict = {}
        self._total_token_usage: dict = {}
        self._last_candidates_text: str = ""
        self._last_id_to_uri: dict[int, str] = {}
        self._last_graph_uris: set[str] = set()

    def name(self) -> str:
        return f"llm_{self._mode}"

    def map_skills(self, skill_strings: list[str]) -> dict[str, ESCOMapping | None]:
        results: dict[str, ESCOMapping | None] = {}
        batch_size = self._config.llm_batch_size
        accumulated = {"input": 0, "output": 0, "total": 0}

        # Global prefetch: compute candidates once for all skills
        candidates, graph_uris = self._prefetch_candidates(skill_strings)
        candidates_text, id_to_uri = self._format_candidates(candidates)

        # Store for potential rescoring by pipeline
        self._last_candidates_text = candidates_text
        self._last_id_to_uri = id_to_uri
        self._last_graph_uris = graph_uris

        batches = list(_batched(skill_strings, batch_size))
        total_batches = len(batches)

        # --- Phase 1: check cache, build prompts for uncached batches ---
        cache_prefix = f"llm_{self._mode}"
        prompt_template = MAPPING_PROMPT if self._mode == "two_stage" else DIRECT_MAPPING_PROMPT

        cached_raw: dict[int, dict] = {}       # batch_idx -> raw LLM result
        uncached: list[tuple[int, list[str], str, str]] = []  # (idx, batch, prompt, cache_key)

        for batch_idx, batch in enumerate(batches):
            cache_key = hash_key(cache_prefix, sorted(batch), candidates_text)
            cached = self._cache.get(cache_key)
            if cached is not None:
                cached_raw[batch_idx] = cached
            else:
                if self._mode == "two_stage":
                    prompt = MAPPING_PROMPT.format(
                        skills=json.dumps(batch, ensure_ascii=False),
                        candidates=candidates_text,
                    )
                else:
                    prompt = DIRECT_MAPPING_PROMPT.format(
                        raw_skills=json.dumps(batch, ensure_ascii=False),
                        candidates=candidates_text,
                    )
                uncached.append((batch_idx, batch, prompt, cache_key))

        logger.info(
            "LLM mapping: %d/%d batches cached, %d to process concurrently",
            len(cached_raw), total_batches, len(uncached),
        )

        # --- Phase 2: fire uncached prompts concurrently ---
        if uncached:
            prompts = [item[2] for item in uncached]
            llm_results = self._llm.generate_json_batch(
                prompts, max_concurrent=self._config.llm_max_concurrent,
            )
            for (batch_idx, _batch, _prompt, cache_key), (raw, token_usage) in zip(uncached, llm_results):
                self._cache.set(cache_key, raw)
                cached_raw[batch_idx] = raw
                for k in ("input", "output", "total"):
                    accumulated[k] += token_usage.get(k, 0)

        # --- Phase 3: parse all results ---
        for batch_idx, batch in enumerate(batches):
            raw = cached_raw.get(batch_idx, {})
            batch_results = self._parse_mappings(batch, raw, graph_uris=graph_uris, id_to_uri=id_to_uri)
            results.update(batch_results)

        self._total_token_usage = accumulated
        return results

    def _process_batch(self, skills: list[str], candidates_text: str, graph_uris: set[str], id_to_uri: dict[int, str]) -> dict[str, ESCOMapping | None]:
        if self._mode == "direct":
            return self._map_direct(skills, candidates_text, graph_uris, id_to_uri)
        else:
            return self._map_two_stage(skills, candidates_text, graph_uris, id_to_uri)

    # Minimum guaranteed slots per retrieval category
    _MIN_SLOTS = {"fuzzy": 15, "embedding": 15, "graph_sibling": 5, "graph_parent": 3}

    def _prefetch_candidates(self, skill_strings: list[str]) -> tuple[list, set[str]]:
        uri_set: set[str] = set()
        skill_texts_by_uri: dict[str, list[str]] = {}
        uri_scores: dict[str, float] = {}
        uri_categories: dict[str, str] = {}

        def _track_uri(uri: str, skill_text: str, score: float, category: str) -> None:
            uri_set.add(uri)
            skill_texts_by_uri.setdefault(uri, []).append(skill_text)
            # Keep the highest score seen for this URI
            if uri not in uri_scores or score > uri_scores[uri]:
                uri_scores[uri] = score
            # Keep earliest category (fuzzy > embedding > graph)
            uri_categories.setdefault(uri, category)

        logger.info("Prefetch: fuzzy matching %d skills...", len(skill_strings))
        fuzzy_results = self._fuzzy.map_skills(skill_strings)
        for skill_text, mapping in fuzzy_results.items():
            if mapping:
                _track_uri(mapping.esco_uri, skill_text, mapping.confidence, "fuzzy")
        logger.info("Prefetch: fuzzy done, %d candidate URIs so far", len(uri_set))

        # Batch embedding search for top-3 per skill
        non_empty = [s for s in skill_strings if s.strip()]
        logger.info("Prefetch: embedding search for %d skills...", len(non_empty))
        embedding_results = self._index.batch_search_by_embedding(non_empty, top_k=3)
        for skill, hits in embedding_results.items():
            for uri, score in hits:
                if score >= self._config.embedding_threshold:
                    _track_uri(uri, skill, score, "embedding")
        logger.info("Prefetch: embedding done, %d candidate URIs total", len(uri_set))

        logger.info("Prefetch: graph enrichment...")
        enriched_uris, graph_uri_categories, enrichment_scores = self._enrichment.enrich(
            list(uri_set), skill_texts_by_uri, uri_scores=uri_scores,
        )
        # Merge enrichment scores and categories for graph-discovered URIs
        uri_scores.update(enrichment_scores)
        uri_categories.update(graph_uri_categories)
        graph_uris = set(graph_uri_categories.keys())

        # Boost near-exact fuzzy matches to prevent generic candidates from outranking them
        FUZZY_EXACT_BOOST = 0.15
        for uri in list(uri_scores):
            if uri_categories.get(uri) == "fuzzy" and uri_scores[uri] >= 0.95:
                uri_scores[uri] = min(uri_scores[uri] + FUZZY_EXACT_BOOST, 1.0)

        # Category-aware selection: guarantee minimum slots per category, fill rest by score
        selected = self._select_candidates(enriched_uris, uri_scores, uri_categories)
        logger.info(
            "Prefetch: done, %d candidates selected (limit %d)",
            len(selected), self._config.llm_max_candidates,
        )
        # Log per-category counts
        cat_counts: dict[str, int] = {}
        for uri in selected:
            cat = uri_categories.get(uri, "unknown")
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
        logger.info("Prefetch: category distribution: %s", cat_counts)

        return [self._index.get_skill(uri) for uri in selected if self._index.get_skill(uri)], graph_uris

    def _select_candidates(
        self,
        enriched_uris: list[str],
        uri_scores: dict[str, float],
        uri_categories: dict[str, str],
    ) -> list[str]:
        """Select candidates with guaranteed minimum slots per category, sorted by score."""
        max_candidates = self._config.llm_max_candidates
        enriched_uris = list(dict.fromkeys(enriched_uris))  # deduplicate preserving order

        # Group URIs by category
        by_category: dict[str, list[str]] = {}
        for uri in enriched_uris:
            cat = uri_categories.get(uri, "fuzzy")
            by_category.setdefault(cat, []).append(uri)

        # Sort each category by score descending
        for cat in by_category:
            by_category[cat].sort(key=lambda u: uri_scores.get(u, 0.0), reverse=True)

        # Phase 1: take guaranteed minimum slots per category
        selected_set: set[str] = set()
        selected: list[str] = []
        for cat, min_count in self._MIN_SLOTS.items():
            for uri in by_category.get(cat, [])[:min_count]:
                if uri not in selected_set:
                    selected_set.add(uri)
                    selected.append(uri)

        # Phase 2: fill remaining slots from score-sorted pool
        remaining = max_candidates - len(selected)
        if remaining > 0:
            all_by_score = sorted(enriched_uris, key=lambda u: uri_scores.get(u, 0.0), reverse=True)
            for uri in all_by_score:
                if uri not in selected_set:
                    selected.append(uri)
                    selected_set.add(uri)
                    remaining -= 1
                    if remaining <= 0:
                        break

        # Final sort by score descending so LLM sees best candidates first
        selected.sort(key=lambda u: uri_scores.get(u, 0.0), reverse=True)
        return selected

    def _format_candidates(self, candidates) -> tuple[str, dict[int, str]]:
        lines = []
        id_to_uri: dict[int, str] = {}
        for idx, skill in enumerate(candidates, start=1):
            id_to_uri[idx] = skill.uri
            alt = ", ".join(skill.alt_labels) if skill.alt_labels else ""
            line = f"- [{idx}] Label: {skill.preferred_label}"
            if alt:
                line += f" | Alt: {alt}"
            lines.append(line)
        text = "\n".join(lines) if lines else "(no candidates found)"
        return text, id_to_uri

    def _map_direct(self, skills: list[str], candidates_text: str, graph_uris: set[str] | None = None, id_to_uri: dict[int, str] | None = None) -> dict[str, ESCOMapping | None]:
        self._last_token_usage = {}
        cache_key = hash_key("llm_direct", sorted(skills), candidates_text)
        cached = self._cache.get(cache_key)

        if cached is None:
            prompt = DIRECT_MAPPING_PROMPT.format(
                raw_skills=json.dumps(skills, ensure_ascii=False),
                candidates=candidates_text,
            )
            raw = self._call_llm(prompt)
            self._cache.set(cache_key, raw)
        else:
            raw = cached

        return self._parse_mappings(skills, raw, graph_uris=graph_uris, id_to_uri=id_to_uri)

    def _map_two_stage(self, skills: list[str], candidates_text: str, graph_uris: set[str] | None = None, id_to_uri: dict[int, str] | None = None) -> dict[str, ESCOMapping | None]:
        self._last_token_usage = {}
        cache_key = hash_key("llm_two_stage", sorted(skills), candidates_text)
        cached = self._cache.get(cache_key)

        if cached is None:
            map_prompt = MAPPING_PROMPT.format(
                skills=json.dumps(skills, ensure_ascii=False),
                candidates=candidates_text,
            )
            raw = self._call_llm(map_prompt)
            self._cache.set(cache_key, raw)
        else:
            raw = cached

        return self._parse_mappings(skills, raw, graph_uris=graph_uris, id_to_uri=id_to_uri)

    def _call_llm(self, prompt: str):
        parsed, token_usage = self._llm.generate_json(prompt)
        self._last_token_usage = token_usage
        return parsed

    def _parse_mappings(self, skills: list[str], raw, allow_extra: bool = False, graph_uris: set[str] | None = None, id_to_uri: dict[int, str] | None = None) -> dict[str, ESCOMapping | None]:
        results: dict[str, ESCOMapping | None] = {s: None for s in skills}

        if not isinstance(raw, dict):
            return results

        for item in raw.get("mappings", []):
            if not isinstance(item, dict):
                continue
            raw_skill = item.get("raw_skill", "")
            label = item.get("esco_label", "")
            confidence = float(item.get("confidence") or 0.0)
            reasoning = item.get("reasoning", "")

            # Resolve compressed candidate ID to full URI
            uri = item.get("esco_id", item.get("esco_uri", ""))
            if isinstance(uri, list):
                uri = uri[0] if uri else ""
            if id_to_uri is not None and isinstance(uri, int):
                uri = id_to_uri.get(uri, "")
            elif id_to_uri is not None and isinstance(uri, str) and uri.isdigit():
                uri = id_to_uri.get(int(uri), "")

            if not self._index.uri_exists(uri):
                logger.warning("LLMMapper: hallucinated URI %s for skill '%s'", uri, raw_skill)
                continue

            # Match back to original skill string (exact or closest)
            target_skill = self._find_original_skill(raw_skill, skills)
            if target_skill is None:
                if not allow_extra:
                    continue
                target_skill = raw_skill
            results[target_skill] = ESCOMapping(
                raw_skill=target_skill,
                esco_uri=uri,
                esco_label=label,
                confidence=confidence,
                method=self.name(),
                details={"reasoning": reasoning},
                via_graph=(uri in graph_uris) if graph_uris else False,
            )

        return results

    def map_vacancy_direct(self, vacancy: Vacancy) -> dict[str, ESCOMapping | None]:
        if not vacancy.raw_skills:
            return {}
        candidates, graph_uris = self._prefetch_candidates(vacancy.raw_skills)
        candidates_text, id_to_uri = self._format_candidates(candidates)
        return self._map_direct_with_context(
            vacancy.raw_skills,
            vacancy.title or "",
            vacancy.description_text or "",
            candidates_text,
            graph_uris=graph_uris,
            id_to_uri=id_to_uri,
        )

    def _map_direct_with_context(
        self,
        skills: list[str],
        title: str,
        description: str,
        candidates_text: str,
        graph_uris: set[str] | None = None,
        id_to_uri: dict[int, str] | None = None,
    ) -> dict[str, ESCOMapping | None]:
        self._last_token_usage = {}
        cache_key = hash_key("llm_direct_ctx", sorted(skills), title, description, candidates_text)
        cached = self._cache.get(cache_key)

        if cached is None:
            prompt = DIRECT_WITH_CONTEXT_PROMPT.format(
                raw_skills=json.dumps(skills, ensure_ascii=False),
                title=title,
                description=description,
                candidates=candidates_text,
            )
            raw = self._call_llm(prompt)
            self._cache.set(cache_key, raw)
        else:
            raw = cached

        return self._parse_mappings(skills, raw, allow_extra=True, graph_uris=graph_uris, id_to_uri=id_to_uri)

    def rescore_with_context(
        self,
        skills: list[str],
        title: str,
        description: str,
        candidates_text: str,
        graph_uris: set[str] | None = None,
        id_to_uri: dict[int, str] | None = None,
    ) -> dict[str, ESCOMapping | None]:
        """Re-score skills with vacancy context for disambiguation."""
        self._last_token_usage = {}
        desc_truncated = description[:1000] if description else ""
        cache_key = hash_key("llm_rescore_ctx", sorted(skills), title, desc_truncated, candidates_text)
        cached = self._cache.get(cache_key)

        if cached is None:
            prompt = RESCORE_WITH_CONTEXT_PROMPT.format(
                skills=json.dumps(skills, ensure_ascii=False),
                title=title,
                description=desc_truncated,
                candidates=candidates_text,
            )
            raw = self._call_llm(prompt)
            self._cache.set(cache_key, raw)
        else:
            raw = cached

        return self._parse_mappings(skills, raw, graph_uris=graph_uris, id_to_uri=id_to_uri)

    def _find_original_skill(self, raw_skill: str, skills: list[str]) -> str | None:
        if raw_skill in skills:
            return raw_skill
        # Case-insensitive fallback
        lower = raw_skill.lower()
        for s in skills:
            if s.lower() == lower:
                return s
        return None
