"""Verify cached ESCO embeddings by running sample similarity searches."""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from esco_pipeline.config import Settings
from esco_pipeline.esco_interface import ESCOIndex

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

SAMPLE_QUERIES = [
    "програмування",
    "управління проєктами",
    "комунікація",
    "аналіз даних",
]


def run_query(index: ESCOIndex, query: str, top_k: int = 5) -> None:
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"{'='*60}")
    results = index.search_by_embedding(query, top_k=top_k)
    for rank, (uri, score) in enumerate(results, 1):
        skill = index.get_skill(uri)
        label = skill.preferred_label if skill else uri
        print(f"  {rank}. [{score:.4f}] {label}")


def main():
    parser = argparse.ArgumentParser(description="Verify ESCO embedding search")
    parser.add_argument("--query", type=str, nargs="+", help="Custom query strings to search")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results per query")
    args = parser.parse_args()

    config = Settings()
    if not config.gemini_api_key:
        logger.error("GEMINI_API_KEY is not set. Add it to .env or set the environment variable.")
        sys.exit(1)

    logger.info("Loading ESCO index (language=%s)...", config.esco_language)
    index = ESCOIndex(
        data_dir=config.esco_data_dir,
        language=config.esco_language,
        gemini_api_key=config.gemini_api_key,
    )
    logger.info("Index ready: %d embeddings loaded", len(index._embedding_uris))

    queries = args.query if args.query else SAMPLE_QUERIES
    for query in queries:
        run_query(index, query, top_k=args.top_k)

    print()


if __name__ == "__main__":
    main()
