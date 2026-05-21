from esco_pipeline.extractors.base import BaseExtractor
from esco_pipeline.models import SkillSource, Vacancy


class PlatformExtractor(BaseExtractor):
    """Returns skills already provided by the job platform."""

    def extract(self, vacancy: Vacancy) -> list[SkillSource]:
        return [
            SkillSource(text=skill, source="platform_array", confidence=1.0)
            for skill in vacancy.raw_skills
            if skill and skill.strip()
        ]
