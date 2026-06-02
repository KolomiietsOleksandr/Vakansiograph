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


def build_analytics():
    logger.info("=== [ANALYTICS] Building analytics cache ===")
    try:
        from app.services.analytics_builder import refresh
        refresh(DB_PATH)
    except Exception:
        logger.exception("[ANALYTICS] Failed")


def collect_jooble():
    logger.info("=== [JOOBLE] Starting Jooble data collection ===")
    if not os.environ.get("JOOBLE_API_KEY"):
        logger.warning("[JOOBLE] JOOBLE_API_KEY not set — skipping")
        return
    try:
        from app.services.parser_jooble import JoobleParser
        saved = JoobleParser().run()
        logger.info("[JOOBLE] Done: %d new jobs saved", saved)
    except Exception:
        logger.exception("[JOOBLE] Failed")


def extract_jooble_skills():
    logger.info("=== [JOOBLE-SKILLS] Extracting skills from Jooble jobs via Gemini ===")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        logger.warning("[JOOBLE-SKILLS] GEMINI_API_KEY not set — skipping")
        return
    try:
        import json
        import sqlite3 as _sqlite3
        from google import genai as _genai

        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        batch_size = 100

        conn = _sqlite3.connect(DB_PATH, timeout=60)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = _sqlite3.Row

        # Jooble jobs that have no skill_raw entries yet
        rows = conn.execute("""
            SELECT jp.position_id, jp.title, jp.qualification_summary
            FROM job_postings jp
            WHERE jp.job_type = 'Jooble'
              AND jp.position_id NOT IN (SELECT DISTINCT position_id FROM job_skills)
        """).fetchall()

        if not rows:
            logger.info("[JOOBLE-SKILLS] No unprocessed Jooble jobs — nothing to do")
            conn.close()
            return

        logger.info("[JOOBLE-SKILLS] Processing %d jobs in batches of %d", len(rows), batch_size)
        client = _genai.Client(api_key=gemini_key)
        total_skills = 0

        for i in range(0, len(rows), batch_size):
            batch = rows[i: i + batch_size]
            postings = [
                {"id": r["position_id"], "title": r["title"], "text": r["qualification_summary"] or ""}
                for r in batch
            ]
            prompt = (
                "You are a skill extraction expert. "
                "Extract professional skills from Ukrainian job postings. "
                "Return skill names in English (translate from Ukrainian when needed). "
                "Include: programming languages, tools, frameworks, methodologies, "
                "domain skills, soft skills, certifications.\n\n"
                f"Job postings: {json.dumps(postings, ensure_ascii=False)}\n\n"
                'Return ONLY valid JSON: '
                '{"results": [{"id": "<position_id>", "skills": ["skill1", "skill2"]}]}'
            )
            try:
                resp = client.models.generate_content(model=gemini_model, contents=prompt)
                text = resp.text.strip()
                if text.startswith("```"):
                    text = text.split("```")[1].lstrip("json").strip()
                data = json.loads(text)
                for r in data.get("results", []):
                    for skill in r.get("skills", []):
                        skill = skill.strip()
                        if not skill:
                            continue
                        try:
                            conn.execute(
                                "INSERT INTO job_skills (position_id, skill_raw) VALUES (?,?)",
                                (r["id"], skill),
                            )
                            total_skills += 1
                        except Exception:
                            pass
                conn.commit()
                logger.info(
                    "[JOOBLE-SKILLS] batch %d/%d done",
                    min(i + batch_size, len(rows)), len(rows),
                )
            except Exception:
                logger.exception("[JOOBLE-SKILLS] Gemini batch failed, continuing")

        conn.close()
        logger.info("[JOOBLE-SKILLS] Done: %d skills extracted", total_skills)
    except Exception:
        logger.exception("[JOOBLE-SKILLS] Failed")


def _trigger_warm():
    web_url = os.environ.get("WEB_INTERNAL_URL", "http://web:5001")
    try:
        import requests as _requests
        _requests.post(f"{web_url}/api/admin/warm-cache", timeout=10)
        logger.info("[WARMER] Cache warm-up triggered")
    except Exception:
        logger.warning("[WARMER] Could not trigger cache warm-up")


def warm_cache_only():
    logger.info("=== [WARMER] Periodic cache warm ===")
    _trigger_warm()


def flush_and_warm_cache():
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis as _redis
        r = _redis.from_url(redis_url)
        keys = r.keys("vkg_*")
        if keys:
            r.delete(*keys)
        logger.info("[PIPELINE] Flushed %d Redis cache keys", len(keys))
    except Exception:
        logger.warning("[PIPELINE] Could not flush Redis cache")
    _trigger_warm()


def pipeline():
    logger.info("=== [PIPELINE] Starting full pipeline ===")
    collect_jobs()
    collect_adzuna()
    collect_jooble()
    extract_jooble_skills()
    enrich_skills()
    build_analytics()
    flush_and_warm_cache()
    logger.info("=== [PIPELINE] Done ===")


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
        pipeline,
        trigger=IntervalTrigger(hours=2),
        id="pipeline",
        name="Full Pipeline: collect → enrich → analytics (every 2h)",
        next_run_time=datetime.now(timezone.utc),
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
    scheduler.add_job(
        warm_cache_only,
        trigger=IntervalTrigger(seconds=540),
        id="cache-warmer",
        name="Periodic Cache Warmer (every 540s)",
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30),
        max_instances=1,
        coalesce=True,
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
    start_scheduler()
