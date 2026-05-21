from abc import ABC, abstractmethod

from esco_pipeline.models import SkillSource, Vacancy


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, vacancy: Vacancy) -> list[SkillSource]: ...
