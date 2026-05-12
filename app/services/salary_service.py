from app.utils.database import get_db_connection
from app.utils.classifiers import get_series_name


class SalaryService:

    @staticmethod
    def get_salaries(group_by: str = "department"):
        conn = get_db_connection()
        c = conn.cursor()

        if group_by == "series":
            c.execute("""SELECT series_code as label, COUNT(*) as count, AVG(min_salary) as avg_min, AVG(max_salary) as avg_max
                FROM job_postings WHERE min_salary > 0 AND series_code != '' GROUP BY series_code HAVING count > 3 ORDER BY avg_max DESC LIMIT 15""")
            results = []
            for r in c.fetchall():
                d = dict(r)
                d["label"] = get_series_name(d["label"])
                results.append(d)

        elif group_by == "state":
            c.execute("""SELECT location_state as label, COUNT(*) as count, AVG(min_salary) as avg_min, AVG(max_salary) as avg_max
                FROM job_postings WHERE min_salary > 0 AND location_state != '' GROUP BY location_state HAVING count > 3 ORDER BY avg_max DESC LIMIT 20""")
            results = [dict(r) for r in c.fetchall()]

        elif group_by == "grade":
            c.execute("""SELECT job_grade as label, COUNT(*) as count, AVG(min_salary) as avg_min, AVG(max_salary) as avg_max
                FROM job_postings WHERE min_salary > 0 AND job_grade != '' GROUP BY job_grade ORDER BY avg_max DESC""")
            results = [dict(r) for r in c.fetchall()]

        else:
            c.execute("""SELECT department as label, COUNT(*) as count, AVG(min_salary) as avg_min, AVG(max_salary) as avg_max
                FROM job_postings WHERE min_salary > 0 AND department != '' GROUP BY department HAVING count > 3 ORDER BY avg_max DESC LIMIT 15""")
            results = [dict(r) for r in c.fetchall()]

        conn.close()
        return results
