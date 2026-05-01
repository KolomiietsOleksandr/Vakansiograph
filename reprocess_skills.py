"""
Re-enrich all unique skills in job_skills using the skills2-main pipeline.

Usage:
    python reprocess_skills.py              # re-enrich all 1603 unique skills
    python reprocess_skills.py --dry-run    # show what would change, no DB writes
    python reprocess_skills.py --batch 50   # custom batch size (default 100)
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# ── Bootstrap ─────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Load .env so GEMINI_API_KEY is available before importing the enricher
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_unique_skills(conn) -> list[tuple[str, int]]:
    """Return (skill_raw, occurrence_count) sorted by frequency desc."""
    cur = conn.cursor()
    cur.execute("""
        SELECT skill_raw, COUNT(*) AS cnt
        FROM job_skills
        WHERE skill_raw IS NOT NULL AND skill_raw != ''
        GROUP BY skill_raw
        ORDER BY cnt DESC
    """)
    return [(row["skill_raw"], row["cnt"]) for row in cur.fetchall()]


def update_skills(conn, mappings: dict, dry_run: bool) -> int:
    """Write enrichment results back to job_skills. Returns rows updated."""
    cur = conn.cursor()
    updated = 0
    for skill_raw, m in mappings.items():
        if m is None:
            continue
        if dry_run:
            logger.info(
                "  [DRY] %-30s → %-40s  (%.2f, %s, %s)",
                skill_raw, m["esco_label"], m["confidence"],
                m["method"], m["skill_category"],
            )
        else:
            cur.execute("""
                UPDATE job_skills
                SET skill_esco_uri   = ?,
                    skill_esco_label = ?,
                    skill_esco_type  = ?,
                    skill_category   = ?
                WHERE skill_raw = ?
            """, (
                m["esco_uri"],
                m["esco_label"],
                m["esco_type"],
                m["skill_category"],
                skill_raw,
            ))
        updated += 1
    if not dry_run:
        conn.commit()
    return updated


def main():
    parser = argparse.ArgumentParser(description="Re-enrich job_skills with skills2-main pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Print changes, do not write to DB")
    parser.add_argument("--batch", type=int, default=100, help="Batch size per pipeline call")
    args = parser.parse_args()

    # ── Import after env is loaded ─────────────────────────────────────────────
    from app.utils.database import get_db_connection
    from app.services.esco_enricher_v2 import map_skills

    conn = get_db_connection()
    all_skills = get_unique_skills(conn)
    conn.close()

    total = len(all_skills)
    logger.info("Found %d unique skills across all job_skills records", total)
    if args.dry_run:
        logger.info("DRY RUN — no changes will be written to the database")

    total_mapped = 0
    total_unchanged = 0
    batch_size = args.batch

    for batch_start in range(0, total, batch_size):
        batch = all_skills[batch_start : batch_start + batch_size]
        skill_raws = [s for s, _ in batch]
        batch_num = batch_start // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size

        logger.info("── Batch %d/%d  (%d skills) ──", batch_num, total_batches, len(skill_raws))

        mappings = map_skills(skill_raws)

        conn = get_db_connection()
        updated = update_skills(conn, mappings, dry_run=args.dry_run)
        conn.close()

        unmapped = sum(1 for m in mappings.values() if m is None)
        total_mapped += updated
        total_unchanged += unmapped
        logger.info(
            "  Batch result: %d mapped, %d unmapped",
            updated, unmapped,
        )

    logger.info("═══════════════════════════════════════")
    logger.info("TOTAL  mapped:   %d / %d unique skills", total_mapped, total)
    logger.info("TOTAL  unmapped: %d / %d unique skills", total_unchanged, total)
    logger.info(
        "DB rows affected: ~%d  (all occurrences of mapped skills)",
        total_mapped,
    )
    if args.dry_run:
        logger.info("DRY RUN — rerun without --dry-run to apply changes")


if __name__ == "__main__":
    main()
