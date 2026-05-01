"""Ablation study: measure each pipeline stage's contribution."""

import argparse
import dataclasses
import json
import logging
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from esco_pipeline.config import Settings
from esco_pipeline.esco_interface import ESCOIndex
from esco_pipeline.loader import load_resumes, load_vacancies
from esco_pipeline.mappers.base import BaseMapper
from esco_pipeline.models import ESCOMapping
from esco_pipeline.pipeline import Pipeline
from evaluation.intrinsic.intrinsic_metrics import compute_metrics
from evaluation.intrinsic.utils import NoGraphESCOIndex
from scripts.run_pipeline import build_mapper

_log_fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=_log_fmt)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Custom components for ablation configs
# ------------------------------------------------------------------


class NoOpMapper(BaseMapper):
    """Returns None for all skills. name() returns 'llm_two_stage' to trigger LLM extraction."""

    def map_skills(self, skill_strings: list[str]) -> dict[str, ESCOMapping | None]:
        return {s: None for s in skill_strings}

    def name(self) -> str:
        return "llm_two_stage"


class NoRescorePipeline(Pipeline):
    """Pipeline subclass that skips Stage 3 (context-aware rescoring)."""

    def _run_concurrent_rescore(self, vacancy_data, rescore_threshold):
        pass


# ------------------------------------------------------------------
# Config definitions
# ------------------------------------------------------------------

CONFIGS = [
    {
        "name": "stage1_only",
        "description": "Extraction only (no mapping)",
        "mapper": "noop",
        "use_graph": True,
        "pipeline_cls": Pipeline,
    },
    {
        "name": "stage12_no_graph",
        "description": "Mapping without graph enrichment, no rescoring",
        "mapper": "llm_two_stage",
        "use_graph": False,
        "pipeline_cls": NoRescorePipeline,
    },
    {
        "name": "stage12_with_graph",
        "description": "Mapping with graph enrichment, no rescoring",
        "mapper": "llm_two_stage",
        "use_graph": True,
        "pipeline_cls": NoRescorePipeline,
    },
    {
        "name": "full_pipeline",
        "description": "Full pipeline (extraction + mapping + rescoring)",
        "mapper": "llm_two_stage",
        "use_graph": True,
        "pipeline_cls": Pipeline,
    },
]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def compute_consistency_rate(jsonl_path: Path) -> float:
    """For each skill appearing >=2 times, fraction mapping to modal URI, macro-averaged."""
    skill_uris: dict[str, list[str | None]] = {}
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            for m in doc.get("direct_mappings", []) + doc.get("graph_mappings", []):
                skill = m.get("raw_skill")
                uri = m.get("esco_uri")
                if skill:
                    skill_uris.setdefault(skill, []).append(uri)
            for skill in doc.get("unmapped_skills", []):
                skill_uris.setdefault(skill, []).append(None)

    rates = []
    for skill, uris in skill_uris.items():
        if len(uris) < 2:
            continue
        counter = Counter(uris)
        modal_count = counter.most_common(1)[0][1]
        rates.append(modal_count / len(uris))

    return round(float(np.mean(rates)), 4) if rates else 0.0


def compute_extraction_stats(jsonl_path: Path) -> dict:
    """For stage1_only: count skills per doc (all unmapped since NoOpMapper returns None)."""
    counts = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            n = len(doc.get("unmapped_skills", []))
            counts.append(n)

    arr = np.array(counts) if counts else np.array([0])
    return {
        "documents": len(counts),
        "skills_per_doc_mean": round(float(np.mean(arr)), 2),
        "skills_per_doc_median": round(float(np.median(arr)), 2),
        "skills_per_doc_std": round(float(np.std(arr)), 2),
        "total_skills": int(np.sum(arr)),
    }


def run_config(name, mapper, esco_index, pipeline_cls, documents, config, output_dir):
    """Run a single ablation config and write JSONL output."""
    pipeline = pipeline_cls(mapper, esco_index, config)
    results = pipeline.run(documents)

    output_path = output_dir / f"ablation_{name}.jsonl"
    with open(output_path, "w") as f:
        for r in results:
            f.write(json.dumps(dataclasses.asdict(r), ensure_ascii=False) + "\n")

    logger.info("Config '%s': %d documents written to %s", name, len(results), output_path)
    return output_path


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Ablation study for pipeline stages")
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
    logger.info("Loaded %d documents for ablation study", len(documents))

    # Run all configs
    summary = {}
    for cfg in CONFIGS:
        name = cfg["name"]
        logger.info("=" * 60)
        logger.info("Running config: %s — %s", name, cfg["description"])
        logger.info("=" * 60)

        # Build mapper
        if cfg["mapper"] == "noop":
            mapper = NoOpMapper()
        else:
            idx = NoGraphESCOIndex(esco_index) if not cfg["use_graph"] else esco_index
            mapper = build_mapper(cfg["mapper"], idx, config)

        # Choose ESCO index for pipeline
        pipeline_esco = NoGraphESCOIndex(esco_index) if not cfg["use_graph"] else esco_index

        jsonl_path = run_config(
            name, mapper, pipeline_esco, cfg["pipeline_cls"],
            documents, config, output_dir,
        )

        # Compute metrics
        if name == "stage1_only":
            metrics = compute_extraction_stats(jsonl_path)
        else:
            metrics = compute_metrics(str(jsonl_path), args.source)
            metrics["consistency_rate"] = compute_consistency_rate(jsonl_path)

        summary[name] = {
            "description": cfg["description"],
            "metrics": metrics,
        }

    # Write summary
    summary_path = output_dir / "ablation_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    logger.info("Summary written to %s", summary_path)

    # Print comparison table
    print_comparison(summary)


def print_comparison(summary: dict):
    """Print a formatted comparison table to stdout."""
    print("\n" + "=" * 80)
    print("ABLATION STUDY RESULTS")
    print("=" * 80)

    # Stage 1 stats
    s1 = summary.get("stage1_only", {}).get("metrics", {})
    print(f"\n--- Stage 1: Extraction Only ---")
    print(f"  Documents:          {s1.get('documents', 'N/A')}")
    print(f"  Skills/doc (mean):  {s1.get('skills_per_doc_mean', 'N/A')}")
    print(f"  Skills/doc (median):{s1.get('skills_per_doc_median', 'N/A')}")
    print(f"  Skills/doc (std):   {s1.get('skills_per_doc_std', 'N/A')}")
    print(f"  Total skills:       {s1.get('total_skills', 'N/A')}")

    # Mapping configs comparison
    mapping_configs = ["stage12_no_graph", "stage12_with_graph", "full_pipeline"]
    headers = ["Metric", "No Graph", "With Graph", "Full Pipeline"]
    rows = [
        ("Unmapped rate", "unmapped_rate_macro"),
        ("Confidence (mean)", ("confidence", "mean")),
        ("Confidence (median)", ("confidence", "median")),
        ("ESCO breadth", "esco_coverage_breadth"),
        ("Mappings/doc (mean)", ("mappings_per_document", "mean")),
        ("Graph yield", "graph_enrichment_yield"),
        ("Consistency rate", "consistency_rate"),
    ]

    print(f"\n--- Mapping Configs Comparison ---")
    print(f"{'Metric':<25} {'No Graph':>12} {'With Graph':>12} {'Full Pipeline':>14}")
    print("-" * 65)

    for label, key in rows:
        vals = []
        for cfg_name in mapping_configs:
            m = summary.get(cfg_name, {}).get("metrics", {})
            if isinstance(key, tuple):
                v = m.get(key[0], {})
                if isinstance(v, dict):
                    v = v.get(key[1], "N/A")
            else:
                v = m.get(key, "N/A")
            if isinstance(v, float):
                vals.append(f"{v:.4f}")
            else:
                vals.append(str(v))
        print(f"{label:<25} {vals[0]:>12} {vals[1]:>12} {vals[2]:>14}")

    print()


if __name__ == "__main__":
    main()
