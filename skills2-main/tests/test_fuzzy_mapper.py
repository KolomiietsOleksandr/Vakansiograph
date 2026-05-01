import pytest
from esco_pipeline.mappers.fuzzy_mapper import FuzzyMapper


def test_fuzzy_mapper_exact_match(mock_esco_index, mock_config):
    mapper = FuzzyMapper(mock_esco_index, mock_config)
    results = mapper.map_skills(["Python"])
    assert "Python" in results
    mapping = results["Python"]
    assert mapping is not None
    assert mapping.method == "fuzzy"
    assert "S001" in mapping.esco_uri


def test_fuzzy_mapper_near_match(mock_esco_index, mock_config):
    mapper = FuzzyMapper(mock_esco_index, mock_config)
    results = mapper.map_skills(["python programming"])
    assert results["python programming"] is not None


def test_fuzzy_mapper_no_match(mock_esco_index, mock_config):
    mock_config.fuzzy_threshold = 95.0  # Very high threshold
    mapper = FuzzyMapper(mock_esco_index, mock_config)
    results = mapper.map_skills(["xyzzy_nonexistent_skill_12345"])
    assert results["xyzzy_nonexistent_skill_12345"] is None


def test_fuzzy_mapper_multiple_skills(mock_esco_index, mock_config):
    mapper = FuzzyMapper(mock_esco_index, mock_config)
    skills = ["Python", "SQL", "teamwork"]
    results = mapper.map_skills(skills)
    assert len(results) == 3
    for skill in skills:
        assert skill in results


def test_fuzzy_mapper_empty_skill(mock_esco_index, mock_config):
    mapper = FuzzyMapper(mock_esco_index, mock_config)
    results = mapper.map_skills([""])
    assert results[""] is None


def test_fuzzy_mapper_name(mock_esco_index, mock_config):
    mapper = FuzzyMapper(mock_esco_index, mock_config)
    assert mapper.name() == "fuzzy"


def test_fuzzy_mapper_confidence_range(mock_esco_index, mock_config):
    mapper = FuzzyMapper(mock_esco_index, mock_config)
    results = mapper.map_skills(["Python"])
    mapping = results["Python"]
    if mapping:
        assert 0.0 <= mapping.confidence <= 1.0
