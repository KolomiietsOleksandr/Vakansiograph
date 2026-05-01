"""CLI for evaluating pipeline output against a gold standard."""
import argparse
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from esco_pipeline.evaluation import evaluate, load_gold_standard, print_comparison_table
from esco_pipeline.models import DocumentResult, ESCOMapping


def load_results_jsonl(path: str) -> list[DocumentResult]:
    results = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            mappings = [ESCOMapping(**m) for m in data.get("mappings", [])]
            result = DocumentResult(
                document_id=data["document_id"],
                mappings=mappings,
                unmapped_skills=data.get("unmapped_skills", []),
                metadata=data.get("metadata", {}),
            )
            results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description="Evaluate ESCO pipeline results")
    parser.add_argument("gold", help="Gold standard JSON file {doc_id: [esco_uris]}")
    parser.add_argument("results", nargs="+", help="Pipeline JSONL output files")
    parser.add_argument("--output-csv", type=str, default=None, help="Export metrics to CSV")
    args = parser.parse_args()

    gold = load_gold_standard(args.gold)
    print(f"Gold standard: {len(gold)} documents")

    metrics_by_mapper: dict = {}
    for result_path in args.results:
        # Use filename as mapper name
        mapper_name = Path(result_path).stem
        results = load_results_jsonl(result_path)
        print(f"Loaded {len(results)} results from {result_path}")
        metrics = evaluate(results, gold)
        metrics_by_mapper[mapper_name] = metrics

    print("\n=== Evaluation Results ===\n")
    print_comparison_table(metrics_by_mapper, output_csv=args.output_csv)


if __name__ == "__main__":
    main()
