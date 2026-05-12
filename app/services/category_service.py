from app.utils.database import get_db_connection
from app.utils.classifiers import get_series_name


class CategoryService:

    @staticmethod
    def get_categories_summary():
        conn = get_db_connection()
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM job_postings")
        total_jobs = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM job_postings WHERE series_code != ''")
        jobs_with_series = c.fetchone()[0]

        c.execute("""SELECT series_code, COUNT(*) as total, AVG(max_salary) as avg_salary,
            SUM(CASE WHEN telework_eligible THEN 1 ELSE 0 END)*100.0/MAX(COUNT(*),1) as remote_pct
            FROM job_postings WHERE series_code != '' GROUP BY series_code HAVING total > 0 ORDER BY total DESC LIMIT 20""")

        categories = [
            {
                "category": get_series_name(r["series_code"]),
                "series_code": r["series_code"],
                "total_postings": r["total"],
                "avg_salary": round(r["avg_salary"] or 0),
                "remote_percentage": round(r["remote_pct"] or 0, 1)
            }
            for r in c.fetchall()
        ]
        conn.close()
        return {
            "categories": categories,
            "coverage": {
                "total_jobs": total_jobs,
                "jobs_with_series": jobs_with_series,
                "coverage_pct": round(jobs_with_series / total_jobs * 100, 1) if total_jobs else 0
            }
        }

    @staticmethod
    def get_collection_status():
        conn = get_db_connection()
        c = conn.cursor()

        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='collection_log'")
        if not c.fetchone():
            conn.close()
            return []

        c.execute("SELECT series_code, series_name, total_found, jobs_collected, started_at, finished_at, status FROM collection_log ORDER BY started_at DESC LIMIT 20")
        results = [dict(r) for r in c.fetchall()]
        conn.close()
        return results
