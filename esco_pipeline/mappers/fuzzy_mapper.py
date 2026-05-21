from rapidfuzz import fuzz, process

from esco_pipeline.config import Settings
from esco_pipeline.esco_interface import ESCOIndexInterface
from esco_pipeline.mappers.base import BaseMapper
from esco_pipeline.models import ESCOMapping
from esco_pipeline.utils import normalize_text


class FuzzyMapper(BaseMapper):
    def __init__(self, esco_index: ESCOIndexInterface, config: Settings):
        self._index = esco_index
        self._config = config

    def name(self) -> str:
        return "fuzzy"

    def map_skills(self, skill_strings: list[str]) -> dict[str, ESCOMapping | None]:
        labels = self._index.get_all_labels()
        label_list = list(labels.keys())
        results: dict[str, ESCOMapping | None] = {}

        for skill in skill_strings:
            normalized = normalize_text(skill)
            if not normalized:
                results[skill] = None
                continue

            match = process.extractOne(
                normalized, label_list, scorer=fuzz.token_sort_ratio
            )
            if match is None:
                results[skill] = None
                continue

            matched_label, score, _ = match
            if score >= self._config.fuzzy_threshold:
                uri = labels[matched_label]
                esco_skill = self._index.get_skill(uri)
                preferred_label = esco_skill.preferred_label if esco_skill else matched_label
                results[skill] = ESCOMapping(
                    raw_skill=skill,
                    esco_uri=uri,
                    esco_label=preferred_label,
                    confidence=score / 100.0,
                    method="fuzzy",
                    details={"matched_label": matched_label, "score": score},
                )
            else:
                results[skill] = None

        return results
