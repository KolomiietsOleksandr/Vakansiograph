import json
import logging
import sys
from pathlib import Path

from rapidfuzz import fuzz

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATASET_PATH = Path("tests/golden/mapping_dataset.json")
LABEL_MATCH_THRESHOLD = 80  # rapidfuzz token_sort_ratio


def _load_dataset() -> dict:
    with open(DATASET_PATH) as f:
        return json.load(f)


def _init_index():
    import os
    from esco_pipeline.esco_interface import ESCOIndex

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    esco_dir = Path("esco")
    if not esco_dir.exists():
        logger.error("ESCO data directory not found at ./esco/. Download ESCO v1.2.1 CSV files first.")
        sys.exit(1)

    logger.info("Loading ESCO index (language=en)…")
    index = ESCOIndex(
        data_dir=".",
        language="en",
        gemini_api_key=gemini_key,
        cache_dir=".cache/esco",
        embedding_title_weight=0.6,
    )
    logger.info("Index ready: %d labels", len(index.get_all_labels()))
    return index


def _best_candidate(index, raw_skill: str) -> tuple[str, str, float] | None:
    """Return (uri, label, score) for the best fuzzy candidate, or None."""
    all_labels = index.get_all_labels()  # label_lower -> uri
    from rapidfuzz import process

    matches = process.extract(
        raw_skill.lower(), list(all_labels.keys()),
        scorer=fuzz.token_sort_ratio, limit=3,
    )
    if not matches:
        return None
    best_label, score, _ = matches[0]
    uri = all_labels[best_label]
    skill_obj = index.get_skill(uri)
    label = skill_obj.preferred_label if skill_obj else best_label
    return uri, label, score / 100.0


def main():
    approve = "--approve" in sys.argv
    dataset = _load_dataset()
    index = _init_index()

    entries = dataset["entries"]
    proposals: list[dict] = []

    for entry in entries:
        if entry.get("expected_uri"):
            proposals.append({**entry, "_proposed_uri": entry["expected_uri"], "_proposed_label": entry["expected_label"], "_match": 1.0, "_action": "already set"})
            continue

        if entry.get("expected_label") is None:
            proposals.append({**entry, "_proposed_uri": None, "_proposed_label": None, "_match": None, "_action": "skip (null expected)"})
            continue

        result = _best_candidate(index, entry["raw_skill"])
        if result is None:
            proposals.append({**entry, "_proposed_uri": None, "_proposed_label": None, "_match": 0.0, "_action": "no candidate"})
            continue

        uri, label, _score = result
        label_match = fuzz.token_sort_ratio(label.lower(), entry["expected_label"].lower()) / 100.0
        action = "approve" if label_match >= LABEL_MATCH_THRESHOLD / 100 else "review"
        proposals.append({
            **entry,
            "_proposed_uri": uri,
            "_proposed_label": label,
            "_match": round(label_match, 3),
            "_action": action,
        })

    print(f"\n{'ID':<12} {'Raw skill':<40} {'Expected label':<35} {'Proposed label':<35} {'Match':>6} {'Action':<10}")
    print("-" * 145)
    for p in proposals:
        print(
            f"{p['id']:<12} {p['raw_skill']:<40} {str(p.get('expected_label','')):<35} "
            f"{str(p.get('_proposed_label','')):<35} {str(p.get('_match',''))[:5]:>6} {p['_action']:<10}"
        )

    approvable = [p for p in proposals if p["_action"] == "approve"]
    need_review = [p for p in proposals if p["_action"] == "review"]
    already_set = [p for p in proposals if p["_action"] == "already set"]
    skipped = [p for p in proposals if p["_action"] in ("skip (null expected)", "no candidate")]

    print(f"\nSummary: {len(already_set)} already set | {len(approvable)} auto-approvable | {len(need_review)} need review | {len(skipped)} skipped")

    if not approve:
        print("\nRe-run with --approve to write auto-approvable URIs into the dataset.")
        return

    updated = 0
    for entry in entries:
        proposal = next((p for p in proposals if p["id"] == entry["id"]), None)
        if proposal and proposal["_action"] == "approve":
            entry["expected_uri"] = proposal["_proposed_uri"]
            updated += 1

    with open(DATASET_PATH, "w") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {updated} URIs to {DATASET_PATH}.")
    if need_review:
        print(f"Still need manual review ({len(need_review)} entries):")
        for p in need_review:
            print(f"  [{p['id']}] {p['raw_skill']!r}  →  proposed: {p['_proposed_label']!r} (match {p['_match']})")


if __name__ == "__main__":
    main()
