from app.utils.database import get_db_connection
from app.utils.classifiers import classify_skill_type


class SkillService:

    @staticmethod
    def get_top_skills(limit: int = 20, country: str = "ALL"):
        conn = get_db_connection()
        c = conn.cursor()

        if country == "ALL":
            c.execute("""
                SELECT
                    COALESCE(skill_esco_label, skill_raw) as display_label,
                    skill_raw,
                    skill_esco_type,
                    skill_category,
                    COUNT(*) as count
                FROM job_skills
                GROUP BY COALESCE(skill_esco_label, skill_raw)
                ORDER BY count DESC
                LIMIT ?
            """, (limit,))
        else:
            c.execute("""
                SELECT
                    COALESCE(js.skill_esco_label, js.skill_raw) as display_label,
                    js.skill_raw,
                    js.skill_esco_type,
                    js.skill_category,
                    COUNT(*) as count
                FROM job_skills js
                JOIN job_postings jp ON js.position_id = jp.position_id
                WHERE jp.location_country = ?
                GROUP BY COALESCE(js.skill_esco_label, js.skill_raw)
                ORDER BY count DESC
                LIMIT ?
            """, (country, limit))

        results = [
            {
                "skill": r["display_label"].title(),
                "type": r["skill_esco_type"] if r["skill_esco_type"]
                        else classify_skill_type(r["skill_raw"]),
                "category": r["skill_category"] or "Other",
                "count": r["count"]
            }
            for r in c.fetchall()
        ]
        conn.close()
        return results
