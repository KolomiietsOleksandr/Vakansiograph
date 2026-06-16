import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("eval_llm")

DEFAULT_DATASET = Path("tests/golden/mapping_dataset.json")
DEFAULT_REPORT = Path("output/eval_report.json")


@dataclass
class EntryResult:
    id: str
    raw_skill: str
    expected_label: str | None
    expected_uri: str | None
    returned_uri: str | None
    returned_label: str | None
    returned_confidence: float | None
    matched: bool          # True if correct mapping (or correctly unmapped)
    hallucinated: bool     # True if returned_uri is not None but doesn't exist in ESCO
    label_score: float     # rapidfuzz similarity between returned and expected label


@dataclass
class EvalReport:
    dataset_version: str
    esco_version: str
    model: str
    timestamp: str
    total: int
    mapping_rate: float
    precision_at_1: float
    avg_confidence: float
    min_confidence: float
    hallucination_rate: float
    thresholds: dict
    threshold_ok: bool
    failures: list[str]    # threshold names that failed
    per_entry: list[dict]


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _label_similarity(a: str, b: str) -> float:
    from rapidfuzz import fuzz
    return fuzz.token_sort_ratio(a.lower(), b.lower()) / 100.0


def _init_mapper():
    # Locate the ESCO CSV directory the same way esco_enricher_v2 does.
    from app.services.esco_enricher_v2 import _BASE_DIR
    esco_dir = _BASE_DIR / "ESCO dataset - v1.2.1 - classification - en - csv"
    if not esco_dir.exists():
        raise RuntimeError(
            f"ESCO data directory not found: {esco_dir}. "
            "Download ESCO v1.2.1 CSV files and place them in the project root."
        )

    logger.info("Initialising ESCO enricher (this may take 10-30s on first run)…")
    import app.services.esco_enricher_v2 as enricher
    enricher._init()
    return enricher.map_skills, enricher._esco_index


def _load_dataset(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _init_llm_mapper():
    """Initialise LLMMapper directly — bypasses the fuzzy/embedding pre-filter gates.
    Used by --llm-only mode so we test the LLM's decision-making, not the full pipeline."""
    import os
    import app.services.esco_enricher_v2 as enricher
    enricher._init()  # loads ESCO index, fuzzy, embedding, llm mappers into module globals

    if enricher._llm_mapper is None:
        raise RuntimeError("LLM mapper not initialised — check GEMINI_API_KEY is set")

    llm_mapper = enricher._llm_mapper
    esco_index = enricher._esco_index

    def _map_via_llm_only(skill_strings: list[str]) -> dict[str, dict | None]:
        raw_results = llm_mapper.map_skills(skill_strings)
        out: dict[str, dict | None] = {}
        for skill, mapping in raw_results.items():
            if mapping is None:
                out[skill] = None
            else:
                skill_obj = esco_index.get_skill(mapping.esco_uri)
                out[skill] = {
                    "esco_uri": mapping.esco_uri,
                    "esco_label": mapping.esco_label,
                    "confidence": mapping.confidence,
                    "method": mapping.method,
                    "esco_type": skill_obj.skill_type if skill_obj else "",
                }
        return out

    return _map_via_llm_only, esco_index


def _filter_entries(
    entries: list[dict],
    category: str | None,
    skip_edges: bool,
    llm_only: bool = False,
) -> list[dict]:
    result = entries
    if llm_only:
        result = [e for e in result if e.get("llm_only") is True]
    if skip_edges:
        result = [e for e in result if e.get("category") != "edge"]
    if category:
        result = [e for e in result if e.get("category") == category]
    return result


# ──────────────────────────────────────────────
# Core evaluation
# ──────────────────────────────────────────────

def evaluate(
    map_skills_fn,
    esco_index,
    entries: list[dict],
    label_match_threshold: float,
) -> list[EntryResult]:
    raw_skills = [e["raw_skill"] for e in entries]

    logger.info("Running map_skills on %d entries…", len(raw_skills))
    t0 = time.time()
    mappings: dict[str, dict | None] = map_skills_fn(raw_skills)
    elapsed = time.time() - t0
    logger.info("Mapping done in %.1fs", elapsed)

    results: list[EntryResult] = []
    for entry in entries:
        raw = entry["raw_skill"]
        expected_label = entry.get("expected_label")
        expected_uri = entry.get("expected_uri")
        mapping = mappings.get(raw)

        returned_uri = mapping["esco_uri"] if mapping else None
        returned_label = mapping["esco_label"] if mapping else None
        returned_conf = mapping["confidence"] if mapping else None

        hallucinated = (
            returned_uri is not None
            and not esco_index.uri_exists(returned_uri)
        )

        label_score = 0.0
        if returned_label and expected_label:
            label_score = _label_similarity(returned_label, expected_label)

        # Correctness
        if expected_label is None:
            # Edge case that should NOT map
            matched = (returned_uri is None)
        elif expected_uri:
            # Exact URI match is available
            matched = (returned_uri == expected_uri)
        else:
            # Label-fuzzy mode
            matched = label_score >= label_match_threshold

        results.append(EntryResult(
            id=entry["id"],
            raw_skill=raw,
            expected_label=expected_label,
            expected_uri=expected_uri,
            returned_uri=returned_uri,
            returned_label=returned_label,
            returned_confidence=returned_conf,
            matched=matched,
            hallucinated=hallucinated,
            label_score=round(label_score, 3),
        ))

    return results


# ──────────────────────────────────────────────
# Metrics
# ──────────────────────────────────────────────

def compute_report(
    results: list[EntryResult],
    dataset: dict,
    model: str,
) -> EvalReport:
    import datetime

    thresholds = dataset.get("thresholds", {})
    min_p1 = thresholds.get("min_precision_at_1", 0.70)
    min_mr = thresholds.get("min_mapping_rate", 0.75)
    max_hr = thresholds.get("max_hallucination_rate", 0.05)
    min_conf = thresholds.get("min_avg_confidence", 0.55)
    label_thr = thresholds.get("label_match_ratio", 80) / 100.0

    n = len(results)

    should_map = [r for r in results if r.expected_label is not None]
    should_not_map = [r for r in results if r.expected_label is None]

    mapped = [r for r in should_map if r.returned_uri is not None]
    mapping_rate = len(mapped) / len(should_map) if should_map else 0.0
    precision_at_1 = sum(1 for r in results if r.matched) / n if n else 0.0

    conf_values = [r.returned_confidence for r in results if r.returned_confidence is not None]
    avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0.0
    min_conf_actual = min(conf_values) if conf_values else 0.0

    hallucinated_count = sum(1 for r in results if r.hallucinated)
    hal_rate = hallucinated_count / n if n else 0.0

    failures = []
    if precision_at_1 < min_p1:
        failures.append(f"precision_at_1={precision_at_1:.3f} < {min_p1}")
    if mapping_rate < min_mr:
        failures.append(f"mapping_rate={mapping_rate:.3f} < {min_mr}")
    if hal_rate > max_hr:
        failures.append(f"hallucination_rate={hal_rate:.3f} > {max_hr}")
    if avg_conf < min_conf and conf_values:
        failures.append(f"avg_confidence={avg_conf:.3f} < {min_conf}")

    return EvalReport(
        dataset_version=dataset.get("version", "?"),
        esco_version=dataset.get("esco_version", "?"),
        model=model,
        timestamp=datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        total=n,
        mapping_rate=round(mapping_rate, 4),
        precision_at_1=round(precision_at_1, 4),
        avg_confidence=round(avg_conf, 4),
        min_confidence=round(min_conf_actual, 4),
        hallucination_rate=round(hal_rate, 4),
        thresholds=thresholds,
        threshold_ok=len(failures) == 0,
        failures=failures,
        per_entry=[asdict(r) for r in results],
    )


# ──────────────────────────────────────────────
# Printing
# ──────────────────────────────────────────────

def print_report(report: EvalReport) -> None:
    ok = "PASS" if report.threshold_ok else "FAIL"
    print(f"\n{'='*65}")
    print(f"  LLM EVAL REPORT  [{ok}]  model={report.model}")
    print(f"  dataset v{report.dataset_version} | ESCO {report.esco_version} | {report.timestamp}")
    print(f"{'='*65}")
    print(f"  Total entries      : {report.total}")
    print(f"  Mapping rate       : {report.mapping_rate:.1%}  (threshold ≥ {report.thresholds.get('min_mapping_rate', '?'):.0%})")
    print(f"  Precision@1        : {report.precision_at_1:.1%}  (threshold ≥ {report.thresholds.get('min_precision_at_1', '?'):.0%})")
    print(f"  Avg confidence     : {report.avg_confidence:.3f}  (threshold ≥ {report.thresholds.get('min_avg_confidence', '?')})")
    print(f"  Min confidence     : {report.min_confidence:.3f}")
    print(f"  Hallucination rate : {report.hallucination_rate:.1%}  (threshold ≤ {report.thresholds.get('max_hallucination_rate', '?'):.0%})")
    print(f"{'='*65}")

    if report.failures:
        print("  THRESHOLD BREACHES:")
        for f in report.failures:
            print(f"    ✗  {f}")
        print()

    misses = [r for r in report.per_entry if not r["matched"]]
    if misses:
        print(f"  INCORRECT MAPPINGS ({len(misses)}):")
        for r in misses:
            exp = r["expected_label"] or "(should be unmapped)"
            got = r["returned_label"] or "(unmapped)"
            hal = " [HALLUCINATED URI]" if r["hallucinated"] else ""
            print(f"    [{r['id']}] {r['raw_skill']!r}")
            print(f"           expected : {exp}")
            print(f"           got      : {got}  conf={r['returned_confidence']}{hal}")
    print()


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LLM golden-dataset regression eval")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--ci", action="store_true", help="Exit 1 if thresholds breached")
    parser.add_argument("--category", default=None)
    parser.add_argument("--skip-edges", action="store_true")
    parser.add_argument(
        "--llm-only", action="store_true",
        help="Test only llm_only=true entries by calling LLMMapper directly (bypasses fuzzy/embedding gates)",
    )
    args = parser.parse_args()

    if not args.dataset.exists():
        logger.error("Dataset not found: %s", args.dataset)
        sys.exit(2)

    dataset = _load_dataset(args.dataset)
    llm_only = getattr(args, "llm_only", False)
    entries = _filter_entries(
        dataset["entries"],
        category=args.category,
        skip_edges=args.skip_edges,
        llm_only=llm_only,
    )
    logger.info("Loaded %d entries (after filters, llm_only=%s)", len(entries), llm_only)

    if llm_only:
        map_skills_fn, esco_index = _init_llm_mapper()
        logger.info("Mode: LLM-direct (bypassing fuzzy/embedding pre-filters)")
    else:
        map_skills_fn, esco_index = _init_mapper()

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    label_threshold = dataset.get("thresholds", {}).get("label_match_ratio", 80) / 100.0

    results = evaluate(map_skills_fn, esco_index, entries, label_threshold)
    report = compute_report(results, dataset, model=model)
    print_report(report)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    with open(args.report, "w") as f:
        json.dump(asdict(report), f, indent=2)
    logger.info("Report written to %s", args.report)

    if args.ci and not report.threshold_ok:
        logger.error("CI mode: thresholds breached — exiting with code 1")
        sys.exit(1)


if __name__ == "__main__":
    main()
