"""Pre-compute and cache ESCO skill embeddings using Gemini API."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from esco_pipeline.config import Settings
from esco_pipeline.esco_interface import ESCOIndex

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    config = Settings()

    if not config.gemini_api_key:
        logger.error("GEMINI_API_KEY is not set. Add it to .env or set the environment variable.")
        sys.exit(1)

    logger.info("Loading ESCO index (language=%s, data_dir=%s)...", config.esco_language, config.esco_data_dir)

    index = ESCOIndex(
        data_dir=config.esco_data_dir,
        language=config.esco_language,
        gemini_api_key=config.gemini_api_key,
    )

    cache_path = Path(config.esco_data_dir) / f".embeddings_cache_{config.esco_language}.npz"
    desc_cache_path = Path(config.esco_data_dir) / f".embeddings_cache_{config.esco_language}_desc.npz"
    logger.info("Done. %d label embedding vectors cached at %s", len(index._embedding_uris), cache_path)
    if index._desc_embedding_matrix is not None:
        logger.info("Description embeddings cached at %s", desc_cache_path)


if __name__ == "__main__":
    main()
