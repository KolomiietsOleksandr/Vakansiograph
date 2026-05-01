import json
import logging
import time

from esco_pipeline.config import Settings
from esco_pipeline.esco_interface import ESCOIndexInterface
from esco_pipeline.mappers.base import BaseMapper
from esco_pipeline.models import Document, DocumentResult, ESCOMapping, Resume, SkillSource, Vacancy
from esco_pipeline.prompts import CV_EXTRACTION_PROMPT, EXTRACTION_PROMPT, RESCORE_WITH_CONTEXT_PROMPT
from esco_pipeline.utils import DiskCache, hash_key

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, mapper: BaseMapper, esco_index: ESCOIndexInterface, config: Settings):
        self._mapper = mapper
        self._index = esco_index
        self._config = config

    def run(self, vacancies: list[Document]) -> list[DocumentResult]:
        start_time = time.time()

        if self._mapper.name() == "llm_direct":
            return self._run_direct_with_context(vacancies, start_time)

        # For LLM two-stage and embedding modes, populate extracted_skills first
        extraction_tokens: dict[str, dict] = {}
        if self._mapper.name() == "llm_two_stage" or (
            self._mapper.name() == "embedding" and bool(self._config.gemini_api_key)
        ):
            extraction_tokens = self._run_llm_extraction(vacancies)

        # Collect all unique skill strings across documents
        unique_skills: set[str] = set()
        for vacancy in vacancies:
            for skill in vacancy.raw_skills:
                if skill and skill.strip():
                    unique_skills.add(skill)
            for skill_source in vacancy.extracted_skills:
                if skill_source.text and skill_source.text.strip():
                    unique_skills.add(skill_source.text)
            if self._mapper.name() == "embedding" and vacancy.title and vacancy.title.strip():
                unique_skills.add(vacancy.title.strip())

        unique_skills_list = list(unique_skills)
        logger.info(
            "Mapping %d unique skills via %s mapper", len(unique_skills_list), self._mapper.name()
        )

        # Run mapper on all unique skills at once (already concurrent internally)
        mapping_start = time.time()
        skill_to_mapping: dict[str, ESCOMapping | None] = {}
        if unique_skills_list:
            skill_to_mapping = self._mapper.map_skills(unique_skills_list)
        mapping_elapsed = time.time() - mapping_start

        mapping_tokens = {}
        if hasattr(self._mapper, "_total_token_usage"):
            mapping_tokens = dict(self._mapper._total_token_usage)

        # Pass 2: per-vacancy rescore for low-confidence/unmapped skills (two_stage only)
        is_two_stage = self._mapper.name() == "llm_two_stage"
        rescore_threshold = self._config.llm_rescore_threshold

        # First pass: build per-vacancy skill lists and identify what needs rescoring
        vacancy_data: list[dict] = []
        for vacancy in vacancies:
            doc_skills = list(vacancy.raw_skills)
            for ss in vacancy.extracted_skills:
                if ss.text not in doc_skills:
                    doc_skills.append(ss.text)
            if self._mapper.name() == "embedding" and vacancy.title and vacancy.title.strip():
                title = vacancy.title.strip()
                if title not in doc_skills:
                    doc_skills.append(title)

            all_mappings = []
            unmapped = []
            for skill in doc_skills:
                if not skill or not skill.strip():
                    continue
                mapping = skill_to_mapping.get(skill)
                if mapping is not None:
                    all_mappings.append(mapping)
                else:
                    unmapped.append(skill)

            vacancy_data.append({
                "vacancy": vacancy,
                "doc_skills": doc_skills,
                "all_mappings": all_mappings,
                "unmapped": unmapped,
            })

        # Concurrent rescoring for two_stage
        if is_two_stage and hasattr(self._mapper, "rescore_with_context"):
            self._run_concurrent_rescore(vacancy_data, rescore_threshold)

        # Build final results
        results = []
        for vd in vacancy_data:
            vacancy = vd["vacancy"]
            doc_skills = vd["doc_skills"]
            all_mappings = vd["all_mappings"]
            unmapped = vd["unmapped"]

            direct_mappings = [m for m in all_mappings if not m.via_graph]
            graph_mappings = [m for m in all_mappings if m.via_graph]

            results.append(DocumentResult(
                document_id=vacancy.id,
                direct_mappings=direct_mappings,
                graph_mappings=graph_mappings,
                unmapped_skills=unmapped,
                metadata={
                    "title": vacancy.title,
                    "mapper": self._mapper.name(),
                    "total_skills": len(doc_skills),
                    "mapped_count": len(direct_mappings) + len(graph_mappings),
                    "unmapped_count": len(unmapped),
                    "mapping_elapsed_s": round(mapping_elapsed, 3),
                    "total_elapsed_s": round(time.time() - start_time, 3),
                    "token_usage": {
                        "extraction": extraction_tokens.get(vacancy.id, {}),
                        "mapping": mapping_tokens,
                    },
                },
            ))

        logger.info(
            "Pipeline complete: %d documents, %.2fs total",
            len(results),
            time.time() - start_time,
        )
        return results

    # ------------------------------------------------------------------
    # Concurrent rescoring
    # ------------------------------------------------------------------

    def _run_concurrent_rescore(self, vacancy_data: list[dict], rescore_threshold: float) -> None:
        """Fire rescore LLM calls for all vacancies concurrently."""
        candidates_text = getattr(self._mapper, "_last_candidates_text", "")
        id_to_uri = getattr(self._mapper, "_last_id_to_uri", {})
        graph_uris = getattr(self._mapper, "_last_graph_uris", set())
        llm_client = getattr(self._mapper, "_llm", None)
        cache = DiskCache(self._config.cache_dir)

        if not candidates_text or llm_client is None:
            return

        # Identify vacancies that need rescoring and build prompts
        rescore_items: list[tuple[int, list[str], str]] = []  # (vd_idx, skills_to_rescore, cache_key)
        uncached_prompts: list[tuple[int, str, str]] = []  # (item_idx, prompt, cache_key)
        cached_results: dict[int, dict] = {}  # item_idx -> raw

        for vd_idx, vd in enumerate(vacancy_data):
            vacancy = vd["vacancy"]
            all_mappings = vd["all_mappings"]
            unmapped = vd["unmapped"]

            ambiguous = [m.raw_skill for m in all_mappings if m.confidence < rescore_threshold]
            skills_to_rescore = ambiguous + unmapped
            if not skills_to_rescore or not (vacancy.title or vacancy.description_text):
                continue

            desc_truncated = (vacancy.description_text or "")[:1000]
            ck = hash_key("llm_rescore_ctx", sorted(skills_to_rescore), vacancy.title or "", desc_truncated, candidates_text)

            item_idx = len(rescore_items)
            rescore_items.append((vd_idx, skills_to_rescore, ck))

            cached = cache.get(ck)
            if cached is not None:
                cached_results[item_idx] = cached
            else:
                prompt = RESCORE_WITH_CONTEXT_PROMPT.format(
                    skills=json.dumps(skills_to_rescore, ensure_ascii=False),
                    title=vacancy.title or "",
                    description=desc_truncated,
                    candidates=candidates_text,
                )
                uncached_prompts.append((item_idx, prompt, ck))

        if not rescore_items:
            return

        logger.info(
            "Rescore: %d vacancies need rescoring (%d cached, %d to call concurrently)",
            len(rescore_items), len(cached_results), len(uncached_prompts),
        )

        # Fire uncached rescore prompts concurrently
        if uncached_prompts:
            prompts = [p[1] for p in uncached_prompts]
            llm_results = llm_client.generate_json_batch(
                prompts, max_concurrent=self._config.llm_max_concurrent,
            )
            for (item_idx, _prompt, ck), (raw, _token_usage) in zip(uncached_prompts, llm_results):
                cache.set(ck, raw)
                cached_results[item_idx] = raw

        # Apply rescore results
        for item_idx, (vd_idx, skills_to_rescore, _ck) in enumerate(rescore_items):
            raw = cached_results.get(item_idx, {})
            if not raw:
                continue
            try:
                rescored = self._mapper._parse_mappings(
                    skills_to_rescore, raw, graph_uris=graph_uris, id_to_uri=id_to_uri
                )
            except Exception as e:
                logger.warning("Rescore parse failed for vacancy %s: %s", vacancy_data[vd_idx]["vacancy"].id, e)
                continue

            vd = vacancy_data[vd_idx]
            all_mappings = vd["all_mappings"]
            unmapped = vd["unmapped"]

            # Replace low-confidence mappings with rescored ones
            for i, m in enumerate(all_mappings):
                if m.raw_skill in rescored and rescored[m.raw_skill] is not None:
                    if rescored[m.raw_skill].confidence > m.confidence:
                        all_mappings[i] = rescored[m.raw_skill]
            # Try to resolve unmapped skills
            new_unmapped = []
            for skill in unmapped:
                if skill in rescored and rescored[skill] is not None:
                    all_mappings.append(rescored[skill])
                else:
                    new_unmapped.append(skill)
            vd["unmapped"] = new_unmapped

    # ------------------------------------------------------------------
    # Direct with context (per-vacancy)
    # ------------------------------------------------------------------

    def _run_direct_with_context(
        self, vacancies: list[Document], start_time: float
    ) -> list[DocumentResult]:
        results = []
        for vacancy in vacancies:
            mapping_start = time.time()
            skill_to_mapping: dict[str, ESCOMapping | None] = {}
            try:
                skill_to_mapping = self._mapper.map_vacancy_direct(vacancy)  # type: ignore[attr-defined]
            except Exception as e:
                logger.warning("llm_direct context mapping failed for %s: %s", vacancy.id, e)
            mapping_tokens = dict(self._mapper._last_token_usage)  # type: ignore[attr-defined]

            mapping_elapsed = time.time() - mapping_start

            doc_skills = list(vacancy.raw_skills)
            all_mappings = []
            unmapped = []
            for skill in doc_skills:
                if not skill or not skill.strip():
                    continue
                mapping = skill_to_mapping.get(skill)
                if mapping is not None:
                    all_mappings.append(mapping)
                else:
                    unmapped.append(skill)

            direct_mappings = [m for m in all_mappings if not m.via_graph]
            graph_mappings = [m for m in all_mappings if m.via_graph]

            results.append(DocumentResult(
                document_id=vacancy.id,
                direct_mappings=direct_mappings,
                graph_mappings=graph_mappings,
                unmapped_skills=unmapped,
                metadata={
                    "title": vacancy.title,
                    "mapper": self._mapper.name(),
                    "total_skills": len(doc_skills),
                    "mapped_count": len(direct_mappings) + len(graph_mappings),
                    "unmapped_count": len(unmapped),
                    "mapping_elapsed_s": round(mapping_elapsed, 3),
                    "total_elapsed_s": round(time.time() - start_time, 3),
                    "token_usage": {
                        "extraction": {},
                        "mapping": mapping_tokens,
                    },
                },
            ))

        logger.info(
            "Pipeline complete: %d documents, %.2fs total",
            len(results),
            time.time() - start_time,
        )
        return results

    # ------------------------------------------------------------------
    # Concurrent LLM extraction
    # ------------------------------------------------------------------

    def _run_llm_extraction(self, vacancies: list[Document]) -> dict[str, dict]:
        llm_client = getattr(self._mapper, "_llm", None)
        cache = DiskCache(self._config.cache_dir)
        extraction_tokens: dict[str, dict] = {}

        def _build_cv_prompt(resume: Resume) -> str:
            exp_lines = []
            for exp in resume.work_experiences:
                if not isinstance(exp, dict):
                    continue
                parts = []
                if exp.get("position"):
                    parts.append(f"Посада: {exp['position']}")
                if exp.get("company"):
                    parts.append(f"Компанія: {exp['company']}")
                if exp.get("industry"):
                    parts.append(f"Галузь: {exp['industry']}")
                if exp.get("responsibilities"):
                    parts.append(f"Обов'язки: {exp['responsibilities']}")
                if parts:
                    exp_lines.append(" | ".join(parts))
            work_text = "\n".join(exp_lines) if exp_lines else "—"

            edu_lines = []
            for edu in resume.educations:
                if not isinstance(edu, dict):
                    continue
                parts = []
                if edu.get("institution"):
                    parts.append(f"Заклад: {edu['institution']}")
                if edu.get("faculty"):
                    parts.append(f"Спеціальність: {edu['faculty']}")
                if edu.get("level"):
                    parts.append(f"Рівень: {edu['level']}")
                if parts:
                    edu_lines.append(" | ".join(parts))
            edu_text = "\n".join(edu_lines) if edu_lines else "—"

            return CV_EXTRACTION_PROMPT.format(
                title=resume.title,
                work_experiences=work_text,
                educations=edu_text,
                additional_info=resume.additional_info or "—",
            )

        if llm_client is None:
            # Fallback to sequential extraction
            from esco_pipeline.extractors.llm_extractor import LLMExtractor
            extractor = LLMExtractor(self._config)
            for vacancy in vacancies:
                if not vacancy.extracted_skills:
                    try:
                        vacancy.extracted_skills = extractor.extract(vacancy)
                        extraction_tokens[vacancy.id] = dict(extractor._last_token_usage)
                    except Exception as e:
                        logger.warning("LLM extraction failed for %s: %s", vacancy.id, e)
            return extraction_tokens

        # Check cache and build prompts for uncached vacancies
        needs_extraction: list[Vacancy] = []
        uncached: list[tuple[int, Vacancy, str, str]] = []  # (idx_in_needs, vacancy, prompt, cache_key)

        for vacancy in vacancies:
            if vacancy.extracted_skills:
                continue

            if isinstance(vacancy, Resume):
                ck = hash_key(
                    "llm_extractor_cv",
                    vacancy.id,
                    vacancy.title,
                    vacancy.work_experiences,
                    vacancy.educations,
                    vacancy.additional_info,
                )
            else:
                ck = hash_key("llm_extractor", vacancy.id, vacancy.title, vacancy.description_text)
            cached = cache.get(ck)
            if cached is not None:
                skills = cached.get("skills", [])
                vacancy.extracted_skills = [
                    SkillSource(text=s, source="llm_extraction", confidence=1.0)
                    for s in skills if s and s.strip()
                ]
            else:
                idx = len(needs_extraction)
                needs_extraction.append(vacancy)
                if isinstance(vacancy, Resume):
                    prompt = _build_cv_prompt(vacancy)
                else:
                    prompt = EXTRACTION_PROMPT.format(
                        title=vacancy.title,
                        text=vacancy.description_text or vacancy.title,
                    )
                uncached.append((idx, vacancy, prompt, ck))

        if not uncached:
            logger.info("LLM extraction: all %d vacancies cached", len(vacancies))
            return extraction_tokens

        logger.info(
            "LLM extraction: %d uncached vacancies to process concurrently",
            len(uncached),
        )

        # Fire all extraction prompts concurrently
        prompts = [item[2] for item in uncached]
        llm_results = llm_client.generate_json_batch(
            prompts, max_concurrent=self._config.llm_max_concurrent,
        )

        for (idx, vacancy, prompt, ck), (parsed, token_usage) in zip(uncached, llm_results):
            skills = parsed.get("skills", []) if isinstance(parsed, dict) else []
            cache.set(ck, {"skills": skills})
            vacancy.extracted_skills = [
                SkillSource(text=s, source="llm_extraction", confidence=1.0)
                for s in skills if s and s.strip()
            ]
            extraction_tokens[vacancy.id] = token_usage

        return extraction_tokens
