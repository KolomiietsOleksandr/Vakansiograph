"""
Location-related database services
"""

from app.utils.database import get_db_connection


class LocationService:
    """Service for location-related queries"""

    @staticmethod
    def get_locations():
        """Get job statistics by location"""
        conn = get_db_connection()
        c = conn.cursor()

        c.execute("""SELECT location_state, COUNT(*) as count, AVG(max_salary) as avg_salary,
            SUM(CASE WHEN telework_eligible THEN 1 ELSE 0 END) as remote_count
            FROM job_postings WHERE location_state != '' GROUP BY location_state ORDER BY count DESC LIMIT 20""")

        results = [dict(r) for r in c.fetchall()]
        conn.close()
        return results
