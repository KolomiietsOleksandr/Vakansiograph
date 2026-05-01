"""Compute corpus-wide intrinsic metrics from pipeline JSONL output."""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np

# Allow running as script: python evaluation/intrinsic/intrinsic_metrics.py
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.intrinsic.utils import stream_jsonl


def compute_metrics(input_path: str, source: str) -> dict:
    per_doc_unmapped_rates = []
    all_confidences = []
    distinct_uris = set()
    per_doc_skills = []
    per_doc_mappings = []
    total_graph = 0
    total_all_mappings = 0
    method_counter = Counter()
    doc_count = 0

    print(f"Streaming {input_path} (source={source})...")
    for doc in stream_jsonl(input_path):
        doc_count += 1
        direct = doc.get("direct_mappings", [])
        graph = doc.get("graph_mappings", [])
        unmapped = doc.get("unmapped_skills", [])

        n_mapped = len(direct) + len(graph)
        n_unmapped = len(unmapped)
        n_total = n_mapped + n_unmapped

        # Unmapped rate per doc
        if n_total > 0:
            per_doc_unmapped_rates.append(n_unmapped / n_total)

        # Confidences and methods
        for m in direct + graph:
            conf = m.get("confidence")
            if conf is not None:
                all_confidences.append(conf)
            method = m.get("method")
            if method:
                method_counter[method] += 1

        # Distinct URIs
        for m in direct + graph:
            uri = m.get("esco_uri")
            if uri:
                distinct_uris.add(uri)

        # Per-doc counts
        per_doc_skills.append(n_total)
        per_doc_mappings.append(n_mapped)

        # Graph enrichment
        total_graph += len(graph)
        total_all_mappings += n_mapped

    # Compute stats
    confidences = np.array(all_confidences) if all_confidences else np.array([])
    unmapped_rates = np.array(per_doc_unmapped_rates) if per_doc_unmapped_rates else np.array([])
    skills_arr = np.array(per_doc_skills) if per_doc_skills else np.array([])
    mappings_arr = np.array(per_doc_mappings) if per_doc_mappings else np.array([])

    # Confidence buckets
    bucket_edges = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    bucket_labels = ["0.0-0.5", "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"]
    confidence_buckets = {}
    if len(confidences) > 0:
        for i in range(len(bucket_labels)):
            lo, hi = bucket_edges[i], bucket_edges[i + 1]
            if i == len(bucket_labels) - 1:
                count = int(np.sum((confidences >= lo) & (confidences <= hi)))
            else:
                count = int(np.sum((confidences >= lo) & (confidences < hi)))
            confidence_buckets[bucket_labels[i]] = count

    def stats(arr):
        if len(arr) == 0:
            return {"mean": 0, "median": 0, "std": 0}
        return {
            "mean": round(float(np.mean(arr)), 4),
            "median": round(float(np.median(arr)), 4),
            "std": round(float(np.std(arr)), 4),
        }

    result = {
        "source": source,
        "documents": doc_count,
        "unmapped_rate_macro": round(float(np.mean(unmapped_rates)), 4) if len(unmapped_rates) > 0 else 0,
        "confidence": {
            "buckets": confidence_buckets,
            **stats(confidences),
        },
        "esco_coverage_breadth": len(distinct_uris),
        "skills_per_document": stats(skills_arr),
        "mappings_per_document": stats(mappings_arr),
        "graph_enrichment_yield": round(total_graph / total_all_mappings, 4) if total_all_mappings > 0 else 0,
        "method_distribution": dict(method_counter.most_common()),
    }
    return result


def print_summary(result: dict):
    print(f"\n{'=' * 60}")
    print(f"Intrinsic Metrics Summary ({result['source']}, {result['documents']} docs)")
    print(f"{'=' * 60}")
    print(f"  Unmapped rate (macro):     {result['unmapped_rate_macro']:.4f}")
    print(f"  Confidence mean/med/std:   {result['confidence']['mean']:.4f} / {result['confidence']['median']:.4f} / {result['confidence']['std']:.4f}")
    print(f"  ESCO coverage breadth:     {result['esco_coverage_breadth']} distinct URIs")
    s = result["skills_per_document"]
    print(f"  Skills/doc mean/med/std:   {s['mean']:.1f} / {s['median']:.1f} / {s['std']:.1f}")
    m = result["mappings_per_document"]
    print(f"  Mappings/doc mean/med/std: {m['mean']:.1f} / {m['median']:.1f} / {m['std']:.1f}")
    print(f"  Graph enrichment yield:    {result['graph_enrichment_yield']:.4f}")
    print(f"  Method distribution:       {result['method_distribution']}")
    print(f"  Confidence buckets:        {result['confidence']['buckets']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Compute intrinsic metrics from pipeline JSONL output")
    parser.add_argument("--input", required=True, help="Path to JSONL file")
    parser.add_argument("--source", default="vacancies", choices=["vacancies", "resumes"], help="Data source type")
    parser.add_argument("--output", required=True, help="Path for JSON output")
    args = parser.parse_args()

    result = compute_metrics(args.input, args.source)
    print_summary(result)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"Results written to {args.output}")


if __name__ == "__main__":
    main()
