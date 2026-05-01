import pytest
from unittest.mock import patch
from esco_pipeline.mappers.embedding_mapper import EmbeddingMapper
from esco_pipeline.mappers.fuzzy_mapper import FuzzyMapper
from esco_pipeline.models import DocumentResult, SkillSource, Vacancy
from esco_pipeline.pipeline import Pipeline


def make_vacancies():
    return [
        Vacancy(
            id="v1",
            title="Python Developer",
            raw_skills=["Python", "SQL"],
            description_text="Looking for a Python developer with SQL skills.",
        ),
        Vacancy(
            id="v2",
            title="Project Manager",
            raw_skills=["project management", "teamwork"],
            description_text="We need an experienced project manager.",
        ),
        Vacancy(
            id="v3",
            title="Unknown Role",
            raw_skills=[],
            description_text="",
        ),
    ]


def test_pipeline_returns_document_results(mock_esco_index, mock_config):
    mapper = FuzzyMapper(mock_esco_index, mock_config)
    pipeline = Pipeline(mapper, mock_esco_index, mock_config)
    vacancies = make_vacancies()
    results = pipeline.run(vacancies)
    assert isinstance(results, list)
    assert len(results) == 3
    for r in results:
        assert isinstance(r, DocumentResult)


def test_pipeline_document_ids(mock_esco_index, mock_config):
    mapper = FuzzyMapper(mock_esco_index, mock_config)
    pipeline = Pipeline(mapper, mock_esco_index, mock_config)
    results = pipeline.run(make_vacancies())
    ids = {r.document_id for r in results}
    assert "v1" in ids
    assert "v2" in ids
    assert "v3" in ids


def test_pipeline_mappings_and_unmapped(mock_esco_index, mock_config):
    mapper = FuzzyMapper(mock_esco_index, mock_config)
    pipeline = Pipeline(mapper, mock_esco_index, mock_config)
    results = pipeline.run(make_vacancies())
    doc_map = {r.document_id: r for r in results}

    v1 = doc_map["v1"]
    # Python and SQL should be mappable
    assert len(v1.direct_mappings) + len(v1.graph_mappings) + len(v1.unmapped_skills) == 2


def test_pipeline_metadata(mock_esco_index, mock_config):
    mapper = FuzzyMapper(mock_esco_index, mock_config)
    pipeline = Pipeline(mapper, mock_esco_index, mock_config)
    results = pipeline.run(make_vacancies())
    for r in results:
        assert "mapper" in r.metadata
        assert r.metadata["mapper"] == "fuzzy"


def test_pipeline_empty_vacancy(mock_esco_index, mock_config):
    mapper = FuzzyMapper(mock_esco_index, mock_config)
    pipeline = Pipeline(mapper, mock_esco_index, mock_config)
    vacancies = [Vacancy(id="empty", title="Empty", raw_skills=[])]
    results = pipeline.run(vacancies)
    assert len(results) == 1
    assert results[0].direct_mappings == [] and results[0].graph_mappings == []
    assert results[0].unmapped_skills == []


def test_pipeline_deduplicates_skills(mock_esco_index, mock_config):
    mapper = FuzzyMapper(mock_esco_index, mock_config)
    pipeline = Pipeline(mapper, mock_esco_index, mock_config)
    # Two vacancies with same skill — should only map once
    vacancies = [
        Vacancy(id="a", title="A", raw_skills=["Python"]),
        Vacancy(id="b", title="B", raw_skills=["Python"]),
    ]
    results = pipeline.run(vacancies)
    assert len(results) == 2
    for r in results:
        assert len(r.direct_mappings) + len(r.graph_mappings) + len(r.unmapped_skills) == 1


def test_embedding_pipeline_skips_extraction_without_api_key(mock_esco_index, mock_config):
    mock_config.gemini_api_key = ""
    mapper = EmbeddingMapper(mock_esco_index, mock_config)
    pipeline = Pipeline(mapper, mock_esco_index, mock_config)
    with patch.object(pipeline, "_run_llm_extraction") as mock_extract:
        pipeline.run([Vacancy(id="v1", title="Dev", raw_skills=["Python"])])
    mock_extract.assert_not_called()


def test_embedding_pipeline_triggers_extraction(mock_esco_index, mock_config):
    mapper = EmbeddingMapper(mock_esco_index, mock_config)
    pipeline = Pipeline(mapper, mock_esco_index, mock_config)
    vacancies = [Vacancy(id="v1", title="Dev", raw_skills=["Python"])]
    with patch.object(pipeline, "_run_llm_extraction") as mock_extract:
        pipeline.run(vacancies)
    mock_extract.assert_called_once_with(vacancies)


def test_embedding_pipeline_includes_title(mock_esco_index, mock_config):
    mapper = EmbeddingMapper(mock_esco_index, mock_config)
    pipeline = Pipeline(mapper, mock_esco_index, mock_config)
    vacancies = [Vacancy(id="v1", title="Data Scientist", raw_skills=[])]
    with patch.object(pipeline, "_run_llm_extraction"):
        results = pipeline.run(vacancies)
    skill_strings = [m.raw_skill for m in results[0].direct_mappings + results[0].graph_mappings] + results[0].unmapped_skills
    assert "Data Scientist" in skill_strings


def test_embedding_pipeline_includes_extracted_skills(mock_esco_index, mock_config):
    mapper = EmbeddingMapper(mock_esco_index, mock_config)
    pipeline = Pipeline(mapper, mock_esco_index, mock_config)
    vacancy = Vacancy(id="v1", title="Dev", raw_skills=[])
    vacancy.extracted_skills = [SkillSource(text="machine learning", source="llm", confidence=0.9)]
    with patch.object(pipeline, "_run_llm_extraction"):
        results = pipeline.run([vacancy])
    skill_strings = [m.raw_skill for m in results[0].direct_mappings + results[0].graph_mappings] + results[0].unmapped_skills
    assert "machine learning" in skill_strings


def test_fuzzy_pipeline_does_not_include_title(mock_esco_index, mock_config):
    mapper = FuzzyMapper(mock_esco_index, mock_config)
    pipeline = Pipeline(mapper, mock_esco_index, mock_config)
    vacancies = [Vacancy(id="v1", title="Unique Job Title XYZ", raw_skills=["Python"])]
    results = pipeline.run(vacancies)
    skill_strings = [m.raw_skill for m in results[0].direct_mappings + results[0].graph_mappings] + results[0].unmapped_skills
    assert "Unique Job Title XYZ" not in skill_strings
