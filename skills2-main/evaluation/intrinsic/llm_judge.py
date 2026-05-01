"""LLM-as-Judge evaluation of mapper quality.

Phase 1 (calibrate): compare LLM judge ratings against expert annotations.
Phase 2 (evaluate): rate mappings from 4 baseline mappers at scale, with document context.

Supports both vacancies and resumes via --source flag.

Usage:
    python evaluation/intrinsic/llm_judge.py calibrate \
        --output evaluation/intrinsic/output/llm_judge_calibration.json

    python evaluation/intrinsic/llm_judge.py evaluate \
        --source vacancies \
        --baseline-dir evaluation/intrinsic/output/vacancies/baseline \
        --sample-size 100 \
        --output evaluation/intrinsic/output/llm_judge_vac_results.json

    python evaluation/intrinsic/llm_judge.py evaluate \
        --source resumes \
        --baseline-dir evaluation/intrinsic/output/resumes/baseline \
        --sample-size 100 \
        --output evaluation/intrinsic/output/llm_judge_cv_results.json

    python evaluation/intrinsic/llm_judge.py all \
        --sample-size 100 \
        --output-dir evaluation/intrinsic/output/

Output structure for 'all':
    evaluation/intrinsic/output/llm_judge/
        calibration.json
        vacancies/results.json
        resumes/results.json
"""

import argparse
import json
import logging
import random
import sys
from pathlib import Path

# Allow running as script from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collections import Counter

from esco_pipeline.config import Settings
from esco_pipeline.llm_client import LLMClient
from esco_pipeline.utils import DiskCache, hash_key
from evaluation.processed.compute_metrics import (
    BANDS,
    aggregate_label,
    cohens_kappa,
    expert_columns,
    load_band,
)

logger = logging.getLogger(__name__)

VALID_RATINGS = {"Correct", "Acceptable", "Incorrect"}
CATEGORIES = ["Incorrect", "Acceptable", "Correct"]

MAPPERS = ["fuzzy", "embedding", "llm_direct", "llm_two_stage"]

JUDGE_SYSTEM_MESSAGE = (
    "You are an expert evaluator of skill-to-ESCO taxonomy mappings. "
    "Always respond with valid JSON only, no markdown fences."
)


# ------------------------------------------------------------------
# Prompt builders
# ------------------------------------------------------------------

def build_calibration_prompt(raw_skill: str, esco_label: str) -> str:
    return (
        f"Given an extracted skill mapped to an ESCO taxonomy skill, "
        f"rate the quality of the mapping.\n\n"
        f"Extracted skill: {raw_skill}\n"
        f"ESCO skill: {esco_label}\n\n"
        f"Rate as one of:\n"
        f'- "Correct": The ESCO skill accurately captures the meaning of the extracted skill\n'
        f'- "Acceptable": The ESCO skill is related and reasonable, though not a perfect match\n'
        f'- "Incorrect": The ESCO skill does not match the extracted skill\n\n'
        f'Respond with JSON: {{"rating": "Correct|Acceptable|Incorrect", "reasoning": "..."}}'
    )


def build_evaluation_prompt(
    document_text: str,
    raw_skill: str,
    esco_label: str,
    source: str = "vacancies",
) -> str:
    truncated = document_text[:2000]
    if len(document_text) > 2000:
        truncated += "..."
    source_label = "vacancy" if source == "vacancies" else "resume/CV"
    return (
        f"Given the following {source_label} text and an extracted skill mapped to an ESCO taxonomy skill, "
        f"rate the quality of the mapping.\n\n"
        f"{source_label.capitalize()} text: {truncated}\n\n"
        f"Extracted skill: {raw_skill}\n"
        f"ESCO skill: {esco_label}\n\n"
        f"Rate as one of:\n"
        f'- "Correct": The ESCO skill accurately captures the meaning of the extracted skill in this context\n'
        f'- "Acceptable": The ESCO skill is related and reasonable, though not a perfect match\n'
        f'- "Incorrect": The ESCO skill does not match the extracted skill in this context\n\n'
        f'Respond with JSON: {{"rating": "Correct|Acceptable|Incorrect", "reasoning": "..."}}'
    )


# ------------------------------------------------------------------
# Judge helpers
# ------------------------------------------------------------------

def _parse_rating(result: dict | list | None) -> tuple[str, str]:
    """Extract (rating, reasoning) from LLM response, normalizing the rating."""
    if result is None:
        return "Incorrect", ""
    if isinstance(result, list):
        result = result[0] if result else {}
    if not result:
        return "Incorrect", ""
    rating = str(result.get("rating", "")).strip()
    reasoning = str(result.get("reasoning", "")).strip()
    # Normalize common variations
    for valid in VALID_RATINGS:
        if rating.lower() == valid.lower():
            return valid, reasoning
    return "Incorrect", reasoning  # fallback


def _judge_batch(
    prompts: list[str],
    llm: LLMClient,
    cache: DiskCache,
    cache_prefix: str,
    batch_size: int = 16,
) -> list[tuple[str, str]]:
    """Judge a batch of prompts, using cache and batched LLM calls."""
    results: list[tuple[str, str] | None] = [None] * len(prompts)
    uncached_indices: list[int] = []
    uncached_prompts: list[str] = []

    # Check cache
    for i, prompt in enumerate(prompts):
        key = hash_key(cache_prefix, prompt)
        cached = cache.get(key)
        if cached is not None:
            results[i] = _parse_rating(cached)
        else:
            uncached_indices.append(i)
            uncached_prompts.append(prompt)

    logger.info(
        "Judge batch: %d cached, %d to evaluate",
        len(prompts) - len(uncached_prompts),
        len(uncached_prompts),
    )

    # Process uncached in batches
    for batch_start in range(0, len(uncached_prompts), batch_size):
        batch = uncached_prompts[batch_start : batch_start + batch_size]
        batch_indices = uncached_indices[batch_start : batch_start + batch_size]

        llm_results = llm.generate_json_batch(
            batch,
            max_concurrent=batch_size,
            max_tokens=256,
            system_message=JUDGE_SYSTEM_MESSAGE,
        )

        for j, (parsed, _) in enumerate(llm_results):
            idx = batch_indices[j]
            if not parsed:
                # LLM call failed — don't cache so it gets retried next run
                logger.warning("LLM call returned empty response for prompt %d, not caching", idx)
                results[idx] = ("Incorrect", "")
                continue
            rating, reasoning = _parse_rating(parsed)
            results[idx] = (rating, reasoning)
            cache.set(
                hash_key(cache_prefix, uncached_prompts[batch_start + j]),
                {"rating": rating, "reasoning": reasoning},
            )

        done = min(batch_start + batch_size, len(uncached_prompts))
        logger.info("Judge progress: %d/%d evaluated", done, len(uncached_prompts))

    return [(r if r is not None else ("Incorrect", "")) for r in results]


# ------------------------------------------------------------------
# Phase 1: Calibration
# ------------------------------------------------------------------

def run_calibration(llm: LLMClient, cache: DiskCache) -> dict:
    """Run calibration against expert annotations.

    Expert CSVs are loaded via compute_metrics.load_band() which reads from
    evaluation/processed/ (hardcoded in that module).
    """
    all_items: list[dict] = []  # {raw_skill, esco_label, expert_label, band}
    per_band_items: dict[str, list[dict]] = {}

    for band_name, filename in BANDS:
        rows = load_band(filename)
        band_items = []
        for row in rows:
            cols = expert_columns(row)
            labels = [row[c] for c in cols]
            expert_label = aggregate_label(labels)
            item = {
                "raw_skill": row["raw_skill"],
                "esco_label": row["esco_label"],
                "expert_label": expert_label,
                "band": band_name,
            }
            band_items.append(item)
            all_items.append(item)
        per_band_items[band_name] = band_items

    logger.info("Loaded %d expert annotations across %d bands", len(all_items), len(BANDS))

    if not all_items:
        logger.warning("No expert annotations found — check evaluation/processed/ CSVs")
        return {
            "n_samples": 0,
            "agreement_with_experts": {"strict_accuracy": 0, "lenient_accuracy": 0, "cohens_kappa": 0},
            "confusion_matrix": {},
            "per_band": {},
            "details": [],
        }

    # Build prompts
    prompts = [
        build_calibration_prompt(item["raw_skill"], item["esco_label"])
        for item in all_items
    ]

    # Judge
    judgements = _judge_batch(prompts, llm, cache, cache_prefix="calibration")

    # Compute metrics
    expert_labels = [item["expert_label"] for item in all_items]
    judge_labels = [j[0] for j in judgements]

    strict_acc = sum(1 for e, j in zip(expert_labels, judge_labels) if e == j) / len(all_items)
    lenient_acc = sum(
        1
        for e, j in zip(expert_labels, judge_labels)
        if e == j or {e, j} <= {"Correct", "Acceptable"}
    ) / len(all_items)
    kappa = cohens_kappa(expert_labels, judge_labels, CATEGORIES)

    # Confusion matrix
    confusion: dict[str, int] = Counter()
    for e, j in zip(expert_labels, judge_labels):
        confusion[f"{e}→{j}"] += 1

    # Per-band metrics
    per_band: dict[str, dict] = {}
    offset = 0
    for band_name, filename in BANDS:
        n = len(per_band_items[band_name])
        band_expert = expert_labels[offset : offset + n]
        band_judge = judge_labels[offset : offset + n]
        band_strict = sum(1 for e, j in zip(band_expert, band_judge) if e == j) / n
        band_lenient = sum(
            1
            for e, j in zip(band_expert, band_judge)
            if e == j or {e, j} <= {"Correct", "Acceptable"}
        ) / n
        band_kappa = cohens_kappa(band_expert, band_judge, CATEGORIES)
        per_band[band_name] = {
            "n": n,
            "strict_accuracy": round(band_strict, 4),
            "lenient_accuracy": round(band_lenient, 4),
            "cohens_kappa": round(band_kappa, 4),
        }
        offset += n

    # Details
    details = []
    for item, (rating, reasoning) in zip(all_items, judgements):
        details.append({
            "raw_skill": item["raw_skill"],
            "esco_label": item["esco_label"],
            "band": item["band"],
            "expert": item["expert_label"],
            "judge": rating,
            "reasoning": reasoning,
        })

    result = {
        "n_samples": len(all_items),
        "agreement_with_experts": {
            "strict_accuracy": round(strict_acc, 4),
            "lenient_accuracy": round(lenient_acc, 4),
            "cohens_kappa": round(kappa, 4),
        },
        "confusion_matrix": dict(confusion),
        "per_band": per_band,
        "details": details,
    }

    # Print summary
    print("\n" + "=" * 60)
    print("LLM JUDGE CALIBRATION RESULTS")
    print("=" * 60)
    print(f"  Samples:           {len(all_items)}")
    print(f"  Strict accuracy:   {strict_acc:.1%}")
    print(f"  Lenient accuracy:  {lenient_acc:.1%}")
    print(f"  Cohen's kappa:     {kappa:.3f}")
    print(f"\n  Confusion matrix:")
    for key in sorted(confusion):
        print(f"    {key}: {confusion[key]}")
    print(f"\n  Per-band:")
    for band_name, metrics in per_band.items():
        print(
            f"    {band_name:<10} n={metrics['n']:>3}  "
            f"strict={metrics['strict_accuracy']:.1%}  "
            f"lenient={metrics['lenient_accuracy']:.1%}  "
            f"kappa={metrics['cohens_kappa']:.3f}"
        )

    return result


# ------------------------------------------------------------------
# Phase 2: Scale evaluation
# ------------------------------------------------------------------

def _load_baseline_mappings(baseline_dir: str, mapper: str) -> list[dict]:
    """Load per-mapping items from a baseline JSONL file."""
    path = Path(baseline_dir) / f"baseline_{mapper}.jsonl"
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            doc = json.loads(line)
            doc_id = doc["document_id"]
            for mapping in doc.get("direct_mappings", []) + doc.get("graph_mappings", []):
                items.append({
                    "document_id": doc_id,
                    "raw_skill": mapping["raw_skill"],
                    "esco_uri": mapping.get("esco_uri", ""),
                    "esco_label": mapping.get("esco_label", ""),
                    "confidence": mapping.get("confidence", 0),
                    "method": mapping.get("method", mapper),
                    "mapper": mapper,
                })
    return items


def _load_document_texts(doc_ids: set[str], source: str) -> dict[str, str]:
    """Load document texts from HuggingFace, indexed by document_id.

    Args:
        doc_ids: Set of document IDs to load.
        source: "vacancies" or "resumes".
    """
    config = Settings()
    config.sample_size = None
    config.select_first = None

    if source == "resumes":
        from esco_pipeline.loader import load_resumes
        documents = load_resumes(config)
    else:
        from esco_pipeline.loader import load_vacancies
        documents = load_vacancies(config)

    texts = {}
    for doc in documents:
        if doc.id in doc_ids:
            parts = []
            if doc.title:
                parts.append(doc.title)
            if doc.description_text:
                parts.append(doc.description_text)
            texts[doc.id] = "\n\n".join(parts)
    return texts


def run_evaluation(
    baseline_dir: str,
    llm: LLMClient,
    cache: DiskCache,
    sample_size: int = 100,
    seed: int = 42,
    source: str = "vacancies",
) -> dict:
    """Run scale evaluation across all baseline mappers.

    Args:
        source: "vacancies" or "resumes" — determines which dataset to load for context.
    """
    rng = random.Random(seed)

    all_sampled: list[dict] = []
    for mapper in MAPPERS:
        try:
            items = _load_baseline_mappings(baseline_dir, mapper)
        except FileNotFoundError:
            logger.warning("Baseline file not found for mapper %s, skipping", mapper)
            continue
        sampled = rng.sample(items, min(sample_size, len(items)))
        all_sampled.extend(sampled)
        logger.info("Sampled %d mappings from %s (total available: %d)", len(sampled), mapper, len(items))

    if not all_sampled:
        logger.warning("No baseline mappings sampled — check baseline dir: %s", baseline_dir)
        return {
            "source": source,
            "sample_size_per_mapper": sample_size,
            "seed": seed,
            "results": {},
            "details": [],
        }

    # Collect doc IDs and load document texts
    doc_ids = {item["document_id"] for item in all_sampled}
    logger.info("Loading %s texts for %d unique documents...", source, len(doc_ids))
    doc_texts = _load_document_texts(doc_ids, source)
    logger.info("Loaded %d document texts", len(doc_texts))

    # Build prompts
    prompts = []
    for item in all_sampled:
        text = doc_texts.get(item["document_id"], "")
        if text:
            prompt = build_evaluation_prompt(text, item["raw_skill"], item["esco_label"], source)
        else:
            # Fallback to no-context prompt if document text unavailable
            prompt = build_calibration_prompt(item["raw_skill"], item["esco_label"])
        prompts.append(prompt)

    # Judge
    cache_prefix = f"evaluation_{source}"
    judgements = _judge_batch(prompts, llm, cache, cache_prefix=cache_prefix)

    # Aggregate per mapper
    mapper_results: dict[str, dict] = {}
    mapper_details: dict[str, list] = {m: [] for m in MAPPERS}

    for item, (rating, reasoning) in zip(all_sampled, judgements):
        mapper_details[item["mapper"]].append({
            "mapper": item["mapper"],
            "document_id": item["document_id"],
            "raw_skill": item["raw_skill"],
            "esco_label": item["esco_label"],
            "judge": rating,
            "reasoning": reasoning,
        })

    for mapper in MAPPERS:
        details = mapper_details[mapper]
        if not details:
            continue
        n = len(details)
        ratings = [d["judge"] for d in details]
        strict = sum(1 for r in ratings if r == "Correct") / n
        lenient = sum(1 for r in ratings if r in ("Correct", "Acceptable")) / n
        incorrect = sum(1 for r in ratings if r == "Incorrect") / n
        mapper_results[mapper] = {
            "strict_accuracy": round(strict, 4),
            "lenient_accuracy": round(lenient, 4),
            "incorrect_rate": round(incorrect, 4),
            "n_judged": n,
            "distribution": dict(Counter(ratings)),
        }

    # Flatten details
    all_details = []
    for mapper in MAPPERS:
        all_details.extend(mapper_details[mapper])

    result = {
        "source": source,
        "sample_size_per_mapper": sample_size,
        "seed": seed,
        "results": mapper_results,
        "details": all_details,
    }

    # Print summary
    source_label = "VACANCIES" if source == "vacancies" else "RESUMES"
    print("\n" + "=" * 60)
    print(f"LLM JUDGE EVALUATION RESULTS — {source_label}")
    print("=" * 60)
    print(f"  Source: {source}")
    print(f"  Sample size per mapper: {sample_size}")
    print(f"  Seed: {seed}")
    print(f"\n  {'Mapper':<16} {'N':>4} {'Strict':>8} {'Lenient':>8} {'Incorrect':>10}")
    print("  " + "-" * 48)
    for mapper in MAPPERS:
        if mapper in mapper_results:
            m = mapper_results[mapper]
            print(
                f"  {mapper:<16} {m['n_judged']:>4} "
                f"{m['strict_accuracy']:>7.1%} "
                f"{m['lenient_accuracy']:>7.1%} "
                f"{m['incorrect_rate']:>9.1%}"
            )

    return result


# ------------------------------------------------------------------
# Combined quality × coverage summary
# ------------------------------------------------------------------

def print_combined_summary(output_dir: str, source: str) -> dict | None:
    """Compute and print combined quality × coverage metrics.

    Reads existing baseline_summary.json and llm_judge results — no LLM calls.
    """
    output_path = Path(output_dir)
    baseline_path = output_path / source / "baseline" / "baseline_summary.json"
    judge_path = output_path / "llm_judge" / source / "results.json"

    if not baseline_path.exists():
        logger.warning("Baseline summary not found: %s", baseline_path)
        return None
    if not judge_path.exists():
        logger.warning("LLM judge results not found: %s", judge_path)
        return None

    with open(baseline_path, encoding="utf-8") as f:
        baseline = json.load(f)
    with open(judge_path, encoding="utf-8") as f:
        judge = json.load(f)

    judge_results = judge.get("results", {})
    combined: dict[str, dict] = {}

    for mapper in MAPPERS:
        if mapper not in baseline or mapper not in judge_results:
            continue
        metrics = baseline[mapper]["metrics"]
        mappings_per_doc = metrics["mappings_per_document"]["mean"]
        unmapped_rate = metrics.get("unmapped_rate_macro", 0)
        strict = judge_results[mapper]["strict_accuracy"]
        lenient = judge_results[mapper]["lenient_accuracy"]

        combined[mapper] = {
            "mappings_per_doc": round(mappings_per_doc, 2),
            "unmapped_rate": round(unmapped_rate, 4),
            "strict_accuracy": strict,
            "lenient_accuracy": lenient,
            "effective_correct_per_doc": round(mappings_per_doc * strict, 2),
            "effective_acceptable_per_doc": round(mappings_per_doc * lenient, 2),
        }

    if not combined:
        logger.warning("No mappers found in both baseline and judge data for %s", source)
        return None

    # Print table
    source_label = source.upper()
    print("\n" + "=" * 90)
    print(f"COMBINED QUALITY × COVERAGE — {source_label}")
    print("=" * 90)
    header = (
        f"  {'Mapper':<16} {'Map/doc':>8} {'Strict':>8} {'Lenient':>8} "
        f"{'Eff.Corr/doc':>13} {'Eff.Acc/doc':>12} {'Unmapped':>9}"
    )
    print(header)
    print("  " + "-" * 76)
    for mapper in MAPPERS:
        if mapper not in combined:
            continue
        m = combined[mapper]
        print(
            f"  {mapper:<16} {m['mappings_per_doc']:>8.1f} "
            f"{m['strict_accuracy']:>7.1%} "
            f"{m['lenient_accuracy']:>7.1%} "
            f"{m['effective_correct_per_doc']:>13.1f} "
            f"{m['effective_acceptable_per_doc']:>12.1f} "
            f"{m['unmapped_rate']:>8.1%}"
        )

    result = {
        "source": source,
        "mappers": combined,
    }

    # Save JSON
    out_path = output_path / "llm_judge" / source / "combined_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved to {out_path}")

    return result


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="LLM-as-Judge evaluation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Calibrate
    p_cal = subparsers.add_parser("calibrate", help="Calibrate LLM judge against expert annotations")
    p_cal.add_argument("--output", default="evaluation/intrinsic/output/llm_judge_calibration.json")

    # Evaluate
    p_eval = subparsers.add_parser("evaluate", help="Evaluate baseline mappers with LLM judge")
    p_eval.add_argument("--source", choices=["vacancies", "resumes"], default="vacancies",
                        help="Data source: vacancies (default) or resumes")
    p_eval.add_argument("--baseline-dir", default=None,
                        help="Baseline dir (default: evaluation/intrinsic/output/{source}/baseline)")
    p_eval.add_argument("--sample-size", type=int, default=100)
    p_eval.add_argument("--seed", type=int, default=42)
    p_eval.add_argument("--output", default=None,
                        help="Output path (default: evaluation/intrinsic/output/llm_judge/{source}/results.json)")

    # All
    p_all = subparsers.add_parser("all", help="Calibrate + evaluate both vacancies and resumes")
    p_all.add_argument("--sample-size", type=int, default=100)
    p_all.add_argument("--seed", type=int, default=42)
    p_all.add_argument("--output-dir", default="evaluation/intrinsic/output/")

    # Summary
    p_sum = subparsers.add_parser("summary", help="Print combined quality × coverage summary from existing data")
    p_sum.add_argument("--source", choices=["vacancies", "resumes"], default=None,
                       help="Source to summarize (default: both)")
    p_sum.add_argument("--output-dir", default="evaluation/intrinsic/output/")

    args = parser.parse_args()

    # Only initialize LLM/cache for commands that need them
    llm = None
    cache = None
    if args.command in ("calibrate", "evaluate", "all"):
        config = Settings()
        llm = LLMClient(config)
        cache = DiskCache(Path(config.cache_dir) / "llm_judge")

    if args.command == "calibrate":
        result = run_calibration(llm, cache)
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nSaved calibration results to {out}")

    elif args.command == "evaluate":
        source = args.source
        baseline_dir = args.baseline_dir or f"evaluation/intrinsic/output/{source}/baseline"
        output = args.output or f"evaluation/intrinsic/output/llm_judge/{source}/results.json"
        result = run_evaluation(baseline_dir, llm, cache, args.sample_size, args.seed, source)
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nSaved evaluation results to {out}")

    elif args.command == "all":
        output_dir = Path(args.output_dir)

        # Phase 1: Calibration
        cal_out_dir = output_dir / "llm_judge"
        cal_out_dir.mkdir(parents=True, exist_ok=True)
        cal_result = run_calibration(llm, cache)
        cal_out = cal_out_dir / "calibration.json"
        with open(cal_out, "w", encoding="utf-8") as f:
            json.dump(cal_result, f, ensure_ascii=False, indent=2)
        print(f"\nSaved calibration results to {cal_out}")

        # Phase 2: Evaluate both sources
        for source in ("vacancies", "resumes"):
            baseline_dir = f"evaluation/intrinsic/output/{source}/baseline"
            if not Path(baseline_dir).exists():
                logger.warning("Baseline dir %s not found, skipping %s", baseline_dir, source)
                continue
            eval_out_dir = output_dir / "llm_judge" / source
            eval_out_dir.mkdir(parents=True, exist_ok=True)
            eval_result = run_evaluation(
                baseline_dir, llm, cache, args.sample_size, args.seed, source,
            )
            eval_out = eval_out_dir / "results.json"
            with open(eval_out, "w", encoding="utf-8") as f:
                json.dump(eval_result, f, ensure_ascii=False, indent=2)
            print(f"\nSaved {source} evaluation results to {eval_out}")

        # Combined summary for each source
        for source in ("vacancies", "resumes"):
            print_combined_summary(str(output_dir), source)

    elif args.command == "summary":
        sources = [args.source] if args.source else ["vacancies", "resumes"]
        for source in sources:
            print_combined_summary(args.output_dir, source)


if __name__ == "__main__":
    main()
