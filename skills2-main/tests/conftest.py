import pytest
from pathlib import Path

from esco_pipeline.esco_interface import MockESCOIndex

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_esco_index():
    return MockESCOIndex(FIXTURES_DIR / "mock_esco.json")


@pytest.fixture
def mock_config():
    from esco_pipeline.config import Settings
    return Settings(
        gemini_api_key="test_key",
        fuzzy_threshold=70.0,
        embedding_threshold=0.5,
        llm_max_candidates=10,
        llm_batch_size=5,
        cache_dir="/tmp/test_esco_cache",
    )
