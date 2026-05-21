from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillSource:
    text: str
    source: str
    confidence: float


@dataclass
class Vacancy:
    id: str
    title: str
    raw_skills: list[str] = field(default_factory=list)
    extracted_skills: list[SkillSource] = field(default_factory=list)
    description_text: str = ""
    location: str = ""
    company_name: str = ""
    salary: str = ""


@dataclass
class Resume:
    id: str
    title: str  # desired position
    raw_skills: list[str] = field(default_factory=list)
    extracted_skills: list[SkillSource] = field(default_factory=list)
    description_text: str = ""  # flat fallback for fuzzy mapper
    location: str = ""
    candidate_name: str = ""
    salary: str = ""
    work_experiences: list[dict] = field(default_factory=list)
    educations: list[dict] = field(default_factory=list)
    additional_info: str = ""


# Union type for pipeline input
Document = Vacancy | Resume


@dataclass
class ESCOMapping:
    raw_skill: str
    esco_uri: str
    esco_label: str
    confidence: float
    method: str
    details: dict[str, Any] = field(default_factory=dict)
    via_graph: bool = False


@dataclass
class DocumentResult:
    document_id: str
    direct_mappings: list[ESCOMapping] = field(default_factory=list)
    graph_mappings: list[ESCOMapping] = field(default_factory=list)
    unmapped_skills: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
