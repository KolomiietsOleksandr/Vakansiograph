from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # LLM provider: "gemini" or "vllm"
    llm_provider: str = "gemini"

    # Gemini API
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # vLLM / OpenAI-compatible server
    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_model: str = "gpt-oss-120b"
    vllm_api_key: str = "EMPTY"  # vLLM default; set if server requires auth

    # Dataset
    dataset_name: str = "KSE-RESEARCH-Group/Work_UA_vacancies"
    sample_size: int | None = None
    select_first: int | None = None
    random_seed: int = 42

    # Fuzzy mapper
    fuzzy_threshold: float = 80.0

    # Embedding mapper
    embedding_threshold: float = 0.72
    embedding_title_weight: float = 0.6
    embedding_sibling_threshold: float = 0.5

    # LLM mapper
    llm_max_candidates: int = 100
    llm_batch_size: int = 10
    llm_rescore_threshold: float = 0.7
    llm_max_concurrent: int = 32  # max parallel LLM requests (for vLLM throughput)

    # vLLM-optimized mapper
    vllm_candidates_per_skill: int = 10  # fuzzy top-5 + embedding top-5, deduped

    # ESCO data
    esco_data_dir: str = "esco"
    esco_language: str = "uk"

    # Cache
    cache_dir: str = ".cache"

    # Output
    output_dir: str = "output"
