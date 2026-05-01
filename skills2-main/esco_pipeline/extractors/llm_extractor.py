import logging

from esco_pipeline.config import Settings
from esco_pipeline.extractors.base import BaseExtractor
from esco_pipeline.llm_client import LLMClient
from esco_pipeline.models import Resume, SkillSource, Vacancy
from esco_pipeline.prompts import CV_EXTRACTION_PROMPT, EXTRACTION_PROMPT
from esco_pipeline.utils import DiskCache, hash_key

logger = logging.getLogger(__name__)


class LLMExtractor(BaseExtractor):
    def __init__(self, config: Settings, llm_client: LLMClient | None = None):
        self._config = config
        self._cache = DiskCache(config.cache_dir)
        self._llm = llm_client or LLMClient(config)
        self._last_token_usage: dict = {}

    def extract(self, document: Vacancy | Resume) -> list[SkillSource]:
        self._last_token_usage = {}
        cache_key = hash_key(
            "llm_extractor", document.id, document.title, document.description_text
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            skills = cached.get("skills", [])
        else:
            skills = self._call_llm(document)
            self._cache.set(cache_key, {"skills": skills})

        return [
            SkillSource(text=skill, source="llm_extraction", confidence=1.0)
            for skill in skills
            if skill and skill.strip()
        ]

    def _call_llm(self, document: Vacancy | Resume) -> list[str]:
        if isinstance(document, Resume):
            prompt = self._build_cv_prompt(document)
        else:
            prompt = EXTRACTION_PROMPT.format(
                title=document.title,
                text=document.description_text or document.title,
            )
        parsed, token_usage = self._llm.generate_json(prompt)
        self._last_token_usage = token_usage
        if isinstance(parsed, dict):
            return parsed.get("skills", [])
        return []

    def _build_cv_prompt(self, resume: Resume) -> str:
        # Format work experiences
        exp_lines = []
        for exp in resume.work_experiences:
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

        # Format educations
        edu_lines = []
        for edu in resume.educations:
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
