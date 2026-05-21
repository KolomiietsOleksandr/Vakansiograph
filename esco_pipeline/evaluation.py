import csv
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from esco_pipeline.models import DocumentResult

logger = logging.getLogger(__name__)


def load_gold_standard(path: str | Path) -> dict[str, list[str]]:
    """Load gold standard from JSON: {doc_id: [esco_uris]}"""
    with open(path) as f:
        return json.load(f)


@dataclass
class EvaluationMetrics:
    precision: float
    recall: float
    f1: float
    unmapped_rate: float
    false_positive_rate: float
    coverage: float


def evaluate(
    results: list[DocumentResult],
    gold_standard: dict[str, list[str]],
) -> dict[str, EvaluationMetrics]:
    """Evaluate pipeline results against gold standard per document."""
    metrics: dict[str, EvaluationMetrics] = {}

    for doc in results:
        if doc.document_id not in gold_standard:
            continue

        gold_uris = set(gold_standard[doc.document_id])
        predicted_uris = {m.esco_uri for m in doc.direct_mappings + doc.graph_mappings}

        tp = len(predicted_uris & gold_uris)
        fp = len(predicted_uris - gold_uris)
        fn = len(gold_uris - predicted_uris)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        total_skills = len(doc.direct_mappings) + len(doc.graph_mappings) + len(doc.unmapped_skills)
        unmapped_rate = len(doc.unmapped_skills) / total_skills if total_skills > 0 else 0.0

        # False positive rate: predicted URIs not in gold
        false_positive_rate = fp / len(predicted_uris) if predicted_uris else 0.0

        coverage = len(predicted_uris) / len(gold_uris) if gold_uris else 0.0

        metrics[doc.document_id] = EvaluationMetrics(
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1, 4),
            unmapped_rate=round(unmapped_rate, 4),
            false_positive_rate=round(false_positive_rate, 4),
            coverage=round(coverage, 4),
        )

    return metrics


def _average_metrics(metrics: dict[str, EvaluationMetrics]) -> EvaluationMetrics:
    if not metrics:
        return EvaluationMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    n = len(metrics)
    return EvaluationMetrics(
        precision=round(sum(m.precision for m in metrics.values()) / n, 4),
        recall=round(sum(m.recall for m in metrics.values()) / n, 4),
        f1=round(sum(m.f1 for m in metrics.values()) / n, 4),
        unmapped_rate=round(sum(m.unmapped_rate for m in metrics.values()) / n, 4),
        false_positive_rate=round(sum(m.false_positive_rate for m in metrics.values()) / n, 4),
        coverage=round(sum(m.coverage for m in metrics.values()) / n, 4),
    )


def print_comparison_table(
    metrics_by_mapper: dict[str, dict[str, EvaluationMetrics]],
    output_csv: str | Path | None = None,
) -> None:
    """Print a comparison table of metrics across mappers and optionally export to CSV."""
    fields = ["mapper", "precision", "recall", "f1", "unmapped_rate", "false_positive_rate", "coverage"]
    header = f"{'Mapper':<20} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Unmapped':>10} {'FP Rate':>10} {'Coverage':>10}"
    separator = "-" * len(header)

    print(separator)
    print(header)
    print(separator)

    rows = []
    for mapper_name, per_doc_metrics in metrics_by_mapper.items():
        avg = _average_metrics(per_doc_metrics)
        print(
            f"{mapper_name:<20} {avg.precision:>10.4f} {avg.recall:>10.4f} {avg.f1:>10.4f} "
            f"{avg.unmapped_rate:>10.4f} {avg.false_positive_rate:>10.4f} {avg.coverage:>10.4f}"
        )
        rows.append({
            "mapper": mapper_name,
            "precision": avg.precision,
            "recall": avg.recall,
            "f1": avg.f1,
            "unmapped_rate": avg.unmapped_rate,
            "false_positive_rate": avg.false_positive_rate,
            "coverage": avg.coverage,
        })
    print(separator)

    if output_csv:
        path = Path(output_csv)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        logger.info("Metrics exported to %s", output_csv)
