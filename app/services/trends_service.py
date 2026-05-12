from app.utils.database import get_db_connection
from app.config import Config


class TrendsService:

    @staticmethod
    def get_skill_salary_roi(limit: int = 20):
        if limit == 20:
            from app.services.analytics_builder import get_cached
            cached = get_cached(Config.DATABASE_PATH, 'skill_roi_20')
            if cached is not None:
                return cached

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT
                COALESCE(js.skill_esco_label, js.skill_raw) AS skill,
                js.skill_category                           AS category,
                js.skill_esco_type                         AS type,
                ROUND(AVG(jp.min_salary))                  AS avg_min_salary,
                ROUND(AVG(jp.max_salary))                  AS avg_max_salary,
                COUNT(DISTINCT jp.position_id)             AS job_count
            FROM job_skills js
            JOIN job_postings jp ON js.position_id = jp.position_id
            WHERE jp.salary_type = 'Per Year'
              AND jp.min_salary  > 20000
              AND (js.skill_esco_label IS NOT NULL OR js.skill_raw IS NOT NULL)
            GROUP BY COALESCE(js.skill_esco_label, js.skill_raw)
            HAVING job_count > 30
            ORDER BY avg_min_salary DESC
            LIMIT ?
        """, (limit,))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_category_salary():
        from app.services.analytics_builder import get_cached
        cached = get_cached(Config.DATABASE_PATH, 'category_salary')
        if cached is not None:
            return cached

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT
                js.skill_category                AS category,
                ROUND(AVG(jp.min_salary))        AS avg_min_salary,
                ROUND(AVG(jp.max_salary))        AS avg_max_salary,
                COUNT(DISTINCT jp.position_id)   AS job_count
            FROM job_skills js
            JOIN job_postings jp ON js.position_id = jp.position_id
            WHERE jp.salary_type = 'Per Year'
              AND jp.min_salary  > 20000
              AND js.skill_category IS NOT NULL
            GROUP BY js.skill_category
            ORDER BY avg_min_salary DESC
        """)
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_skill_demand_by_category():
        from app.services.analytics_builder import get_cached
        cached = get_cached(Config.DATABASE_PATH, 'skill_demand')
        if cached is not None:
            return cached

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT skill_category, total_occurrences
            FROM (
                SELECT skill_category, SUM(cnt) AS total_occurrences
                FROM (
                    SELECT skill_category, COUNT(*) AS cnt
                    FROM job_skills
                    WHERE skill_category IS NOT NULL
                    GROUP BY skill_category
                )
                GROUP BY skill_category
            )
            ORDER BY total_occurrences DESC
        """)
        categories = {r["skill_category"]: r["total_occurrences"] for r in c.fetchall()}

        result = []
        for cat, total in categories.items():
            c.execute("""
                SELECT COALESCE(skill_esco_label, skill_raw) AS skill,
                       skill_esco_type AS type,
                       COUNT(*) AS count
                FROM job_skills
                WHERE skill_category = ?
                GROUP BY COALESCE(skill_esco_label, skill_raw)
                ORDER BY count DESC
                LIMIT 5
            """, (cat,))
            result.append({
                "category": cat,
                "total_occurrences": total,
                "top_skills": [dict(r) for r in c.fetchall()]
            })

        conn.close()
        return sorted(result, key=lambda x: -x["total_occurrences"])

    @staticmethod
    def get_posting_volume_by_month():
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT
                substr(date_posted, 1, 7) AS month,
                COUNT(*)                 AS count
            FROM job_postings
            WHERE date_posted IS NOT NULL
              AND length(date_posted) >= 7
            GROUP BY month
            ORDER BY month DESC
            LIMIT 24
        """)
        rows = c.fetchall()
        conn.close()
        return [{"month": r["month"], "count": r["count"]} for r in reversed(rows)]

    @staticmethod
    def get_available_countries():
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT location_country, COUNT(*) AS count
            FROM job_postings
            WHERE location_country IS NOT NULL AND location_country != ''
            GROUP BY location_country
            ORDER BY count DESC
        """)
        rows = c.fetchall()
        conn.close()
        return [{"country": r["location_country"], "count": r["count"]} for r in rows]

    @staticmethod
    def get_skill_timeline(skill: str, country: str = "ALL"):
        conn = get_db_connection()
        c = conn.cursor()
        if country == "ALL":
            c.execute("""
                SELECT
                    substr(jp.date_posted, 1, 7) AS month,
                    COUNT(DISTINCT jp.position_id) AS count
                FROM job_skills js
                JOIN job_postings jp ON js.position_id = jp.position_id
                WHERE LOWER(COALESCE(js.skill_esco_label, js.skill_raw)) = LOWER(?)
                  AND jp.date_posted IS NOT NULL
                  AND length(jp.date_posted) >= 7
                GROUP BY month
                ORDER BY month ASC
            """, (skill,))
        else:
            c.execute("""
                SELECT
                    substr(jp.date_posted, 1, 7) AS month,
                    COUNT(DISTINCT jp.position_id) AS count
                FROM job_skills js
                JOIN job_postings jp ON js.position_id = jp.position_id
                WHERE LOWER(COALESCE(js.skill_esco_label, js.skill_raw)) = LOWER(?)
                  AND jp.location_country = ?
                  AND jp.date_posted IS NOT NULL
                  AND length(jp.date_posted) >= 7
                GROUP BY month
                ORDER BY month ASC
            """, (skill, country))
        rows = c.fetchall()
        conn.close()
        return [{"month": r["month"], "count": r["count"]} for r in rows]

    @staticmethod
    def get_country_stats(country: str = "ALL"):
        conn = get_db_connection()
        c = conn.cursor()
        if country == "ALL":
            c.execute("""
                SELECT COUNT(*) AS total_jobs,
                       COUNT(DISTINCT organization) AS total_orgs,
                       MIN(date_posted) AS oldest,
                       MAX(date_posted) AS newest
                FROM job_postings
            """)
        else:
            c.execute("""
                SELECT COUNT(*) AS total_jobs,
                       COUNT(DISTINCT organization) AS total_orgs,
                       MIN(date_posted) AS oldest,
                       MAX(date_posted) AS newest
                FROM job_postings
                WHERE location_country = ?
            """, (country,))
        row = c.fetchone()

        if country == "ALL":
            c.execute("SELECT COUNT(DISTINCT COALESCE(skill_esco_label, skill_raw)) FROM job_skills")
        else:
            c.execute("""
                SELECT COUNT(DISTINCT COALESCE(js.skill_esco_label, js.skill_raw))
                FROM job_skills js
                JOIN job_postings jp ON js.position_id = jp.position_id
                WHERE jp.location_country = ?
            """, (country,))
        skill_count = c.fetchone()[0]
        conn.close()
        return {
            "total_jobs": row["total_jobs"],
            "total_orgs": row["total_orgs"],
            "unique_skills": skill_count,
            "oldest": row["oldest"],
            "newest": row["newest"],
        }

    @staticmethod
    def get_posting_volume_by_country(country: str = "ALL"):
        conn = get_db_connection()
        c = conn.cursor()
        if country == "ALL":
            c.execute("""
                SELECT substr(date_posted, 1, 7) AS month, COUNT(*) AS count
                FROM job_postings
                WHERE date_posted IS NOT NULL AND length(date_posted) >= 7
                GROUP BY month ORDER BY month DESC LIMIT 24
            """)
        else:
            c.execute("""
                SELECT substr(date_posted, 1, 7) AS month, COUNT(*) AS count
                FROM job_postings
                WHERE date_posted IS NOT NULL AND length(date_posted) >= 7
                  AND location_country = ?
                GROUP BY month ORDER BY month DESC LIMIT 24
            """, (country,))
        rows = c.fetchall()
        conn.close()
        return [{"month": r["month"], "count": r["count"]} for r in reversed(rows)]

    @staticmethod
    def get_skill_country_breakdown(skill: str):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT jp.location_country AS country,
                   COUNT(DISTINCT jp.position_id) AS count
            FROM job_skills js
            JOIN job_postings jp ON js.position_id = jp.position_id
            WHERE LOWER(COALESCE(js.skill_esco_label, js.skill_raw)) = LOWER(?)
              AND jp.location_country IS NOT NULL AND jp.location_country != ''
            GROUP BY jp.location_country
            ORDER BY count DESC
            LIMIT 20
        """, (skill,))
        rows = c.fetchall()
        conn.close()
        return [{"country": r["country"], "count": r["count"]} for r in rows]

    @staticmethod
    def get_skill_detail(skill: str):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT COALESCE(skill_esco_label, skill_raw) AS skill,
                   skill_esco_label AS esco_label,
                   skill_esco_type  AS type,
                   skill_category   AS category,
                   skill_esco_uri   AS uri,
                   COUNT(*)                       AS total_occurrences,
                   COUNT(DISTINCT position_id)    AS job_count
            FROM job_skills
            WHERE LOWER(COALESCE(skill_esco_label, skill_raw)) = LOWER(?)
            GROUP BY COALESCE(skill_esco_label, skill_raw)
            LIMIT 1
        """, (skill,))
        row = c.fetchone()
        if not row:
            conn.close()
            return None
        result = dict(row)

        c.execute("""
            SELECT ROUND(AVG(jp.min_salary)) AS avg_min,
                   ROUND(AVG(jp.max_salary)) AS avg_max
            FROM job_skills js
            JOIN job_postings jp ON js.position_id = jp.position_id
            WHERE LOWER(COALESCE(js.skill_esco_label, js.skill_raw)) = LOWER(?)
              AND jp.salary_type = 'Per Year' AND jp.min_salary > 20000
        """, (skill,))
        sal = c.fetchone()
        result["avg_min_salary"] = sal["avg_min"] if sal else None
        result["avg_max_salary"] = sal["avg_max"] if sal else None

        if result.get("category"):
            c.execute("""
                SELECT COALESCE(skill_esco_label, skill_raw) AS skill,
                       COUNT(*) AS count
                FROM job_skills
                WHERE skill_category = ?
                  AND LOWER(COALESCE(skill_esco_label, skill_raw)) != LOWER(?)
                GROUP BY COALESCE(skill_esco_label, skill_raw)
                ORDER BY count DESC LIMIT 8
            """, (result["category"], skill))
            result["related_skills"] = [dict(r) for r in c.fetchall()]
        else:
            result["related_skills"] = []

        conn.close()
        return result

    @staticmethod
    def get_top_skills_by_category(category: str, limit: int = 10):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT
                COALESCE(skill_esco_label, skill_raw) AS skill,
                skill_esco_type                       AS type,
                skill_esco_uri                        AS uri,
                COUNT(*)                              AS count
            FROM job_skills
            WHERE skill_category = ?
            GROUP BY COALESCE(skill_esco_label, skill_raw)
            ORDER BY count DESC
            LIMIT ?
        """, (category, limit))
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]
