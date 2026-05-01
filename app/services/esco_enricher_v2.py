"""
ESCO Enricher v2 — skills2-main integration
Replaces the old difflib-based normalizer with a 3-stage pipeline:
  1. FuzzyMapper    — RapidFuzz token_sort_ratio (fast, no API)
  2. EmbeddingMapper — Gemini embeddings + cosine similarity (batch)
  3. LLMMapper(two_stage) — fuzzy+embedding+graph candidates → Gemini re-ranks
"""

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Path setup ────────────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_SKILLS2_DIR = _BASE_DIR / "skills2-main"
if str(_SKILLS2_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS2_DIR))

# ── Lazy singletons ───────────────────────────────────────────────────────────
_esco_index = None
_fuzzy_mapper = None
_embedding_mapper = None
_llm_mapper = None
_settings = None


def _init():
    global _esco_index, _fuzzy_mapper, _embedding_mapper, _llm_mapper, _settings

    if _esco_index is not None:
        return

    from esco_pipeline.config import Settings
    from esco_pipeline.esco_interface import ESCOIndex
    from esco_pipeline.llm_client import LLMClient
    from esco_pipeline.mappers.embedding_mapper import EmbeddingMapper
    from esco_pipeline.mappers.fuzzy_mapper import FuzzyMapper
    from esco_pipeline.mappers.llm_mapper import LLMMapper

    gemini_key = os.getenv("GEMINI_API_KEY", "")

    # _env_file=None prevents pydantic-settings from reading our .env
    # (which contains extra keys that Settings doesn't define)
    _settings = Settings(
        _env_file=None,
        gemini_api_key=gemini_key,
        llm_provider="gemini",
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        fuzzy_threshold=80.0,
        embedding_threshold=0.72,
        llm_batch_size=15,
        llm_max_concurrent=16,
        cache_dir=str(_BASE_DIR / ".cache" / "esco"),
    )

    # Pass gemini_api_key only if embeddings are already cached —
    # pre-computation requires paid tier (free tier is too slow: ~2 RPM).
    # Once .embeddings_cache_en.npz exists, full pipeline unlocks automatically.
    emb_cache = _BASE_DIR / ".embeddings_cache_en.npz"
    active_key = gemini_key if emb_cache.exists() else ""
    if not active_key and gemini_key:
        logger.info("Embedding cache not found — running fuzzy+LLM only (no embeddings). "
                    "Pre-compute once with: python3 precompute_embeddings.py")

    logger.info("Loading ESCO index…")
    _esco_index = ESCOIndex(
        data_dir=str(_BASE_DIR),
        language="en",
        gemini_api_key=active_key,
        cache_dir=str(_BASE_DIR / ".cache" / "esco"),
        embedding_title_weight=0.6,
    )
    logger.info("ESCO index ready: %d skills loaded", len(_esco_index.get_all_labels()))

    llm_client = LLMClient(_settings)

    _fuzzy_mapper = FuzzyMapper(_esco_index, _settings)
    _embedding_mapper = EmbeddingMapper(_esco_index, _settings)
    _llm_mapper = LLMMapper(
        _esco_index,
        _settings,
        fuzzy_mapper=_fuzzy_mapper,
        embedding_mapper=_embedding_mapper,
        mode="two_stage",
        llm_client=llm_client,
    )


# ── Public helpers ────────────────────────────────────────────────────────────

def _esco_chain(uri: str) -> list[str]:
    """Walk parent hierarchy and return list of preferred labels (root first)."""
    _init()
    chain = []
    current = uri
    while current:
        parent = _esco_index.get_parent(current)
        if parent is None:
            break
        chain.append(parent.preferred_label)
        current = parent.uri
    return list(reversed(chain))


def map_skills(skill_raws: list[str]) -> dict[str, dict | None]:
    """
    Map raw skill strings to ESCO using a 3-stage pipeline.
    Returns {skill_raw: {"esco_uri", "esco_label", "esco_type", "skill_category",
                         "confidence", "method"} | None}
    """
    from app.utils.classifiers import get_skill_category

    _init()

    if not skill_raws:
        return {}

    results: dict[str, dict | None] = {}
    remaining = list(skill_raws)

    # ── Stage 1: Fuzzy ────────────────────────────────────────────────────────
    fuzzy_results = _fuzzy_mapper.map_skills(remaining)
    still_unmapped = []
    for skill in remaining:
        m = fuzzy_results.get(skill)
        if m and m.confidence >= 0.85:        # only keep high-confidence fuzzy hits
            skill_obj = _esco_index.get_skill(m.esco_uri)
            esco_type = skill_obj.skill_type if skill_obj else ""
            chain = _esco_chain(m.esco_uri)
            results[skill] = {
                "esco_uri": m.esco_uri,
                "esco_label": m.esco_label,
                "esco_type": esco_type,
                "skill_category": get_skill_category(m.esco_label, m.esco_uri, chain),
                "confidence": m.confidence,
                "method": "fuzzy",
            }
        else:
            still_unmapped.append(skill)

    logger.info("Fuzzy: %d mapped, %d remaining", len(results), len(still_unmapped))

    if not still_unmapped:
        return results

    # ── Stage 2: Embedding ────────────────────────────────────────────────────
    emb_results = _embedding_mapper.map_skills(still_unmapped)
    after_embedding = []
    for skill in still_unmapped:
        m = emb_results.get(skill)
        if m:
            skill_obj = _esco_index.get_skill(m.esco_uri)
            esco_type = skill_obj.skill_type if skill_obj else ""
            chain = _esco_chain(m.esco_uri)
            results[skill] = {
                "esco_uri": m.esco_uri,
                "esco_label": m.esco_label,
                "esco_type": esco_type,
                "skill_category": get_skill_category(m.esco_label, m.esco_uri, chain),
                "confidence": m.confidence,
                "method": "embedding",
            }
        else:
            after_embedding.append(skill)

    logger.info("Embedding: +%d mapped, %d remaining",
                len(still_unmapped) - len(after_embedding), len(after_embedding))

    if not after_embedding:
        return results

    # ── Stage 3: LLM two-stage ────────────────────────────────────────────────
    llm_results = _llm_mapper.map_skills(after_embedding)
    for skill in after_embedding:
        m = llm_results.get(skill)
        if m:
            skill_obj = _esco_index.get_skill(m.esco_uri)
            esco_type = skill_obj.skill_type if skill_obj else ""
            chain = _esco_chain(m.esco_uri)
            results[skill] = {
                "esco_uri": m.esco_uri,
                "esco_label": m.esco_label,
                "esco_type": esco_type,
                "skill_category": get_skill_category(m.esco_label, m.esco_uri, chain),
                "confidence": m.confidence,
                "method": f"llm_{m.method}" if not m.method.startswith("llm") else m.method,
            }
        else:
            results[skill] = None

    llm_mapped = sum(1 for s in after_embedding if results.get(s))
    logger.info("LLM two-stage: +%d mapped, %d truly unmapped",
                llm_mapped, len(after_embedding) - llm_mapped)

    return results
