import json
import os
import sqlite3
import logging

logger = logging.getLogger(__name__)


def _build_insights(conn):
    """Generate 3 market insight cards via Gemini and store in analytics_cache."""
    try:
        rows = {k: conn.execute(
            "SELECT data FROM analytics_cache WHERE key = ?", (k,)
        ).fetchone() for k in ('skill_demand', 'top_skills_20', 'overview')}

        if not all(rows.values()):
            logger.warning("[ANALYTICS] insights: missing cache data, skipping")
            return

        skill_demand = json.loads(rows['skill_demand'][0])
        top_skills   = json.loads(rows['top_skills_20'][0])
        overview     = json.loads(rows['overview'][0])

        total = sum(d['total_occurrences'] for d in skill_demand) or 1
        top_cats = [
            {
                'category': d['category'],
                'pct': round(d['total_occurrences'] * 100 / total),
                'top_skills': [s['skill'] for s in d.get('top_skills', [])[:3]],
            }
            for d in skill_demand[:6]
        ]
        top5 = [s['skill'] for s in top_skills[:5]]

        prompt = (
            "You are a labor market analyst. Based on real job posting data below, "
            "return a JSON array of exactly 3 insight cards.\n\n"
            f"Total postings: {overview.get('total_jobs', 0):,}\n"
            f"Organizations: {overview.get('total_organizations', 0)}\n"
            f"Unique ESCO skills: {overview.get('unique_skills', 0)}\n"
            f"Remote-eligible: {round(overview.get('remote_percentage') or 0)}%\n"
            f"Skill category breakdown: {json.dumps(top_cats)}\n"
            f"Top 5 skills by demand: {', '.join(top5)}\n\n"
            "Each card object must have:\n"
            '  "num"   — short metric derived from the data above (e.g. "38%", "12", "$94K")\n'
            '  "label" — 2-4 word title, ALL CAPS\n'
            '  "note"  — 1-2 sentences, max 25 words total, wrap one key term in <strong>…</strong>\n\n'
            "Return ONLY the JSON array, no markdown fences, no explanation."
        )

        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            logger.warning("[ANALYTICS] GEMINI_API_KEY not set — skipping insights")
            return

        from google import genai as _genai
        client = _genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            contents=prompt,
        )
        text = resp.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        insights = json.loads(text)
        _store(conn, 'market_insights', insights)
        logger.info("[ANALYTICS] market_insights cached via Gemini")
    except Exception:
        logger.exception("[ANALYTICS] insights build failed")


def _build_hero_stats(conn):
    """Generate 6 hero float stat cards via Gemini and store in analytics_cache."""
    try:
        keys = ('overview', 'skill_demand', 'skill_roi_20', 'locations')
        rows = {k: conn.execute(
            "SELECT data FROM analytics_cache WHERE key = ?", (k,)
        ).fetchone() for k in keys}

        if not rows['overview']:
            logger.warning("[ANALYTICS] hero_stats: missing overview, skipping")
            return

        overview     = json.loads(rows['overview'][0])
        skill_demand = json.loads(rows['skill_demand'][0]) if rows['skill_demand'] else []
        roi          = json.loads(rows['skill_roi_20'][0]) if rows['skill_roi_20'] else []
        locations    = json.loads(rows['locations'][0])    if rows['locations']    else []

        total_occ = sum(d['total_occurrences'] for d in skill_demand) or 1
        it_cat = next(
            (d for d in skill_demand if 'IT' in d.get('category', '') or 'Tech' in d.get('category', '')),
            None
        )
        it_pct       = round(it_cat['total_occurrences'] * 100 / total_occ) if it_cat else 0
        top_roi_skill = roi[0]['skill'] if roi else 'N/A'
        top_roi_sal   = round((roi[0].get('avg_min_salary') or 0) / 1000) if roi else 0
        avg_min       = round(overview.get('avg_salary', {}).get('min', 0) / 1000)
        avg_max       = round(overview.get('avg_salary', {}).get('max', 0) / 1000)

        data_summary = (
            f"Total postings: {overview.get('total_jobs', 0):,}\n"
            f"New this week: {overview.get('new_this_week', 0)}\n"
            f"Organizations: {overview.get('total_organizations', 0)}\n"
            f"Unique ESCO skills: {overview.get('unique_skills', 0)}\n"
            f"Remote-eligible: {round(overview.get('remote_percentage') or 0)}%\n"
            f"IT & Tech skill share: {it_pct}%\n"
            f"Avg annual salary: ${avg_min}K–${avg_max}K\n"
            f"Top ROI skill: {top_roi_skill} at avg ${top_roi_sal}K/yr\n"
            f"Countries tracked: {len(locations)}\n"
        )

        prompt = (
            "You are a labor market analyst. Based on real job posting data below, "
            "return a JSON array of exactly 6 hero stat cards.\n\n"
            f"{data_summary}\n"
            "Each card must have exactly these fields:\n"
            '  "val"   — short metric string derived from the data (e.g. "38%", "$94K", "12", "2.4K+")\n'
            '  "label" — 2–4 word label, ALL CAPS\n'
            '  "icon"  — one of exactly: trending, globe, dollar, layers, users, star\n'
            '  "color" — one of exactly: green, orange, blue, purple, cyan, pink\n\n'
            "Each stat must be unique and directly derived from the numbers above. "
            "Return ONLY the JSON array, no markdown fences, no explanation."
        )

        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            logger.warning("[ANALYTICS] GEMINI_API_KEY not set — skipping hero_stats")
            return

        from google import genai as _genai
        client = _genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            contents=prompt,
        )
        text = resp.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        stats = json.loads(text)
        _store(conn, 'hero_stats', stats)
        logger.info("[ANALYTICS] hero_stats cached via Gemini")
    except Exception:
        logger.exception("[ANALYTICS] hero_stats build failed")


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

    _build_insights(conn)
    _build_hero_stats(conn)
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
