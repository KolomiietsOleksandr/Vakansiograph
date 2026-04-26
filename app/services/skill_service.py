"""
Skills-related database services
"""

from app.utils.database import get_db_connection
from app.utils.classifiers import classify_skill_type


class SkillService:
    """Service for skills-related queries"""

    @staticmethod
    def get_top_skills(limit: int = 20, country: str = "ALL"):
        """Get most frequent skills, preferring ESCO labels and types when available.
        Optionally filter by location_country (2-letter code or 'ALL')."""
        conn = get_db_connection()
        c = conn.cursor()

        if country == "ALL":
            c.execute("""
                SELECT
                    COALESCE(skill_esco_label, skill_raw) as display_label,
                    skill_raw,
                    skill_esco_type,
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
                "count": r["count"]
            }
            for r in c.fetchall()
        ]
        conn.close()
        return results
