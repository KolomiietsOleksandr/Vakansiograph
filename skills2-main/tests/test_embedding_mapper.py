import pytest
from esco_pipeline.mappers.embedding_mapper import EmbeddingMapper


def test_embedding_mapper_exact_match(mock_esco_index, mock_config):
    mock_config.embedding_threshold = 0.5
    mapper = EmbeddingMapper(mock_esco_index, mock_config)
    results = mapper.map_skills(["Python"])
    assert "Python" in results
    # MockESCOIndex uses fuzzy for embeddings, so "Python" should match
    mapping = results["Python"]
    assert mapping is not None
    assert mapping.method == "embedding"


def test_embedding_mapper_no_match_high_threshold(mock_esco_index, mock_config):
    mock_config.embedding_threshold = 0.999
    mapper = EmbeddingMapper(mock_esco_index, mock_config)
    results = mapper.map_skills(["zzz_no_match_skill"])
    assert results["zzz_no_match_skill"] is None


def test_embedding_mapper_empty_skill(mock_esco_index, mock_config):
    mapper = EmbeddingMapper(mock_esco_index, mock_config)
    results = mapper.map_skills([""])
    assert results[""] is None


def test_embedding_mapper_name(mock_esco_index, mock_config):
    mapper = EmbeddingMapper(mock_esco_index, mock_config)
    assert mapper.name() == "embedding"


def test_embedding_mapper_multiple_skills(mock_esco_index, mock_config):
    mock_config.embedding_threshold = 0.5
    mapper = EmbeddingMapper(mock_esco_index, mock_config)
    skills = ["Python", "SQL", "teamwork"]
    results = mapper.map_skills(skills)
    assert len(results) == 3
    for skill in skills:
        assert skill in results


def test_embedding_mapper_confidence_in_range(mock_esco_index, mock_config):
    mock_config.embedding_threshold = 0.5
    mapper = EmbeddingMapper(mock_esco_index, mock_config)
    results = mapper.map_skills(["Python"])
    mapping = results["Python"]
    if mapping:
        assert 0.0 <= mapping.confidence <= 1.0
