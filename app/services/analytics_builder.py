import json
import sqlite3
import logging

logger = logging.getLogger(__name__)

CACHE_TABLE = """
    CREATE TABLE IF NOT EXISTS analytics_cache (
        key TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
"""


def _store(conn, key, data):
    conn.execute(
        "INSERT OR REPLACE INTO analytics_cache (key, data, updated_at) VALUES (?, ?, datetime('now'))",
        (key, json.dumps(data))
    )
    conn.commit()
    logger.info(f"[ANALYTICS] cached: {key}")


def refresh(db_path: str):
    conn = sqlite3.connect(db_path, timeout=600)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(CACHE_TABLE)

    try:
        total = conn.execute("SELECT COUNT(*) FROM job_postings").fetchone()[0]
        orgs = conn.execute("SELECT COUNT(DISTINCT organization) FROM job_postings").fetchone()[0]
        sal = conn.execute(
            "SELECT AVG(min_salary), AVG(max_salary) FROM job_postings WHERE salary_type='Per Year' AND min_salary > 20000"
        ).fetchone()
        remote_pct = conn.execute(
            "SELECT SUM(CASE WHEN telework_eligible THEN 1 ELSE 0 END)*100.0/MAX(COUNT(*),1) FROM job_postings"
        ).fetchone()[0]
        unique_skills = conn.execute("SELECT COUNT(DISTINCT skill_raw) FROM job_skills").fetchone()[0]
        new_this_week = conn.execute(
            "SELECT COUNT(*) FROM job_postings WHERE date_posted >= date('now','-7 days')"
        ).fetchone()[0]
        _store(conn, 'overview', {
            'total_jobs': total,
            'total_organizations': orgs,
            'avg_salary': {'min': round(sal[0] or 0), 'max': round(sal[1] or 0)},
            'remote_percentage': remote_pct or 0,
            'unique_skills': unique_skills,
            'new_this_week': new_this_week,
        })
    except Exception:
        logger.exception("[ANALYTICS] overview failed")

    try:
        rows = conn.execute("""
            SELECT COALESCE(skill_esco_label, skill_raw) AS skill,
                   skill_esco_type AS type,
                   skill_category AS category,
                   COUNT(*) AS count
            FROM job_skills WHERE skill_esco_label IS NOT NULL
            GROUP BY COALESCE(skill_esco_label, skill_raw)
            ORDER BY count DESC LIMIT 20
        """).fetchall()
        _store(conn, 'top_skills_20', [dict(r) for r in rows])
    except Exception:
        logger.exception("[ANALYTICS] top_skills failed")

    try:
        rows = conn.execute("""
            SELECT js.skill_category AS category,
                   ROUND(AVG(jp.min_salary)) AS avg_min_salary,
                   ROUND(AVG(jp.max_salary)) AS avg_max_salary,
                   COUNT(DISTINCT jp.position_id) AS job_count
            FROM job_skills js JOIN job_postings jp ON js.position_id = jp.position_id
            WHERE jp.salary_type = 'Per Year' AND jp.min_salary > 20000
              AND js.skill_category IS NOT NULL
            GROUP BY js.skill_category ORDER BY avg_min_salary DESC
        """).fetchall()
        _store(conn, 'category_salary', [dict(r) for r in rows])
    except Exception:
        logger.exception("[ANALYTICS] category_salary failed")

    try:
        cats = conn.execute("""
            SELECT skill_category, COUNT(*) AS total
            FROM job_skills WHERE skill_category IS NOT NULL
            GROUP BY skill_category ORDER BY total DESC
        """).fetchall()
        result = []
        for cat_row in cats:
            cat = cat_row['skill_category']
            top = conn.execute("""
                SELECT COALESCE(skill_esco_label, skill_raw) AS skill,
                       skill_esco_type AS type, COUNT(*) AS count
                FROM job_skills WHERE skill_category = ?
                GROUP BY COALESCE(skill_esco_label, skill_raw)
                ORDER BY count DESC LIMIT 5
            """, (cat,)).fetchall()
            result.append({
                'category': cat,
                'total_occurrences': cat_row['total'],
                'top_skills': [dict(r) for r in top],
            })
        _store(conn, 'skill_demand', result)
    except Exception:
        logger.exception("[ANALYTICS] skill_demand failed")

    try:
        rows = conn.execute("""
            SELECT COALESCE(js.skill_esco_label, js.skill_raw) AS skill,
                   js.skill_category AS category, js.skill_esco_type AS type,
                   ROUND(AVG(jp.min_salary)) AS avg_min_salary,
                   ROUND(AVG(jp.max_salary)) AS avg_max_salary,
                   COUNT(DISTINCT jp.position_id) AS job_count
            FROM job_skills js JOIN job_postings jp ON js.position_id = jp.position_id
            WHERE jp.salary_type = 'Per Year' AND jp.min_salary > 20000
              AND (js.skill_esco_label IS NOT NULL OR js.skill_raw IS NOT NULL)
            GROUP BY COALESCE(js.skill_esco_label, js.skill_raw)
            HAVING job_count > 30 ORDER BY avg_min_salary DESC LIMIT 20
        """).fetchall()
        _store(conn, 'skill_roi_20', [dict(r) for r in rows])
    except Exception:
        logger.exception("[ANALYTICS] skill_roi failed")

    try:
        for group_by in ('series', 'state', 'grade', 'department'):
            col_map = {
                'series': ('series_code', 15),
                'state': ('location_state', 20),
                'grade': ('job_grade', 50),
                'department': ('department', 15),
            }
            col, limit = col_map[group_by]
            rows = conn.execute(f"""
                SELECT {col} as label, COUNT(*) as count,
                       AVG(min_salary) as avg_min, AVG(max_salary) as avg_max
                FROM job_postings WHERE min_salary > 0 AND {col} != ''
                GROUP BY {col} HAVING count > 3 ORDER BY avg_max DESC LIMIT {limit}
            """).fetchall()
            _store(conn, f'salaries_{group_by}', [dict(r) for r in rows])
    except Exception:
        logger.exception("[ANALYTICS] salaries failed")

    try:
        rows = conn.execute("""
            SELECT location_state, COUNT(*) as count, AVG(max_salary) as avg_salary,
                   SUM(CASE WHEN telework_eligible THEN 1 ELSE 0 END) as remote_count
            FROM job_postings WHERE location_state != ''
            GROUP BY location_state ORDER BY count DESC LIMIT 20
        """).fetchall()
        _store(conn, 'locations', [dict(r) for r in rows])
    except Exception:
        logger.exception("[ANALYTICS] locations failed")

    conn.close()
    logger.info("[ANALYTICS] Refresh complete")


def get_cached(db_path: str, key: str):
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        row = conn.execute(
            "SELECT data FROM analytics_cache WHERE key = ?", (key,)
        ).fetchone()
        conn.close()
        return json.loads(row[0]) if row else None
    except Exception:
        return None
