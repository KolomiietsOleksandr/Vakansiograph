"""Consistency analysis: how often the same skill string maps to the same ESCO URI."""

import argparse
import json
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from esco_pipeline.esco_interface import ESCOIndex
from evaluation.intrinsic.utils import stream_jsonl


def collect_skill_uris(jsonl_path: str) -> dict[str, list[str]]:
    """Build skill_lower → [esco_uri, ...] from JSONL mappings."""
    skill_uris: dict[str, list[str]] = defaultdict(list)
    print(f"Collecting skill→URI mappings from {jsonl_path}")
    for doc in stream_jsonl(jsonl_path):
        for mapping in doc.get("direct_mappings", []) + doc.get("graph_mappings", []):
            raw = mapping.get("raw_skill", "")
            uri = mapping.get("esco_uri", "")
            if raw and uri:
                skill_uris[raw.lower()].append(uri)
    return dict(skill_uris)


def classify_inconsistency(uris: list[str], esco: ESCOIndex) -> str:
    """Check if URI set represents polysemy or instability."""
    unique = list(set(uris))
    for u1, u2 in combinations(unique, 2):
        # Check parent/child
        parent1 = esco.get_parent(u1)
        if parent1 and parent1.uri == u2:
            return "instability"
        parent2 = esco.get_parent(u2)
        if parent2 and parent2.uri == u1:
            return "instability"
        # Check siblings
        siblings1 = {s.uri for s in esco.get_siblings(u1)}
        if u2 in siblings1:
            return "instability"
    return "polysemy"


def histogram_bucket(consistency: float) -> str:
    if consistency >= 1.0:
        return "100%"
    elif consistency >= 0.9:
        return "90-99%"
    elif consistency >= 0.8:
        return "80-89%"
    elif consistency >= 0.7:
        return "70-79%"
    elif consistency >= 0.6:
        return "60-69%"
    elif consistency >= 0.5:
        return "50-59%"
    else:
        return "<50%"


def analyze(jsonl_path: str, esco_dir: str, min_count: int) -> dict:
    skill_uris = collect_skill_uris(jsonl_path)
    total_unique = len(skill_uris)

    qualifying = {s: uris for s, uris in skill_uris.items() if len(uris) >= min_count}
    print(f"Total unique skills: {total_unique}, qualifying (>={min_count}): {len(qualifying)}")

    print("Loading ESCO index for hierarchy checks...")
    esco = ESCOIndex(data_dir=esco_dir, gemini_api_key="")

    bucket_order = ["100%", "90-99%", "80-89%", "70-79%", "60-69%", "50-59%", "<50%"]
    histogram: dict[str, int] = {b: 0 for b in bucket_order}
    consistencies: list[float] = []
    inconsistent_skills: list[dict] = []
    polysemy_count = 0
    instability_count = 0

    for i, (skill, uris) in enumerate(qualifying.items(), 1):
        if i % 500 == 0:
            print(f"  Analyzing skill {i}/{len(qualifying)}")

        counter = Counter(uris)
        modal_uri, modal_count = counter.most_common(1)[0]
        total = len(uris)
        consistency = modal_count / total

        consistencies.append(consistency)
        histogram[histogram_bucket(consistency)] += 1

        if consistency < 1.0:
            classification = classify_inconsistency(uris, esco)
            if classification == "polysemy":
                polysemy_count += 1
            else:
                instability_count += 1

            uri_dist = []
            for uri, count in counter.most_common():
                skill_obj = esco.get_skill(uri)
                label = skill_obj.preferred_label if skill_obj else uri
                uri_dist.append({"uri": uri, "label": label, "count": count})

            inconsistent_skills.append({
                "skill": skill,
                "consistency": round(consistency, 4),
                "total_occurrences": total,
                "uri_distribution": uri_dist,
                "classification": classification,
            })

    inconsistent_skills.sort(key=lambda x: x["consistency"])
    macro_avg = sum(consistencies) / len(consistencies) if consistencies else 0.0

    return {
        "total_unique_skills": total_unique,
        "qualifying_skills": len(qualifying),
        "macro_avg_consistency": round(macro_avg, 4),
        "histogram": histogram,
        "polysemy_count": polysemy_count,
        "instability_count": instability_count,
        "top_inconsistent": inconsistent_skills[:20],
    }


def main():
    parser = argparse.ArgumentParser(description="Consistency analysis for skill→ESCO mappings")
    parser.add_argument("--input", required=True, help="JSONL input path")
    parser.add_argument("--esco-dir", default="esco", help="ESCO data directory")
    parser.add_argument("--min-count", type=int, default=5, help="Minimum skill occurrences")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    result = analyze(args.input, args.esco_dir, args.min_count)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\nResults written to {args.output}")
    print(f"  Qualifying skills: {result['qualifying_skills']}")
    print(f"  Macro-avg consistency: {result['macro_avg_consistency']}")
    print(f"  Polysemy: {result['polysemy_count']}, Instability: {result['instability_count']}")
    print(f"  Histogram: {result['histogram']}")


if __name__ == "__main__":
    main()
