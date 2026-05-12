import os
import logging
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

API_KEY = os.environ.get("USAJOBS_API_KEY", "")
EMAIL   = os.environ.get("USAJOBS_EMAIL", "")
DB_PATH = os.environ.get("DATABASE_PATH", os.environ.get("DB_PATH", "app/labor_market.db"))


def collect_jobs():
    logger.info("=== [COLLECT] Starting USAJOBS data collection ===")
    if not API_KEY:
        logger.error("[COLLECT] USAJOBS_API_KEY not set — skipping")
        return
    try:
        from app.services.usajobs_client_all import USAJobsClient, DataCollector
        client    = USAJobsClient(api_key=API_KEY, email=EMAIL)
        collector = DataCollector(client, db_path=DB_PATH)
        result    = collector.collect_all(max_pages=20, date_posted=90)
        logger.info(f"[COLLECT] Done: {result}")
    except Exception:
        logger.exception("[COLLECT] Failed")


def collect_adzuna():
    logger.info("=== [ADZUNA] Starting Adzuna data collection ===")
    adzuna_id  = os.environ.get("ADZUNA_APP_ID", "")
    adzuna_key = os.environ.get("ADZUNA_APP_KEY", "")
    if not adzuna_id or not adzuna_key:
        logger.warning("[ADZUNA] ADZUNA_APP_ID / ADZUNA_APP_KEY not set — skipping")
        return
    try:
        from app.services.parser_adjuna import AdzunaParser
        AdzunaParser().run()
        logger.info("[ADZUNA] Done")
    except Exception:
        logger.exception("[ADZUNA] Failed")


def enrich_skills():
    logger.info("=== [ENRICH] Starting ESCO skill enrichment ===")
    try:
        import sqlite3
        from app.services.esco_enricher_v2 import map_skills

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.execute("""
            SELECT skill_raw, COUNT(*) as cnt
            FROM job_skills
            WHERE (skill_esco_uri IS NULL OR skill_esco_uri = '')
              AND skill_raw IS NOT NULL AND skill_raw != ''
            GROUP BY skill_raw
            ORDER BY cnt DESC
        """)
        unmapped = [row["skill_raw"] for row in cur.fetchall()]
        conn.close()

        if not unmapped:
            logger.info("[ENRICH] No unmapped skills — nothing to do")
            return

        logger.info("[ENRICH] Mapping %d new unique skills…", len(unmapped))
        mappings = map_skills(unmapped)

        conn = sqlite3.connect(DB_PATH)
        updated = 0
        for skill_raw, m in mappings.items():
            if m is None:
                continue
            conn.execute("""
                UPDATE job_skills
                SET skill_esco_uri   = ?,
                    skill_esco_label = ?,
                    skill_esco_type  = ?,
                    skill_category   = ?
                WHERE skill_raw = ?
            """, (m["esco_uri"], m["esco_label"], m["esco_type"], m["skill_category"], skill_raw))
            updated += 1
        conn.commit()
        conn.close()

        logger.info("[ENRICH] Done: %d/%d skills mapped", updated, len(unmapped))
    except Exception:
        logger.exception("[ENRICH] Failed")


def cleanup():
    logger.info("=== [CLEANUP] Starting weekly cleanup ===")
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute("DELETE FROM job_postings WHERE date_posted < date('now', '-90 days')")
        deleted = cur.rowcount
        cur.execute("""
            DELETE FROM job_skills
            WHERE position_id NOT IN (SELECT position_id FROM job_postings)
        """)
        orphans = cur.rowcount
        conn.commit()
        conn.close()
        logger.info(f"[CLEANUP] Removed {deleted} postings, {orphans} orphan skill records")
    except Exception:
        logger.exception("[CLEANUP] Failed")


def start_scheduler():
    scheduler = BlockingScheduler(timezone="UTC")

    scheduler.add_job(
        collect_jobs,
        trigger=IntervalTrigger(hours=6),
        id="collect_jobs",
        name="USAJOBS Collection (every 6h)",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        collect_adzuna,
        trigger=IntervalTrigger(hours=6, start_date=datetime.now(timezone.utc) + timedelta(hours=3)),
        id="collect_adzuna",
        name="Adzuna Collection (every 6h, offset +3h)",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enrich_skills,
        trigger=CronTrigger(hour=3, minute=0),
        id="enrich_skills",
        name="ESCO Skill Enrichment (daily 03:00 UTC)",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        cleanup,
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0),
        id="cleanup",
        name="Weekly Cleanup (Sun 02:00 UTC)",
        max_instances=1,
    )

    logger.info("=" * 55)
    logger.info("VakansioGraph Worker — Scheduler started")
    logger.info(f"DB: {DB_PATH}")
    for job in scheduler.get_jobs():
        logger.info(f"  {job.name}")
    logger.info("=" * 55)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    collect_jobs()
    collect_adzuna()
    enrich_skills()
    start_scheduler()
