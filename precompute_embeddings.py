"""
One-time pre-computation of ESCO embeddings (requires Gemini paid tier).
Run this ONCE. Results cached to .embeddings_cache_en.npz (~50MB).
After that reprocess_skills.py will use full fuzzy+embedding+LLM pipeline.

Usage:
    python3 precompute_embeddings.py
"""

import logging
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "skills2-main"))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key:
        print("ERROR: GEMINI_API_KEY not set in .env")
        sys.exit(1)

    cache_file = BASE_DIR / ".embeddings_cache_en.npz"
    if cache_file.exists():
        logger.info("Cache already exists at %s — nothing to do.", cache_file)
        sys.exit(0)

    from esco_pipeline.esco_interface import ESCOIndex

    logger.info("Starting ESCO embedding pre-computation…")
    logger.info("Requires Gemini paid tier (free tier limit: ~2 RPM → too slow).")
    logger.info("With paid tier (3000 RPM) this takes ~3 minutes.")

    ESCOIndex(
        data_dir=str(BASE_DIR),
        language="en",
        gemini_api_key=gemini_key,
        cache_dir=str(BASE_DIR / ".cache" / "esco"),
    )

    if cache_file.exists():
        size_mb = cache_file.stat().st_size / 1_000_000
        logger.info("Done! Cache saved: %s (%.1f MB)", cache_file, size_mb)
        logger.info("Now run:  python3 reprocess_skills.py")
    else:
        logger.error("Cache file not found after computation — something went wrong.")
