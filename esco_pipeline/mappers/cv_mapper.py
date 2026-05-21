"""Multi-signal ESCO candidate retrieval mapper for CVs/resumes.

Uses structured CV sections (work experience, education) as additional
signals for ESCO candidate retrieval via embedding search, then merges
with platform skills mapped through fuzzy/embedding mappers.
"""

import logging
from collections import defaultdict

from esco_pipeline.config import Settings
from esco_pipeline.esco_interface import ESCOIndexInterface
from esco_pipeline.mappers.base import BaseMapper
from esco_pipeline.mappers.embedding_mapper import EmbeddingMapper
from esco_pipeline.mappers.fuzzy_mapper import FuzzyMapper
from esco_pipeline.models import ESCOMapping, Resume

logger = logging.getLogger(__name__)


class CVWeightedMapper(BaseMapper):
    """Maps CV skills using multi-signal candidate retrieval.

    Algorithm per resume:
    1. Platform skills (raw_skills) — mapped via fuzzy + embedding (same as vacancy)
    2. Work experience signals — embedding search on position + responsibilities
       with overlap boost when both match
    3. Education signals — embedding search on faculty
    4. Merge all candidates, deduplicate by URI, keep highest weighted score
    """

    def __init__(
        self,
        esco_index: ESCOIndexInterface,
        config: Settings,
        fuzzy: FuzzyMapper | None = None,
        embedding: EmbeddingMapper | None = None,
    ):
        self._index = esco_index
        self._config = config
        self._fuzzy = fuzzy or FuzzyMapper(esco_index, config)
        self._embedding = embedding or EmbeddingMapper(esco_index, config)

    def name(self) -> str:
        return "cv_weighted"

    def map_skills(self, skill_strings: list[str]) -> dict[str, ESCOMapping | None]:
        """Fallback: map plain skill strings via fuzzy + embedding merge."""
        fuzzy_results = self._fuzzy.map_skills(skill_strings)
        embedding_results = self._embedding.map_skills(skill_strings)

        merged: dict[str, ESCOMapping | None] = {}
        for skill in skill_strings:
            f = fuzzy_results.get(skill)
            e = embedding_results.get(skill)
            if f and e:
                merged[skill] = f if f.confidence >= e.confidence else e
            else:
                merged[skill] = f or e
        return merged

    def map_resume(self, resume: Resume) -> dict[str, ESCOMapping | None]:
        """Map a resume using multi-signal candidate retrieval."""
        # 1. Map platform skills via fuzzy + embedding
        results: dict[str, ESCOMapping | None] = {}
        if resume.raw_skills:
            results = self.map_skills(resume.raw_skills)

        # 2. Collect section-based candidates via embedding search
        # uri -> (weighted_score, label)
        section_candidates: dict[str, tuple[float, str]] = defaultdict(lambda: (0.0, ""))

        exp_weight = self._config.cv_experience_weight
        edu_weight = self._config.cv_education_weight
        overlap_boost = self._config.cv_overlap_boost

        # Work experience signals
        for exp in resume.work_experiences:
            position = exp.get("position") or ""
            responsibilities = exp.get("responsibilities") or ""

            if not position and not responsibilities:
                continue

            title_hits: dict[str, float] = {}
            resp_hits: dict[str, float] = {}

            if position.strip():
                for uri, score in self._index.search_by_embedding(position, top_k=10):
                    title_hits[uri] = score

            if responsibilities.strip():
                for uri, score in self._index.search_by_embedding(responsibilities, top_k=10):
                    resp_hits[uri] = score

            # Overlap boost: candidates in both get boosted
            all_uris = set(title_hits) | set(resp_hits)
            for uri in all_uris:
                t_score = title_hits.get(uri, 0.0)
                r_score = resp_hits.get(uri, 0.0)
                base_score = max(t_score, r_score)

                if uri in title_hits and uri in resp_hits:
                    weighted = base_score * exp_weight * overlap_boost
                else:
                    weighted = base_score * exp_weight

                cur_score, cur_label = section_candidates[uri]
                if weighted > cur_score:
                    skill = self._index.get_skill(uri)
                    label = skill.preferred_label if skill else uri
                    section_candidates[uri] = (weighted, label)

        # Education signals
        for edu in resume.educations:
            faculty = edu.get("faculty") or ""
            if not faculty.strip():
                continue

            for uri, score in self._index.search_by_embedding(faculty, top_k=5):
                weighted = score * edu_weight
                cur_score, cur_label = section_candidates[uri]
                if weighted > cur_score:
                    skill = self._index.get_skill(uri)
                    label = skill.preferred_label if skill else uri
                    section_candidates[uri] = (weighted, label)

        # 3. Convert section candidates above threshold to mappings
        threshold = self._config.embedding_threshold
        for uri, (score, label) in section_candidates.items():
            if score < threshold:
                continue

            # Don't overwrite a higher-confidence mapping from raw_skills
            skill_key = f"_cv_section:{label}"
            existing = results.get(skill_key)
            if existing and existing.confidence >= score:
                continue

            results[skill_key] = ESCOMapping(
                raw_skill=label,
                esco_uri=uri,
                esco_label=label,
                confidence=score,
                method="cv_weighted",
                details={"source": "cv_section"},
            )

        return results
