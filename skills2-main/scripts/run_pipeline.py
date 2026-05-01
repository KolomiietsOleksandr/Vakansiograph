"""CLI for running the ESCO skill mapping pipeline."""
import argparse
import dataclasses
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from esco_pipeline.config import Settings
from esco_pipeline.esco_interface import ESCOIndex, MockESCOIndex
from esco_pipeline.loader import load_resumes, load_vacancies
from esco_pipeline.mappers.embedding_mapper import EmbeddingMapper
from esco_pipeline.mappers.fuzzy_mapper import FuzzyMapper
from esco_pipeline.mappers.llm_mapper import LLMMapper
from esco_pipeline.pipeline import Pipeline

_log_fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_root = logging.getLogger()
_root.setLevel(logging.INFO)

_console = logging.StreamHandler()
_console.setFormatter(logging.Formatter(_log_fmt))
_root.addHandler(_console)

Path("output").mkdir(exist_ok=True)
_file = logging.FileHandler("output/pipeline.log")
_file.setFormatter(logging.Formatter(_log_fmt))
_root.addHandler(_file)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _load_done_ids(output_file: Path) -> set[str]:
    """Read an existing JSONL output and return the set of document_ids already processed."""
    done: set[str] = set()
    if not output_file.exists():
        return done
    with open(output_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
                doc_id = doc.get("document_id")
                if doc_id:
                    done.add(str(doc_id))
            except json.JSONDecodeError:
                continue
    return done


def build_mapper(mapper_name: str, esco_index, config: Settings):
    fuzzy = FuzzyMapper(esco_index, config)
    embedding = EmbeddingMapper(esco_index, config)

    if mapper_name == "fuzzy":
        return fuzzy
    elif mapper_name == "embedding":
        return embedding
    elif mapper_name == "llm_direct":
        return LLMMapper(esco_index, config, fuzzy, embedding, mode="direct")
    elif mapper_name == "llm_two_stage":
        return LLMMapper(esco_index, config, fuzzy, embedding, mode="two_stage")
    elif mapper_name == "vllm_optimized":
        from esco_pipeline.mappers.vllm_optimized_mapper import VLLMOptimizedMapper
        return VLLMOptimizedMapper(esco_index, config, fuzzy, embedding)
    elif mapper_name == "cv_weighted":
        from esco_pipeline.mappers.cv_mapper import CVWeightedMapper
        return CVWeightedMapper(esco_index, config, fuzzy, embedding)
    else:
        raise ValueError(f"Unknown mapper: {mapper_name}")


def _batched(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


# ------------------------------------------------------------------
# Core run logic
# ------------------------------------------------------------------

def run_single(
    mapper_name: str,
    vacancies,
    esco_index,
    config: Settings,
    output_path: Path,
    *,
    resume: bool = False,
    batch_size: int = 0,
):
    """Run a single mapper over *vacancies* and write JSONL output.

    When *resume* is True the output file is opened in append mode and
    vacancies whose ``document_id`` already appears in the file are skipped.

    When *batch_size* > 0 the vacancy list is split into batches of that
    size, each batch is run through the pipeline independently, and results
    are flushed to disk after every batch so progress is never lost.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_file = output_path.parent / f"{output_path.stem}_{mapper_name}{output_path.suffix}"

    # --- Resume: figure out what's already done ---
    done_ids: set[str] = set()
    if resume:
        done_ids = _load_done_ids(output_file)
        if done_ids:
            logger.info("Resume: %d documents already in %s — skipping them", len(done_ids), output_file)
        vacancies = [v for v in vacancies if str(v.id) not in done_ids]
        if not vacancies:
            logger.info("All vacancies already processed. Nothing to do.")
            return []

    mapper = build_mapper(mapper_name, esco_index, config)

    # --- Decide write mode ---
    write_mode = "a" if resume else "w"

    # --- If no batching requested, run everything at once (original behaviour) ---
    if batch_size <= 0:
        pipeline = Pipeline(mapper, esco_index, config)
        results = pipeline.run(vacancies)
        with open(output_file, write_mode) as f:
            for result in results:
                f.write(json.dumps(dataclasses.asdict(result), ensure_ascii=False) + "\n")
        logger.info("Results written to %s (%d documents)", output_file, len(results))
        return results

    # --- Batched processing with incremental writes ---
    all_results = []
    batches = list(_batched(vacancies, batch_size))
    total_batches = len(batches)

    for batch_num, batch in enumerate(batches, start=1):
        logger.info(
            "=== Vacancy batch %d/%d (%d vacancies) ===",
            batch_num,
            total_batches,
            len(batch),
        )
        pipeline = Pipeline(mapper, esco_index, config)
        results = pipeline.run(batch)

        # Flush this batch to disk immediately
        with open(output_file, "a" if (resume or batch_num > 1) else write_mode) as f:
            for result in results:
                f.write(json.dumps(dataclasses.asdict(result), ensure_ascii=False) + "\n")

        all_results.extend(results)
        logger.info(
            "Batch %d/%d done — %d results flushed (cumulative: %d)",
            batch_num,
            total_batches,
            len(results),
            len(all_results),
        )

    logger.info("All results written to %s (%d documents total)", output_file, len(all_results))
    return all_results


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ESCO Skill Mapping Pipeline")
    parser.add_argument(
        "--source",
        choices=["vacancies", "resumes"],
        default="vacancies",
        help="Data source: vacancies (default) or resumes",
    )
    parser.add_argument(
        "--mapper",
        choices=["fuzzy", "embedding", "llm_direct", "llm_two_stage", "vllm_optimized", "cv_weighted", "all"],
        default="fuzzy",
        help="Mapper to use",
    )
    parser.add_argument("--sample", type=int, default=None, help="Number of vacancies to sample (with shuffle)")
    parser.add_argument("--first", type=int, default=None, help="Take first N vacancies without shuffling")
    parser.add_argument("--output", type=str, default="output/results.jsonl", help="Output JSONL path")
    parser.add_argument(
        "--esco-dir",
        type=str,
        default=None,
        help="Path to ESCO CSV data directory (default: config.esco_data_dir = 'esco')",
    )
    parser.add_argument(
        "--esco-index",
        type=str,
        default=None,
        help="Path to mock ESCO JSON file (uses MockESCOIndex; skips real CSV loading)",
    )

    # --- vLLM / provider overrides ---
    parser.add_argument(
        "--provider",
        choices=["gemini", "vllm"],
        default=None,
        help="LLM provider (overrides LLM_PROVIDER env var)",
    )
    parser.add_argument("--vllm-base-url", type=str, default=None, help="vLLM server base URL")
    parser.add_argument("--vllm-model", type=str, default=None, help="Model name on the vLLM server")

    # --- Batch / resume ---
    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help="Process vacancies in batches of this size (0 = all at once)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Skip vacancies already present in the output file",
    )

    args = parser.parse_args()

    config = Settings()

    # Apply CLI overrides
    if args.sample:
        config.sample_size = args.sample
    if args.first:
        config.select_first = args.first
    if args.provider:
        config.llm_provider = args.provider
    if args.vllm_base_url:
        config.vllm_base_url = args.vllm_base_url
    if args.vllm_model:
        config.vllm_model = args.vllm_model

    # Load ESCO index
    if args.esco_index:
        esco_index = MockESCOIndex(args.esco_index)
    else:
        esco_dir = Path(args.esco_dir) if args.esco_dir else Path(config.esco_data_dir)
        if not esco_dir.exists():
            logger.error("ESCO directory not found: %s", esco_dir)
            sys.exit(1)
        esco_index = ESCOIndex(esco_dir, config.esco_language, config.gemini_api_key, config.cache_dir, config.embedding_title_weight)

    if args.source == "resumes":
        documents = load_resumes(config)
        if not documents:
            logger.error("No resumes loaded.")
            sys.exit(1)
    else:
        documents = load_vacancies(config)
        if not documents:
            logger.error("No vacancies loaded.")
            sys.exit(1)

    output_path = Path(args.output)
    all_mappers = ["fuzzy", "embedding", "llm_direct", "llm_two_stage", "vllm_optimized"]
    if args.source == "resumes":
        all_mappers.append("cv_weighted")
    mapper_names = all_mappers if args.mapper == "all" else [args.mapper]

    for mapper_name in mapper_names:
        logger.info("--- Running mapper: %s ---", mapper_name)
        try:
            run_single(
                mapper_name,
                documents,
                esco_index,
                config,
                output_path,
                resume=args.resume,
                batch_size=args.batch_size,
            )
        except Exception as e:
            logger.error("Mapper %s failed: %s", mapper_name, e, exc_info=True)


if __name__ == "__main__":
    main()
