"""Generate LaTeX table fragments from evaluation JSON outputs.

Usage:
    python evaluation/intrinsic/format_results.py --help
    python evaluation/intrinsic/format_results.py \\
        --intrinsic-vac evaluation/intrinsic/output/vac_intrinsic.json \\
        --intrinsic-cv evaluation/intrinsic/output/cv_intrinsic.json \\
        --output evaluation/intrinsic/output/tables/
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_pct(val: float) -> str:
    """Format a 0-1 fraction as percentage with 1 decimal, e.g. '95.2\\%'."""
    return f"{val * 100:.1f}\\%"


def fmt_float(val: float, decimals: int = 3) -> str:
    return f"{val:.{decimals}f}"


def fmt_int(val: int) -> str:
    """Format integer with LaTeX-safe comma grouping, e.g. '8{,}176'."""
    s = f"{val:,}"
    return s.replace(",", "{,}")


def bold(val: str) -> str:
    return f"\\textbf{{{val}}}"


def write_table(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"=== {path.name} ===")
    print(content)
    print()


# ---------------------------------------------------------------------------
# Table 1: Intrinsic Metrics Summary
# ---------------------------------------------------------------------------

def table_intrinsic(vac: dict, cv: dict) -> str:
    rows = [
        ("Documents", fmt_int(vac["documents"]), fmt_int(cv["documents"])),
        ("Unmapped rate", fmt_pct(vac["unmapped_rate_macro"]), fmt_pct(cv["unmapped_rate_macro"])),
        ("Mean confidence", fmt_float(vac["confidence"]["mean"]), fmt_float(cv["confidence"]["mean"])),
        ("Median confidence", fmt_float(vac["confidence"]["median"]), fmt_float(cv["confidence"]["median"])),
        ("Skills per document", fmt_float(vac["skills_per_document"]["mean"], 1), fmt_float(cv["skills_per_document"]["mean"], 1)),
        ("Mappings per document", fmt_float(vac["mappings_per_document"]["mean"], 1), fmt_float(cv["mappings_per_document"]["mean"], 1)),
        ("Distinct ESCO URIs", fmt_int(vac["esco_coverage_breadth"]), fmt_int(cv["esco_coverage_breadth"])),
        ("Graph enrichment yield", fmt_pct(vac["graph_enrichment_yield"]), fmt_pct(cv["graph_enrichment_yield"])),
    ]
    body = " \\\\\n".join(f"  {metric} & {v} & {c}" for metric, v, c in rows)
    return _wrap_table(
        "lrr",
        "Metric & Vacancies & Resumes",
        body,
        "Intrinsic evaluation metrics for vacancies and resumes.",
        "tab:intrinsic",
    )


# ---------------------------------------------------------------------------
# Table 2: Confidence Distribution
# ---------------------------------------------------------------------------

CONF_BUCKETS = ["0.0-0.5", "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"]


def table_confidence(vac: dict, cv: dict) -> str:
    vac_b = vac["confidence"]["buckets"]
    cv_b = cv["confidence"]["buckets"]
    vac_total = sum(vac_b.values())
    cv_total = sum(cv_b.values())

    rows = []
    for bucket in CONF_BUCKETS:
        vp = vac_b.get(bucket, 0) / vac_total if vac_total else 0
        cp = cv_b.get(bucket, 0) / cv_total if cv_total else 0
        rows.append(f"  {bucket} & {fmt_pct(vp)} & {fmt_pct(cp)}")

    body = " \\\\\n".join(rows)
    return _wrap_table(
        "lrr",
        "Confidence range & Vacancies & Resumes",
        body,
        "Distribution of mapping confidence scores.",
        "tab:confidence",
    )


# ---------------------------------------------------------------------------
# Table 3: Consistency Analysis
# ---------------------------------------------------------------------------

HIST_KEYS = ["100%", "90-99%", "80-89%", "70-79%", "60-69%", "50-59%", "<50%"]


def table_consistency(vac: dict, cv: dict) -> str:
    metric_rows = [
        ("Total unique skills", fmt_int(vac["total_unique_skills"]), fmt_int(cv["total_unique_skills"])),
        ("Qualifying skills ($\\geq 5$ occ.)", fmt_int(vac["qualifying_skills"]), fmt_int(cv["qualifying_skills"])),
        ("Macro-avg consistency", fmt_float(vac["macro_avg_consistency"]), fmt_float(cv["macro_avg_consistency"])),
        ("Polysemy count", fmt_int(vac["polysemy_count"]), fmt_int(cv["polysemy_count"])),
        ("Instability count", fmt_int(vac["instability_count"]), fmt_int(cv["instability_count"])),
    ]
    lines = [f"  {m} & {v} & {c}" for m, v, c in metric_rows]

    # Histogram rows
    hist_lines = []
    for key in HIST_KEYS:
        vc = vac["histogram"].get(key, 0)
        cc = cv["histogram"].get(key, 0)
        hist_lines.append(f"  Consistency {key} & {fmt_int(vc)} & {fmt_int(cc)}")

    body = " \\\\\n".join(lines) + " \\\\\n    \\midrule\n" + " \\\\\n".join(hist_lines)
    return _wrap_table(
        "lrr",
        "Metric & Vacancies & Resumes",
        body,
        "Mapping consistency analysis.",
        "tab:consistency",
    )


# ---------------------------------------------------------------------------
# Table 4: Ablation Study
# ---------------------------------------------------------------------------

ABLATION_CONFIGS = [
    ("stage1_only", "Stage 1 only"),
    ("stage12_no_graph", "Stage 1+2 (no graph)"),
    ("stage12_with_graph", "Stage 1+2 (with graph)"),
    ("full_pipeline", "Full pipeline"),
]


def table_ablation(data: dict, source: str) -> str:
    # Collect values for bolding best
    cols = {
        "skills": [],
        "unmapped": [],
        "confidence": [],
        "graph": [],
        "consistency": [],
    }
    parsed = []
    for key, label in ABLATION_CONFIGS:
        m = data[key]["metrics"]
        if key == "stage1_only":
            row = {
                "label": label,
                "skills": m.get("skills_per_doc_mean", m.get("skills_per_document", {}).get("mean")),
                "unmapped": None,
                "confidence": None,
                "graph": None,
                "consistency": None,
            }
        else:
            row = {
                "label": label,
                "skills": m.get("skills_per_document", {}).get("mean"),
                "unmapped": m.get("unmapped_rate_macro"),
                "confidence": m.get("confidence", {}).get("mean"),
                "graph": m.get("graph_enrichment_yield"),
                "consistency": m.get("consistency_rate"),
            }
        parsed.append(row)
        for c in cols:
            if row[c] is not None:
                cols[c].append(row[c])

    # Determine best: lowest unmapped, highest confidence/consistency, skills N/A for bolding
    best = {}
    if cols["unmapped"]:
        best["unmapped"] = min(cols["unmapped"])
    if cols["confidence"]:
        best["confidence"] = max(cols["confidence"])
    if cols["consistency"]:
        best["consistency"] = max(cols["consistency"])

    lines = []
    for row in parsed:
        cells = [row["label"]]

        # Skills/doc
        cells.append(fmt_float(row["skills"], 1) if row["skills"] is not None else "---")

        # Unmapped
        if row["unmapped"] is not None:
            v = fmt_pct(row["unmapped"])
            cells.append(bold(v) if row["unmapped"] == best.get("unmapped") else v)
        else:
            cells.append("---")

        # Mean confidence
        if row["confidence"] is not None:
            v = fmt_float(row["confidence"])
            cells.append(bold(v) if row["confidence"] == best.get("confidence") else v)
        else:
            cells.append("---")

        # Graph yield
        cells.append(fmt_pct(row["graph"]) if row["graph"] is not None else "---")

        # Consistency
        if row["consistency"] is not None:
            v = fmt_float(row["consistency"])
            cells.append(bold(v) if row["consistency"] == best.get("consistency") else v)
        else:
            cells.append("---")

        lines.append("  " + " & ".join(cells))

    body = " \\\\\n".join(lines)
    src_label = "vacancies" if "vac" in source else "resumes"
    return _wrap_table(
        "lrrrrr",
        "Configuration & Skills/doc & Unmapped & Mean conf. & Graph yield & Consistency",
        body,
        f"Ablation study results ({src_label}).",
        f"tab:ablation-{src_label[:3]}",
    )


# ---------------------------------------------------------------------------
# Table 5: Baseline Comparison
# ---------------------------------------------------------------------------

BASELINE_MAPPERS = [
    ("fuzzy", "Fuzzy"),
    ("embedding", "Embedding"),
    ("llm_direct", "LLM direct"),
    ("llm_two_stage", "LLM two-stage"),
]


def table_baseline(data: dict, source: str) -> str:
    cols = {"unmapped": [], "confidence": [], "consistency": [], "breadth": []}
    parsed = []
    for key, label in BASELINE_MAPPERS:
        m = data[key]["metrics"]
        row = {
            "label": label,
            "unmapped": m.get("unmapped_rate_macro"),
            "confidence": m.get("confidence", {}).get("mean"),
            "breadth": m.get("esco_coverage_breadth"),
            "consistency": m.get("consistency_rate"),
        }
        parsed.append(row)
        for c in cols:
            if row[c] is not None:
                cols[c].append(row[c])

    best = {}
    if cols["unmapped"]:
        best["unmapped"] = min(cols["unmapped"])
    if cols["confidence"]:
        best["confidence"] = max(cols["confidence"])
    if cols["consistency"]:
        best["consistency"] = max(cols["consistency"])
    if cols["breadth"]:
        best["breadth"] = max(cols["breadth"])

    lines = []
    for row in parsed:
        cells = [row["label"]]

        # Unmapped
        if row["unmapped"] is not None:
            v = fmt_pct(row["unmapped"])
            cells.append(bold(v) if row["unmapped"] == best.get("unmapped") else v)
        else:
            cells.append("---")

        # Confidence
        if row["confidence"] is not None:
            v = fmt_float(row["confidence"])
            cells.append(bold(v) if row["confidence"] == best.get("confidence") else v)
        else:
            cells.append("---")

        # Breadth
        if row["breadth"] is not None:
            v = fmt_int(row["breadth"])
            cells.append(bold(v) if row["breadth"] == best.get("breadth") else v)
        else:
            cells.append("---")

        # Consistency
        if row["consistency"] is not None:
            v = fmt_float(row["consistency"])
            cells.append(bold(v) if row["consistency"] == best.get("consistency") else v)
        else:
            cells.append("---")

        lines.append("  " + " & ".join(cells))

    body = " \\\\\n".join(lines)
    src_label = "vacancies" if "vac" in source else "resumes"
    return _wrap_table(
        "lrrrr",
        "Mapper & Unmapped & Mean conf. & ESCO URIs & Consistency",
        body,
        f"Baseline mapper comparison ({src_label}).",
        f"tab:baseline-{src_label[:3]}",
    )


# ---------------------------------------------------------------------------
# Table 6: Expert Evaluation
# ---------------------------------------------------------------------------

def table_expert(expert_dir: str) -> str:
    # Import from compute_metrics.py
    metrics_dir = Path(expert_dir).resolve()
    sys.path.insert(0, str(metrics_dir))
    from compute_metrics import BANDS, compute_band_metrics, load_band, aggregate_label
    sys.path.pop(0)

    band_metrics = {}
    all_aggregated = []
    all_rows = []
    for band_name, filename in BANDS:
        rows = load_band(filename)
        band_metrics[band_name] = compute_band_metrics(rows)
        all_rows.extend(rows)
        from compute_metrics import expert_columns
        cols = expert_columns(rows[0])
        for row in rows:
            labels = [row[c] for c in cols]
            all_aggregated.append(aggregate_label(labels))

    # Overall metrics
    n_total = len(all_aggregated)
    overall_strict = sum(1 for l in all_aggregated if l == "Correct") / n_total
    overall_lenient = sum(1 for l in all_aggregated if l in ("Correct", "Acceptable")) / n_total
    overall_incorrect = sum(1 for l in all_aggregated if l == "Incorrect") / n_total

    # Overall kappa
    from compute_metrics import expert_columns, cohens_kappa, fleiss_kappa
    cols = expert_columns(all_rows[0])
    n_experts = len(cols)
    categories = ["Incorrect", "Acceptable", "Correct"]
    if n_experts == 2:
        overall_kappa = cohens_kappa(
            [r[cols[0]] for r in all_rows],
            [r[cols[1]] for r in all_rows],
            categories,
        )
    else:
        matrix = []
        for row in all_rows:
            counts = [0] * len(categories)
            for c in cols:
                idx = categories.index(row[c])
                counts[idx] += 1
            matrix.append(counts)
        overall_kappa = fleiss_kappa(matrix, categories)

    overall_raw = sum(
        1 for row in all_rows if len(set(row[c] for c in cols)) == 1
    ) / len(all_rows)

    lines = []
    for band_name, _ in BANDS:
        m = band_metrics[band_name]
        lines.append(
            f"  {band_name.capitalize()} & {m['n']} & {fmt_pct(m['strict_accuracy'])} "
            f"& {fmt_pct(m['lenient_accuracy'])} & {fmt_pct(m['incorrect_rate'])} "
            f"& {fmt_float(m['kappa'])} & {fmt_pct(m['raw_agreement'])}"
        )
    overall_line = (
        f"  Overall & {n_total} & {fmt_pct(overall_strict)} "
        f"& {fmt_pct(overall_lenient)} & {fmt_pct(overall_incorrect)} "
        f"& {fmt_float(overall_kappa)} & {fmt_pct(overall_raw)}"
    )

    body = " \\\\\n".join(lines) + " \\\\\n    \\midrule\n" + overall_line
    return _wrap_table(
        "lrrrrrr",
        "Band & $N$ & Strict & Lenient & Incorrect & $\\kappa$ & Agreement",
        body,
        "Expert evaluation of mapping quality by skill frequency band.",
        "tab:expert",
    )


# ---------------------------------------------------------------------------
# Shared table wrapper
# ---------------------------------------------------------------------------

def _wrap_table(col_spec: str, header: str, body: str, caption: str, label: str) -> str:
    return (
        "\\begin{table}[htbp]\n"
        "  \\centering\n"
        f"  \\caption{{{caption}}}\n"
        f"  \\label{{{label}}}\n"
        f"  \\begin{{tabular}}{{{col_spec}}}\n"
        "    \\toprule\n"
        f"    {header} \\\\\n"
        "    \\midrule\n"
        f"{body} \\\\\n"
        "    \\bottomrule\n"
        "  \\end{tabular}\n"
        "\\end{table}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate LaTeX tables from evaluation outputs.")
    parser.add_argument("--intrinsic-vac", type=str, help="Path to vac_intrinsic.json")
    parser.add_argument("--intrinsic-cv", type=str, help="Path to cv_intrinsic.json")
    parser.add_argument("--consistency-vac", type=str, help="Path to vac_consistency.json")
    parser.add_argument("--consistency-cv", type=str, help="Path to cv_consistency.json")
    parser.add_argument("--ablation-vac", type=str, help="Path to vacancies ablation_summary.json")
    parser.add_argument("--ablation-cv", type=str, help="Path to resumes ablation_summary.json")
    parser.add_argument("--baseline-vac", type=str, help="Path to vacancies baseline_summary.json")
    parser.add_argument("--baseline-cv", type=str, help="Path to resumes baseline_summary.json")
    parser.add_argument("--expert-dir", type=str, help="Directory with expert CSV files")
    parser.add_argument("--output", type=str, default="evaluation/intrinsic/output/tables/",
                        help="Output directory for .tex files")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    def load(path: str | None) -> dict | None:
        if path and Path(path).exists():
            return json.loads(Path(path).read_text(encoding="utf-8"))
        return None

    generated = 0

    # Table 1: Intrinsic
    vac_i = load(args.intrinsic_vac)
    cv_i = load(args.intrinsic_cv)
    if vac_i and cv_i:
        try:
            tex = table_intrinsic(vac_i, cv_i)
            write_table(out / "table_intrinsic.tex", tex)
            generated += 1
        except Exception as e:
            print(f"WARNING: skipping table_intrinsic: {e}", file=sys.stderr)

    # Table 2: Confidence
    if vac_i and cv_i:
        try:
            tex = table_confidence(vac_i, cv_i)
            write_table(out / "table_confidence.tex", tex)
            generated += 1
        except Exception as e:
            print(f"WARNING: skipping table_confidence: {e}", file=sys.stderr)

    # Table 3: Consistency
    vac_c = load(args.consistency_vac)
    cv_c = load(args.consistency_cv)
    if vac_c and cv_c:
        try:
            tex = table_consistency(vac_c, cv_c)
            write_table(out / "table_consistency.tex", tex)
            generated += 1
        except Exception as e:
            print(f"WARNING: skipping table_consistency: {e}", file=sys.stderr)

    # Table 4: Ablation
    for path_arg, source_tag, filename in [
        (args.ablation_vac, "vac", "table_ablation_vacancies.tex"),
        (args.ablation_cv, "cv", "table_ablation_resumes.tex"),
    ]:
        data = load(path_arg)
        if data:
            try:
                tex = table_ablation(data, source_tag)
                write_table(out / filename, tex)
                generated += 1
            except Exception as e:
                print(f"WARNING: skipping {filename}: {e}", file=sys.stderr)

    # Table 5: Baseline
    for path_arg, source_tag, filename in [
        (args.baseline_vac, "vac", "table_baseline_vacancies.tex"),
        (args.baseline_cv, "cv", "table_baseline_resumes.tex"),
    ]:
        data = load(path_arg)
        if data:
            try:
                tex = table_baseline(data, source_tag)
                write_table(out / filename, tex)
                generated += 1
            except Exception as e:
                print(f"WARNING: skipping {filename}: {e}", file=sys.stderr)

    # Table 6: Expert
    if args.expert_dir and Path(args.expert_dir).is_dir():
        try:
            tex = table_expert(args.expert_dir)
            write_table(out / "table_expert.tex", tex)
            generated += 1
        except Exception as e:
            print(f"WARNING: skipping table_expert: {e}", file=sys.stderr)

    print(f"Generated {generated} table(s) in {out}/")


if __name__ == "__main__":
    main()
