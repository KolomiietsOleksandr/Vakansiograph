"""Extract raw skills from processed JSONL files and compute frequency statistics.

Outputs a JSON file with every unique (raw_skill → esco_uri, esco_label, confidence)
mapping and its occurrence count across the corpus, split by source (vacancies/resumes).

Usage:
    python scripts/extract_skill_frequencies.py \
        --vac evaluation/vac_llm_two_stage_llm_two_stage.jsonl \
        --cv evaluation/cv_llm_two_stage2_llm_two_stage.jsonl \
        --output evaluation/skill_frequencies.json
"""
import argparse
import json
from collections import Counter
from pathlib import Path


def extract_skills(path: str) -> tuple[Counter, dict]:
    """Return (skill_counter, skill_to_best_mapping) from a JSONL file.

    skill_counter: raw_skill_lower → total occurrences
    skill_to_best_mapping: raw_skill_lower → {raw_skill, esco_uri, esco_label, confidence, reasoning}
        keeps the highest-confidence mapping seen for each skill.
    """
    counter: Counter = Counter()
    best: dict[str, dict] = {}

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            for m in doc.get("direct_mappings", []) + doc.get("graph_mappings", []):
                key = m["raw_skill"].strip().lower()
                counter[key] += 1
                conf = m.get("confidence", 0)
                if key not in best or conf > best[key]["confidence"]:
                    best[key] = {
                        "raw_skill": m["raw_skill"].strip(),
                        "esco_uri": m["esco_uri"],
                        "esco_label": m["esco_label"],
                        "confidence": conf,
                        "reasoning": m.get("details", {}).get("reasoning", ""),
                        "via_graph": m.get("via_graph", False),
                    }

            for skill in doc.get("unmapped_skills", []):
                key = skill.strip().lower()
                counter[key] += 1
                if key not in best:
                    best[key] = {
                        "raw_skill": skill.strip(),
                        "esco_uri": None,
                        "esco_label": None,
                        "confidence": 0,
                        "reasoning": "",
                        "via_graph": False,
                    }

    return counter, best


def main():
    parser = argparse.ArgumentParser(description="Extract skill frequencies from pipeline output")
    parser.add_argument("--vac", required=True, help="Vacancies JSONL file")
    parser.add_argument("--cv", required=True, help="Resumes JSONL file")
    parser.add_argument("--output", default="evaluation/skill_frequencies.json", help="Output JSON")
    args = parser.parse_args()

    vac_counts, vac_best = extract_skills(args.vac)
    cv_counts, cv_best = extract_skills(args.cv)

    # Merge
    all_skills = set(vac_counts.keys()) | set(cv_counts.keys())
    total_counts = Counter()
    for key in all_skills:
        total_counts[key] = vac_counts.get(key, 0) + cv_counts.get(key, 0)

    # Build output: one entry per unique skill
    results = []
    for key in all_skills:
        # Pick best mapping from whichever source has higher confidence
        vb = vac_best.get(key)
        cb = cv_best.get(key)
        if vb and cb:
            mapping = vb if vb["confidence"] >= cb["confidence"] else cb
        else:
            mapping = vb or cb

        results.append({
            "raw_skill": mapping["raw_skill"],
            "raw_skill_lower": key,
            "esco_uri": mapping["esco_uri"],
            "esco_label": mapping["esco_label"],
            "confidence": mapping["confidence"],
            "reasoning": mapping["reasoning"],
            "via_graph": mapping["via_graph"],
            "count_total": total_counts[key],
            "count_vacancies": vac_counts.get(key, 0),
            "count_resumes": cv_counts.get(key, 0),
        })

    results.sort(key=lambda x: x["count_total"], reverse=True)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Print summary
    mapped = [r for r in results if r["esco_uri"] is not None]
    unmapped = [r for r in results if r["esco_uri"] is None]

    print(f"Total unique skills: {len(results)}")
    print(f"  Mapped:   {len(mapped)}")
    print(f"  Unmapped: {len(unmapped)}")
    print(f"\nTop 20 most frequent:")
    for r in results[:20]:
        status = r["esco_label"] or "UNMAPPED"
        print(f"  {r['count_total']:>5}x  {r['raw_skill']:<40}  → {status}")

    print(f"\nTop 10 rarest (count=1):")
    rare = [r for r in results if r["count_total"] == 1]
    for r in rare[:10]:
        status = r["esco_label"] or "UNMAPPED"
        print(f"  {r['count_total']:>5}x  {r['raw_skill']:<40}  → {status}")

    print(f"\nTotal rare skills (count=1): {len(rare)}")
    print(f"Output written to: {output_path}")


if __name__ == "__main__":
    main()
