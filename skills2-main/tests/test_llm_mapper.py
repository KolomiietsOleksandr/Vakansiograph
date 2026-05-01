import json
import pytest
from unittest.mock import MagicMock, patch

from esco_pipeline.mappers.llm_mapper import LLMMapper
from esco_pipeline.mappers.fuzzy_mapper import FuzzyMapper
from esco_pipeline.mappers.embedding_mapper import EmbeddingMapper


@pytest.fixture
def llm_mapper_direct(mock_esco_index, mock_config):
    mock_llm = MagicMock()
    fuzzy = FuzzyMapper(mock_esco_index, mock_config)
    embedding = EmbeddingMapper(mock_esco_index, mock_config)
    return LLMMapper(mock_esco_index, mock_config, fuzzy, embedding, mode="direct", llm_client=mock_llm)


@pytest.fixture
def llm_mapper_two_stage(mock_esco_index, mock_config):
    mock_llm = MagicMock()
    fuzzy = FuzzyMapper(mock_esco_index, mock_config)
    embedding = EmbeddingMapper(mock_esco_index, mock_config)
    return LLMMapper(mock_esco_index, mock_config, fuzzy, embedding, mode="two_stage", llm_client=mock_llm)


def test_name_direct(llm_mapper_direct):
    assert llm_mapper_direct.name() == "llm_direct"


def test_name_two_stage(llm_mapper_two_stage):
    assert llm_mapper_two_stage.name() == "llm_two_stage"


def test_format_candidates_with_skills(llm_mapper_direct, mock_esco_index):
    skills = [mock_esco_index.get_skill("http://data.europa.eu/esco/skill/S001")]
    text, id_to_uri = llm_mapper_direct._format_candidates(skills)
    assert "[1]" in text
    assert "Python programming" in text
    assert id_to_uri == {1: "http://data.europa.eu/esco/skill/S001"}


def test_format_candidates_empty(llm_mapper_direct):
    text, id_to_uri = llm_mapper_direct._format_candidates([])
    assert text == "(no candidates found)"
    assert id_to_uri == {}


def test_parse_mappings_with_compressed_id(llm_mapper_direct):
    id_to_uri = {1: "http://data.europa.eu/esco/skill/S001"}
    raw = {
        "mappings": [
            {
                "raw_skill": "Python",
                "esco_id": 1,
                "esco_label": "Python programming",
                "confidence": 0.9,
                "reasoning": "exact match",
            }
        ],
        "unmapped": [],
    }
    results = llm_mapper_direct._parse_mappings(["Python"], raw, id_to_uri=id_to_uri)
    assert results["Python"] is not None
    assert results["Python"].esco_uri == "http://data.europa.eu/esco/skill/S001"
    assert results["Python"].confidence == 0.9


def test_parse_mappings_with_string_id(llm_mapper_direct):
    """LLM may return the numeric ID as a string."""
    id_to_uri = {1: "http://data.europa.eu/esco/skill/S001"}
    raw = {
        "mappings": [
            {
                "raw_skill": "Python",
                "esco_id": "1",
                "esco_label": "Python programming",
                "confidence": 0.9,
                "reasoning": "exact match",
            }
        ],
    }
    results = llm_mapper_direct._parse_mappings(["Python"], raw, id_to_uri=id_to_uri)
    assert results["Python"] is not None
    assert results["Python"].esco_uri == "http://data.europa.eu/esco/skill/S001"


def test_parse_mappings_hallucinated_id(llm_mapper_direct):
    """Invalid compressed ID (not in mapping) is caught."""
    id_to_uri = {1: "http://data.europa.eu/esco/skill/S001"}
    raw = {
        "mappings": [
            {
                "raw_skill": "Python",
                "esco_id": 999,
                "esco_label": "Fake skill",
                "confidence": 0.9,
                "reasoning": "hallucination",
            }
        ]
    }
    results = llm_mapper_direct._parse_mappings(["Python"], raw, id_to_uri=id_to_uri)
    assert results["Python"] is None


def test_parse_mappings_valid_uri_without_id_mapping(llm_mapper_direct):
    """Backwards compat: still works with full URIs when id_to_uri is None."""
    raw = {
        "mappings": [
            {
                "raw_skill": "Python",
                "esco_uri": "http://data.europa.eu/esco/skill/S001",
                "esco_label": "Python programming",
                "confidence": 0.9,
                "reasoning": "exact match",
            }
        ],
        "unmapped": [],
    }
    results = llm_mapper_direct._parse_mappings(["Python"], raw)
    assert results["Python"] is not None
    assert results["Python"].esco_uri == "http://data.europa.eu/esco/skill/S001"


def test_parse_mappings_hallucinated_uri(llm_mapper_direct):
    raw = {
        "mappings": [
            {
                "raw_skill": "Python",
                "esco_uri": "http://fake.uri/nonexistent",
                "esco_label": "Fake skill",
                "confidence": 0.9,
                "reasoning": "hallucination",
            }
        ]
    }
    results = llm_mapper_direct._parse_mappings(["Python"], raw)
    assert results["Python"] is None


def test_parse_mappings_invalid_raw(llm_mapper_direct):
    results = llm_mapper_direct._parse_mappings(["Python"], "not a dict")
    assert results["Python"] is None


def test_find_original_skill_exact(llm_mapper_direct):
    skills = ["Python", "SQL"]
    assert llm_mapper_direct._find_original_skill("Python", skills) == "Python"


def test_find_original_skill_case_insensitive(llm_mapper_direct):
    skills = ["Python", "SQL"]
    assert llm_mapper_direct._find_original_skill("python", skills) == "Python"


def test_find_original_skill_not_found(llm_mapper_direct):
    skills = ["Python", "SQL"]
    assert llm_mapper_direct._find_original_skill("Rust", skills) is None


def test_map_skills_returns_all_keys(llm_mapper_direct):
    raw_response = {
        "mappings": [
            {
                "raw_skill": "Python",
                "esco_id": 1,
                "esco_label": "Python programming",
                "confidence": 0.85,
                "reasoning": "match",
            }
        ],
        "unmapped": ["SQL"],
    }
    llm_mapper_direct._llm.generate_json_batch = MagicMock(
        return_value=[(raw_response, {"input": 0, "output": 0, "total": 0})]
    )

    results = llm_mapper_direct.map_skills(["Python", "SQL"])
    assert "Python" in results
    assert "SQL" in results
    assert results["Python"] is not None
    assert results["SQL"] is None


def test_two_stage_makes_single_llm_call(llm_mapper_two_stage, tmp_path):
    """_map_two_stage no longer calls the extraction prompt — only one LLM call per batch."""
    raw_response = {
        "mappings": [{"raw_skill": "Python", "esco_id": 1,
                      "esco_label": "Python programming", "confidence": 0.9, "reasoning": ""}]
    }
    llm_mapper_two_stage._llm.generate_json_batch = MagicMock(
        return_value=[(raw_response, {"input": 0, "output": 0, "total": 0})]
    )
    llm_mapper_two_stage._cache._dir = tmp_path

    results = llm_mapper_two_stage.map_skills(["Python"])
    llm_mapper_two_stage._llm.generate_json_batch.assert_called_once()
    assert results["Python"] is not None
    assert results["Python"].raw_skill == "Python"


def test_map_skills_uses_cache(llm_mapper_direct, tmp_path):
    """map_skills uses DiskCache so repeated calls don't re-invoke LLM."""
    raw_response = {"mappings": [{"raw_skill": "Python", "esco_id": 1, "esco_label": "Python programming", "confidence": 0.9, "reasoning": ""}], "unmapped": []}
    llm_mapper_direct._llm.generate_json_batch = MagicMock(
        return_value=[(raw_response, {"input": 0, "output": 0, "total": 0})]
    )
    llm_mapper_direct._cache._dir = tmp_path

    llm_mapper_direct.map_skills(["Python"])
    llm_mapper_direct.map_skills(["Python"])
    # Second call served from cache — generate_json_batch called only once
    assert llm_mapper_direct._llm.generate_json_batch.call_count == 1


def test_last_token_usage_populated_after_live_call(llm_mapper_direct, tmp_path):
    """_last_token_usage reflects token usage from the LLM response."""
    llm_mapper_direct._llm.generate_json = MagicMock(
        return_value=({"mappings": []}, {"input": 100, "output": 50, "total": 150})
    )
    llm_mapper_direct._cache._dir = tmp_path

    llm_mapper_direct._map_direct_with_context(["Python"], "Engineer", "desc", "candidates")

    assert llm_mapper_direct._last_token_usage == {"input": 100, "output": 50, "total": 150}


def test_last_token_usage_zero_on_cache_hit(llm_mapper_direct, tmp_path):
    """_last_token_usage is {} when result is served from cache."""
    llm_mapper_direct._llm.generate_json = MagicMock(
        return_value=({"mappings": []}, {"input": 100, "output": 50, "total": 150})
    )
    llm_mapper_direct._cache._dir = tmp_path

    # First call (live)
    llm_mapper_direct._map_direct_with_context(["Python"], "Engineer", "desc", "candidates")
    # Second call (from cache)
    llm_mapper_direct._map_direct_with_context(["Python"], "Engineer", "desc", "candidates")

    assert llm_mapper_direct._last_token_usage == {}
