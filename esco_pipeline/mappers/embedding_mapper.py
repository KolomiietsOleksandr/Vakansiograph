from esco_pipeline.config import Settings
from esco_pipeline.esco_interface import ESCOIndexInterface
from esco_pipeline.mappers.base import BaseMapper
from esco_pipeline.models import ESCOMapping


class EmbeddingMapper(BaseMapper):
    def __init__(self, esco_index: ESCOIndexInterface, config: Settings):
        self._index = esco_index
        self._config = config

    def name(self) -> str:
        return "embedding"

    def map_skills(self, skill_strings: list[str]) -> dict[str, ESCOMapping | None]:
        results: dict[str, ESCOMapping | None] = {}

        for skill in skill_strings:
            if not skill.strip():
                results[skill] = None
                continue

            hits = self._index.search_by_embedding(skill, top_k=3)
            if not hits:
                results[skill] = None
                continue

            # Return best match above threshold
            best = None
            for uri, similarity in hits:
                if similarity >= self._config.embedding_threshold:
                    if best is None or similarity > best[1]:
                        best = (uri, similarity)

            if best:
                uri, similarity = best
                esco_skill = self._index.get_skill(uri)
                label = esco_skill.preferred_label if esco_skill else uri
                results[skill] = ESCOMapping(
                    raw_skill=skill,
                    esco_uri=uri,
                    esco_label=label,
                    confidence=similarity,
                    method="embedding",
                    details={"similarity": similarity},
                )
            else:
                results[skill] = None

        return results
