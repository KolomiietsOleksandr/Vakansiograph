from abc import ABC, abstractmethod

from esco_pipeline.models import ESCOMapping


class BaseMapper(ABC):
    @abstractmethod
    def map_skills(self, skill_strings: list[str]) -> dict[str, ESCOMapping | None]: ...

    @abstractmethod
    def name(self) -> str: ...
