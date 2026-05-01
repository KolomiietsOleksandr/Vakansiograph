"""Baseline comparison: compare alternative mapping strategies against the full pipeline."""

import argparse
import dataclasses
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from esco_pipeline.config import Settings
from esco_pipeline.esco_interface import ESCOIndex
from esco_pipeline.loader import load_resumes, load_vacancies
from esco_pipeline.pipeline import Pipeline
from evaluation.intrinsic.ablation import compute_consistency_rate
from evaluation.intrinsic.intrinsic_metrics import compute_metrics
from scripts.run_pipeline import build_mapper

_log_fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=_log_fmt)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Mapper configs
# ------------------------------------------------------------------

CONFIGS = [
    {"name": "fuzzy",         "mapper": "fuzzy"},
    {"name": "embedding",     "mapper": "embedding"},
    {"name": "llm_direct",    "mapper": "llm_direct"},
    {"name": "llm_two_stage", "mapper": "llm_two_stage"},
]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def run_config(name, mapper, esco_index, documents, config, output_dir):
    """Run a single baseline config and write JSONL output."""
    pipeline = Pipeline(mapper, esco_index, config)
    results = pipeline.run(documents)

    output_path = output_dir / f"baseline_{name}.jsonl"
    with open(output_path, "w") as f:
        for r in results:
            f.write(json.dumps(dataclasses.asdict(r), ensure_ascii=False) + "\n")

    logger.info("Config '%s': %d documents written to %s", name, len(results), output_path)
    return output_path


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Baseline comparison of mapping strategies")
    parser.add_argument(
        "--source", choices=["vacancies", "resumes"], default="vacancies",
        help="Data source",
    )
    parser.add_argument("--sample", type=int, default=50, help="Number of documents to sample")
    parser.add_argument("--esco-dir", type=str, default="esco", help="ESCO data directory")
    parser.add_argument("--output", type=str, default="evaluation/intrinsic/output/", help="Output directory")
    parser.add_argument(
        "--provider", choices=["gemini", "vllm"], default=None,
        help="LLM provider override",
    )
    parser.add_argument("--vllm-base-url", type=str, default=None)
    parser.add_argument("--vllm-model", type=str, default=None)
    parser.add_argument("--resume", action="store_true", help="Skip configs whose JSONL already has the expected number of lines")
    args = parser.parse_args()

    # Setup config
    config = Settings()
    config.sample_size = args.sample
    config.random_seed = 42
    if args.provider:
        config.llm_provider = args.provider
    if args.vllm_base_url:
        config.vllm_base_url = args.vllm_base_url
    if args.vllm_model:
        config.vllm_model = args.vllm_model

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load ESCO index
    esco_dir = Path(args.esco_dir)
    if not esco_dir.exists():
        logger.error("ESCO directory not found: %s", esco_dir)
        sys.exit(1)
    esco_index = ESCOIndex(
        esco_dir, config.esco_language, config.gemini_api_key,
        config.cache_dir, config.embedding_title_weight,
    )

    # Load documents once
    if args.source == "resumes":
        documents = load_resumes(config)
    else:
        documents = load_vacancies(config)
    if not documents:
        logger.error("No documents loaded.")
        sys.exit(1)
    logger.info("Loaded %d documents for baseline comparison", len(documents))

    # Run all configs
    summary = {}
    for cfg in CONFIGS:
        name = cfg["name"]
        logger.info("=" * 60)
        logger.info("Running mapper: %s", name)
        logger.info("=" * 60)

        jsonl_path = output_dir / f"baseline_{name}.jsonl"

        # --resume: skip configs whose JSONL already has the expected number of lines
        if args.resume and jsonl_path.exists():
            line_count = sum(1 for _ in open(jsonl_path))
            if line_count == args.sample:
                logger.info("Skipping '%s': %s already has %d lines", name, jsonl_path, line_count)
                metrics = compute_metrics(str(jsonl_path), args.source)
                metrics["consistency_rate"] = compute_consistency_rate(jsonl_path)
                summary[name] = {"metrics": metrics}
                continue

        mapper = build_mapper(cfg["mapper"], esco_index, config)

        jsonl_path = run_config(
            name, mapper, esco_index, documents, config, output_dir,
        )

        metrics = compute_metrics(str(jsonl_path), args.source)
        metrics["consistency_rate"] = compute_consistency_rate(jsonl_path)

        summary[name] = {"metrics": metrics}

    # Write summary JSON
    summary_path = output_dir / "baseline_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    logger.info("Summary written to %s", summary_path)

    # Write comparison CSV
    rows = []
    for cfg in CONFIGS:
        name = cfg["name"]
        m = summary[name]["metrics"]
        rows.append({
            "mapper": name,
            "unmapped_rate_macro": m.get("unmapped_rate_macro", 0),
            "confidence_mean": m.get("confidence", {}).get("mean", 0),
            "confidence_median": m.get("confidence", {}).get("median", 0),
            "esco_coverage_breadth": m.get("esco_coverage_breadth", 0),
            "mappings_per_doc_mean": m.get("mappings_per_document", {}).get("mean", 0),
            "graph_enrichment_yield": m.get("graph_enrichment_yield", 0),
            "consistency_rate": m.get("consistency_rate", 0),
        })

    df = pd.DataFrame(rows)
    csv_path = output_dir / "baseline_comparison.csv"
    df.to_csv(csv_path, index=False)
    logger.info("CSV written to %s", csv_path)

    # Print comparison table
    print_comparison(summary)


def print_comparison(summary: dict):
    """Print a formatted comparison table to stdout."""
    print("\n" + "=" * 80)
    print("BASELINE COMPARISON RESULTS")
    print("=" * 80)

    mapper_names = ["fuzzy", "embedding", "llm_direct", "llm_two_stage"]
    metric_rows = [
        ("Unmapped rate", "unmapped_rate_macro"),
        ("Confidence (mean)", ("confidence", "mean")),
        ("Confidence (median)", ("confidence", "median")),
        ("ESCO breadth", "esco_coverage_breadth"),
        ("Mappings/doc (mean)", ("mappings_per_document", "mean")),
        ("Graph yield", "graph_enrichment_yield"),
        ("Consistency rate", "consistency_rate"),
    ]

    header = f"{'Metric':<25}"
    for name in mapper_names:
        header += f" {name:>14}"
    print(f"\n{header}")
    print("-" * (25 + 15 * len(mapper_names)))

    for label, key in metric_rows:
        line = f"{label:<25}"
        for name in mapper_names:
            m = summary.get(name, {}).get("metrics", {})
            if isinstance(key, tuple):
                v = m.get(key[0], {})
                if isinstance(v, dict):
                    v = v.get(key[1], "N/A")
            else:
                v = m.get(key, "N/A")
            if isinstance(v, float):
                line += f" {v:>14.4f}"
            else:
                line += f" {str(v):>14}"
        print(line)

    print()


if __name__ == "__main__":
    main()
