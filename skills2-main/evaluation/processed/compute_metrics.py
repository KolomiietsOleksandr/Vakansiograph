"""Compute evaluation metrics from expert annotations.

Supports 2 or 3 experts. Re-run when Taras delivers his annotations.

Usage:
    python evaluation/processed/compute_metrics.py
"""
import csv
import sys
from collections import Counter
from pathlib import Path

# Ordinal encoding: lower = stricter
LABEL_ORDER = {"Incorrect": 0, "Acceptable": 1, "Correct": 2}
ORDER_LABEL = {v: k for k, v in LABEL_ORDER.items()}

BANDS = [
    ("frequent", "all_experts- frequent.csv"),
    ("mid", "all_experts - medium.csv"),
    ("rare", "all_experts - rare.csv"),
]

HERE = Path(__file__).parent


def load_band(filename: str) -> list[dict]:
    rows = []
    with open(HERE / filename, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def expert_columns(row: dict) -> list[str]:
    """Return expert match columns present in this row."""
    cols = sorted(k for k in row if k.startswith("match_"))
    return cols


def aggregate_label(labels: list[str]) -> str:
    """Aggregate expert labels into a single label.

    - 3 experts: majority vote (mode).
    - 2 experts: conservative (minimum ordinal).
    """
    cleaned = [l.strip() for l in labels]
    unknown = [l for l in cleaned if l not in LABEL_ORDER]
    if unknown:
        raise ValueError(f"Unknown label(s): {unknown}. Expected one of {sorted(LABEL_ORDER)}")

    codes = [LABEL_ORDER[l] for l in cleaned]
    n = len(codes)

    if n == 2:
        # Conservative: take the lower (stricter) rating.
        return ORDER_LABEL[min(codes)]

    if n >= 3:
        # Prefer a true majority vote when it exists. If no majority (e.g., 3-way disagreement
        # among Incorrect/Acceptable/Correct), fall back to an ordinal median to avoid picking an
        # arbitrary rater due to tie ordering.
        cnt = Counter(codes)
        top_code, top_count = cnt.most_common(1)[0]
        if top_count >= (n // 2) + 1:
            return ORDER_LABEL[top_code]

        sorted_codes = sorted(codes)
        return ORDER_LABEL[sorted_codes[(n - 1) // 2]]  # median (lower-median if even)

    return cleaned[0]


def cohens_kappa(labels1: list[str], labels2: list[str], categories: list[str]) -> float:
    """Cohen's kappa for two raters."""
    n = len(labels1)
    assert n == len(labels2)

    # Observed agreement
    po = sum(1 for a, b in zip(labels1, labels2) if a == b) / n

    # Expected agreement
    pe = 0.0
    for cat in categories:
        p1 = sum(1 for l in labels1 if l == cat) / n
        p2 = sum(1 for l in labels2 if l == cat) / n
        pe += p1 * p2

    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def fleiss_kappa(ratings_matrix: list[list[int]], categories: list[str]) -> float:
    """Fleiss' kappa for 3+ raters.

    ratings_matrix: list of rows, each row = [count_cat0, count_cat1, count_cat2]
    """
    n_subjects = len(ratings_matrix)
    n_raters = sum(ratings_matrix[0])
    n_categories = len(categories)

    # Proportion per category
    p_j = []
    for j in range(n_categories):
        total = sum(row[j] for row in ratings_matrix)
        p_j.append(total / (n_subjects * n_raters))

    # Per-subject agreement
    P_i = []
    for row in ratings_matrix:
        s = sum(r * (r - 1) for r in row)
        P_i.append(s / (n_raters * (n_raters - 1)))

    P_bar = sum(P_i) / n_subjects
    Pe = sum(p ** 2 for p in p_j)

    if Pe == 1.0:
        return 1.0
    return (P_bar - Pe) / (1 - Pe)


def compute_band_metrics(rows: list[dict]) -> dict:
    """Compute metrics for a single frequency band."""
    cols = expert_columns(rows[0])
    n_experts = len(cols)

    all_labels_per_expert = {c: [] for c in cols}
    aggregated = []

    for row in rows:
        labels = [row[c] for c in cols]
        all_labels_per_expert_row = {c: row[c] for c in cols}
        for c in cols:
            all_labels_per_expert[c].append(row[c])
        aggregated.append(aggregate_label(labels))

    # Strict accuracy: Correct only
    strict = sum(1 for l in aggregated if l == "Correct") / len(aggregated)
    # Lenient accuracy: Correct + Acceptable
    lenient = sum(1 for l in aggregated if l in ("Correct", "Acceptable")) / len(aggregated)
    # Incorrect rate
    incorrect = sum(1 for l in aggregated if l == "Incorrect") / len(aggregated)

    # Distribution
    dist = Counter(aggregated)

    # Inter-annotator agreement
    categories = ["Incorrect", "Acceptable", "Correct"]
    if n_experts == 2:
        kappa = cohens_kappa(
            all_labels_per_expert[cols[0]],
            all_labels_per_expert[cols[1]],
            categories,
        )
        agreement_type = "Cohen's kappa"
    elif n_experts >= 3:
        # Build ratings matrix for Fleiss
        matrix = []
        for row in rows:
            counts = [0] * len(categories)
            for c in cols:
                idx = categories.index(row[c])
                counts[idx] += 1
            matrix.append(counts)
        kappa = fleiss_kappa(matrix, categories)
        agreement_type = "Fleiss' kappa"
    else:
        kappa = None
        agreement_type = "N/A"

    # Raw agreement (% same label across all experts)
    raw_agree = sum(
        1 for row in rows if len(set(row[c] for c in cols)) == 1
    ) / len(rows)

    return {
        "n": len(rows),
        "n_experts": n_experts,
        "strict_accuracy": strict,
        "lenient_accuracy": lenient,
        "incorrect_rate": incorrect,
        "distribution": dict(dist),
        "kappa": kappa,
        "agreement_type": agreement_type,
        "raw_agreement": raw_agree,
    }


def main():
    print("=" * 70)
    print("ESCO Mapping Expert Evaluation Results")
    print("=" * 70)

    all_aggregated = []
    band_metrics = {}

    for band_name, filename in BANDS:
        rows = load_band(filename)
        metrics = compute_band_metrics(rows)
        band_metrics[band_name] = metrics

        cols = expert_columns(rows[0])
        for row in rows:
            labels = [row[c] for c in cols]
            all_aggregated.append(aggregate_label(labels))

        print(f"\n--- {band_name.upper()} (n={metrics['n']}, {metrics['n_experts']} experts) ---")
        print(f"  Strict accuracy (Correct):          {metrics['strict_accuracy']:.1%}")
        print(f"  Lenient accuracy (Correct+Accept.):  {metrics['lenient_accuracy']:.1%}")
        print(f"  Incorrect rate:                      {metrics['incorrect_rate']:.1%}")
        print(f"  Distribution: {metrics['distribution']}")
        print(f"  {metrics['agreement_type']}:  {metrics['kappa']:.3f}" if metrics['kappa'] is not None else "")
        print(f"  Raw agreement:                       {metrics['raw_agreement']:.1%}")

    # Overall
    n_total = len(all_aggregated)
    overall_strict = sum(1 for l in all_aggregated if l == "Correct") / n_total
    overall_lenient = sum(1 for l in all_aggregated if l in ("Correct", "Acceptable")) / n_total
    overall_incorrect = sum(1 for l in all_aggregated if l == "Incorrect") / n_total
    overall_dist = Counter(all_aggregated)

    # Overall kappa (pool all rows)
    all_rows = []
    for _, filename in BANDS:
        all_rows.extend(load_band(filename))
    cols = expert_columns(all_rows[0])
    n_experts = len(cols)
    categories = ["Incorrect", "Acceptable", "Correct"]

    if n_experts == 2:
        overall_kappa = cohens_kappa(
            [r[cols[0]] for r in all_rows],
            [r[cols[1]] for r in all_rows],
            categories,
        )
        kappa_type = "Cohen's kappa"
    elif n_experts >= 3:
        matrix = []
        for row in all_rows:
            counts = [0] * len(categories)
            for c in cols:
                idx = categories.index(row[c])
                counts[idx] += 1
            matrix.append(counts)
        overall_kappa = fleiss_kappa(matrix, categories)
        kappa_type = "Fleiss' kappa"

    print(f"\n{'=' * 70}")
    print(f"OVERALL (n={n_total}, {n_experts} experts)")
    print(f"{'=' * 70}")
    print(f"  Strict accuracy (Correct):          {overall_strict:.1%}")
    print(f"  Lenient accuracy (Correct+Accept.):  {overall_lenient:.1%}")
    print(f"  Incorrect rate:                      {overall_incorrect:.1%}")
    print(f"  Distribution: {dict(overall_dist)}")
    print(f"  {kappa_type}:  {overall_kappa:.3f}")

    # Summary table for paper
    print(f"\n{'=' * 70}")
    print("SUMMARY TABLE (for paper)")
    print(f"{'=' * 70}")
    print(f"{'Band':<12} {'N':>4} {'Strict':>8} {'Lenient':>8} {'Incorrect':>10} {'Kappa':>8}")
    print("-" * 54)
    for band_name in ["frequent", "mid", "rare"]:
        m = band_metrics[band_name]
        print(f"{band_name:<12} {m['n']:>4} {m['strict_accuracy']:>7.1%} {m['lenient_accuracy']:>7.1%} {m['incorrect_rate']:>9.1%} {m['kappa']:>7.3f}")
    print("-" * 54)
    print(f"{'Overall':<12} {n_total:>4} {overall_strict:>7.1%} {overall_lenient:>7.1%} {overall_incorrect:>9.1%} {overall_kappa:>7.3f}")


if __name__ == "__main__":
    main()
