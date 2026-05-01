"""Stratified sampling from pipeline output to produce annotation gold set."""
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def load_results(jsonl_path: str) -> list[dict]:
    results = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def stratified_sample(results: list[dict], n: int, seed: int = 42) -> list[dict]:
    """Sample documents stratifying by mapped/unmapped skill ratio."""
    rng = random.Random(seed)

    def coverage_bucket(doc: dict) -> str:
        total = len(doc.get("mappings", [])) + len(doc.get("unmapped_skills", []))
        if total == 0:
            return "empty"
        ratio = len(doc.get("mappings", [])) / total
        if ratio >= 0.8:
            return "high"
        elif ratio >= 0.4:
            return "medium"
        else:
            return "low"

    buckets: dict[str, list] = {"high": [], "medium": [], "low": [], "empty": []}
    for doc in results:
        buckets[coverage_bucket(doc)].append(doc)

    # Proportional allocation
    sampled = []
    per_bucket = max(1, n // len([b for b in buckets.values() if b]))
    for bucket_docs in buckets.values():
        rng.shuffle(bucket_docs)
        sampled.extend(bucket_docs[:per_bucket])

    rng.shuffle(sampled)
    return sampled[:n]


def main():
    parser = argparse.ArgumentParser(description="Sample pipeline output for annotation")
    parser.add_argument("input", help="Input JSONL file from pipeline")
    parser.add_argument("--n", type=int, default=50, help="Number of documents to sample")
    parser.add_argument("--output", type=str, default="output/annotation_sample.jsonl")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    results = load_results(args.input)
    print(f"Loaded {len(results)} documents")

    sampled = stratified_sample(results, args.n, args.seed)
    print(f"Sampled {len(sampled)} documents")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for doc in sampled:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    # Also write gold standard template
    gold_path = output_path.parent / "gold_standard_template.json"
    gold = {doc["document_id"]: [] for doc in sampled}
    with open(gold_path, "w") as f:
        json.dump(gold, f, ensure_ascii=False, indent=2)

    print(f"Annotation sample: {output_path}")
    print(f"Gold standard template: {gold_path} (fill in ESCO URIs)")


if __name__ == "__main__":
    main()
