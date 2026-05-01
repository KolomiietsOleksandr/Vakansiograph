"""Compare outputs from multiple mapper JSONL result files side-by-side."""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def load_jsonl(path: Path) -> list[dict]:
    results = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def extract_mapper_name(stem: str) -> str:
    """Extract mapper name from filename stem: 'run20_embedding' -> 'embedding'."""
    parts = stem.split("_", 1)
    return parts[1] if len(parts) > 1 else stem


def short_uri(uri: str) -> str:
    """Return last path segment of ESCO URI."""
    return uri.rstrip("/").split("/")[-1] if uri else ""


def build_doc_map(docs: list[dict]) -> dict[str, dict[str, tuple | None]]:
    """Build {doc_id: {skill_str: (uri, label, confidence) | None}} from doc list."""
    doc_map: dict[str, dict[str, tuple | None]] = {}
    for doc in docs:
        doc_id = doc["document_id"]
        skill_map: dict[str, tuple | None] = {}
        for m in doc.get("mappings", []):
            skill_map[m["raw_skill"]] = (m["esco_uri"], m["esco_label"], m["confidence"])
        for skill in doc.get("unmapped_skills", []):
            skill_map[skill] = None
        doc_map[doc_id] = skill_map
    return doc_map


def print_section(title: str, width: int = 80) -> None:
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def main():
    parser = argparse.ArgumentParser(description="Compare mapper JSONL outputs side-by-side")
    parser.add_argument("files", nargs="+", help="JSONL result files to compare")
    parser.add_argument("--output-csv", type=str, default=None, help="Export per-skill table to CSV")
    args = parser.parse_args()

    # Load all files
    mapper_data: dict[str, list[dict]] = {}
    for file_path in args.files:
        path = Path(file_path)
        if not path.exists():
            print(f"ERROR: File not found: {file_path}", file=sys.stderr)
            sys.exit(1)
        name = extract_mapper_name(path.stem)
        mapper_data[name] = load_jsonl(path)

    mapper_names = list(mapper_data.keys())

    # Build doc maps per mapper
    mapper_doc_maps: dict[str, dict[str, dict[str, tuple | None]]] = {
        name: build_doc_map(docs) for name, docs in mapper_data.items()
    }

    # Collect all doc IDs (preserve order from first mapper)
    all_doc_ids: list[str] = []
    seen_ids: set[str] = set()
    for name in mapper_names:
        for doc_id in mapper_doc_maps[name]:
            if doc_id not in seen_ids:
                all_doc_ids.append(doc_id)
                seen_ids.add(doc_id)

    # -------------------------------------------------------------------------
    # Section 1 — Aggregate stats
    # -------------------------------------------------------------------------
    print_section("SECTION 1 — Aggregate Stats")

    col_w = [22, 6, 14, 8, 10, 9, 10]
    headers = ["Mapper", "Docs", "Skills seen", "Mapped", "Unmapped", "Mapped%", "Avg Conf"]
    row_fmt = "{:<22} {:>6} {:>14} {:>8} {:>10} {:>9} {:>10}"

    print(row_fmt.format(*headers))
    print("-" * sum(col_w) + "-" * (len(col_w) - 1))

    agg_stats: dict[str, dict] = {}
    for name in mapper_names:
        doc_map = mapper_doc_maps[name]
        docs_count = len(doc_map)
        seen = 0
        mapped = 0
        unmapped = 0
        conf_sum = 0.0

        for skill_map in doc_map.values():
            for result in skill_map.values():
                seen += 1
                if result is not None:
                    mapped += 1
                    conf_sum += result[2]
                else:
                    unmapped += 1

        mapped_pct = (mapped / seen * 100) if seen > 0 else 0.0
        avg_conf = (conf_sum / mapped) if mapped > 0 else 0.0
        agg_stats[name] = dict(docs=docs_count, seen=seen, mapped=mapped, unmapped=unmapped,
                               mapped_pct=mapped_pct, avg_conf=avg_conf)
        print(row_fmt.format(
            name, docs_count, seen, mapped, unmapped,
            f"{mapped_pct:.1f}%", f"{avg_conf:.3f}"
        ))

    # -------------------------------------------------------------------------
    # Section 2 — Per-document summary
    # -------------------------------------------------------------------------
    print_section("SECTION 2 — Per-Document Summary")

    # Build header dynamically
    doc_header = ["Doc ID"]
    for name in mapper_names:
        short = name[:4]
        doc_header += [f"Skills({short})", f"Mapped({short})"]

    # Determine column widths
    doc_col_w = 20
    stat_col_w = 14
    header_line = f"{'Doc ID':<{doc_col_w}}" + "".join(f"{h:>{stat_col_w}}" for h in doc_header[1:])
    print(header_line)
    print("-" * len(header_line))

    for doc_id in all_doc_ids:
        row = f"{doc_id:<{doc_col_w}}"
        for name in mapper_names:
            skill_map = mapper_doc_maps[name].get(doc_id, {})
            skills_count = len(skill_map)
            mapped_count = sum(1 for v in skill_map.values() if v is not None)
            row += f"{skills_count:>{stat_col_w}}{mapped_count:>{stat_col_w}}"
        print(row)

    # -------------------------------------------------------------------------
    # Section 3 — Skill-level disagreement
    # -------------------------------------------------------------------------
    print_section("SECTION 3 — Skill-level Disagreement (top 30)")

    # For each skill that appears in >=2 mappers, collect assigned URIs
    skill_assignments: dict[str, dict[str, tuple | None]] = defaultdict(dict)

    for name in mapper_names:
        for skill_map in mapper_doc_maps[name].values():
            for skill, result in skill_map.items():
                skill_assignments[skill][name] = result

    # Filter to skills appearing in >=2 mappers
    multi_mapper_skills = {
        skill: assignments
        for skill, assignments in skill_assignments.items()
        if len(assignments) >= 2
    }

    # Count distinct URIs per skill (None counts as one distinct "unmapped" value)
    def distinct_uris(assignments: dict) -> int:
        uris = set()
        for result in assignments.values():
            uris.add(result[0] if result is not None else "__unmapped__")
        return len(uris)

    disagreements = sorted(
        multi_mapper_skills.items(),
        key=lambda x: distinct_uris(x[1]),
        reverse=True,
    )[:30]

    if not disagreements:
        print("  No skills appeared in 2+ mappers.")
    else:
        skill_col = 35
        mapper_col = 40
        header_parts = [f"{'Skill':<{skill_col}}"]
        for name in mapper_names:
            header_parts.append(f"{name:<{mapper_col}}")
        print("".join(header_parts))
        print("-" * (skill_col + mapper_col * len(mapper_names)))

        for skill, assignments in disagreements:
            # Truncate long skill strings
            skill_display = skill[:skill_col - 1] if len(skill) >= skill_col else skill
            row = f"{skill_display:<{skill_col}}"
            for name in mapper_names:
                result = assignments.get(name)
                if result is None and name not in assignments:
                    cell = "N/A"
                elif result is None:
                    cell = "unmapped"
                else:
                    uri, label, conf = result
                    cell = f"{short_uri(uri)} / {label}"
                    if len(cell) > mapper_col - 3:
                        cell = cell[: mapper_col - 4] + "…"
                row += f"{cell:<{mapper_col}}"
            print(row)

    # -------------------------------------------------------------------------
    # Optional CSV export
    # -------------------------------------------------------------------------
    if args.output_csv:
        csv_path = Path(args.output_csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for skill, assignments in skill_assignments.items():
            row = {"skill": skill}
            for name in mapper_names:
                result = assignments.get(name)
                if result is None and name not in assignments:
                    row[f"{name}_uri"] = "N/A"
                    row[f"{name}_label"] = "N/A"
                    row[f"{name}_conf"] = "N/A"
                elif result is None:
                    row[f"{name}_uri"] = "unmapped"
                    row[f"{name}_label"] = "unmapped"
                    row[f"{name}_conf"] = ""
                else:
                    uri, label, conf = result
                    row[f"{name}_uri"] = uri
                    row[f"{name}_label"] = label
                    row[f"{name}_conf"] = f"{conf:.4f}"
            rows.append(row)

        fieldnames = ["skill"] + [
            f"{name}_{field}"
            for name in mapper_names
            for field in ["uri", "label", "conf"]
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nCSV exported to: {csv_path}")


if __name__ == "__main__":
    main()
