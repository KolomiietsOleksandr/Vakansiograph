from app.utils.database import get_db_connection


class JobService:

    @staticmethod
    def get_overview():
        conn = get_db_connection()
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM job_postings")
        total = c.fetchone()[0]

        c.execute("SELECT COUNT(DISTINCT organization) FROM job_postings")
        orgs = c.fetchone()[0]

        c.execute("""SELECT AVG(min_salary), AVG(max_salary) FROM job_postings
                     WHERE salary_type = 'Per Year' AND min_salary > 20000""")
        r = c.fetchone()
        avg_sal = {"min": round(r[0] or 0), "max": round(r[1] or 0)}

        c.execute("SELECT SUM(CASE WHEN telework_eligible THEN 1 ELSE 0 END)*100.0/MAX(COUNT(*),1) FROM job_postings")
        remote = round(c.fetchone()[0] or 0, 1)

        c.execute("SELECT COUNT(DISTINCT skill_raw) FROM job_skills")
        skills = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM job_postings WHERE date_posted >= date('now','-7 days')")
        week = c.fetchone()[0]
        if week == 0:
            week = total

        conn.close()

        return {
            "total_jobs": total,
            "total_organizations": orgs,
            "avg_salary": avg_sal,
            "remote_percentage": remote,
            "unique_skills": skills,
            "new_this_week": week
        }

    @staticmethod
    def get_recent_jobs(limit: int = 20, keyword: str = ""):
        conn = get_db_connection()
        c = conn.cursor()

        if keyword:
            c.execute("""SELECT position_id, title, organization, department, location_city, location_state,
                min_salary, max_salary, salary_type, job_grade, series_code, telework_eligible, date_posted, url
                FROM job_postings WHERE title LIKE ? OR qualification_summary LIKE ? ORDER BY date_posted DESC LIMIT ?""",
                (f"%{keyword}%", f"%{keyword}%", limit))
        else:
            c.execute("""SELECT position_id, title, organization, department, location_city, location_state,
                min_salary, max_salary, salary_type, job_grade, series_code, telework_eligible, date_posted, url
                FROM job_postings ORDER BY date_posted DESC LIMIT ?""", (limit,))

        results = [dict(r) for r in c.fetchall()]
        conn.close()
        return results
