import sqlite3
from app.config import Config


def get_db_connection():
    conn = sqlite3.connect(Config.DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def ensure_indexes():
    conn = sqlite3.connect(Config.DATABASE_PATH, timeout=30)
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_skills_esco_label ON job_skills(skill_esco_label);
        CREATE INDEX IF NOT EXISTS idx_skills_esco_type  ON job_skills(skill_esco_type);
        CREATE INDEX IF NOT EXISTS idx_skills_position   ON job_skills(position_id);
        CREATE INDEX IF NOT EXISTS idx_skills_category   ON job_skills(skill_category);
        CREATE INDEX IF NOT EXISTS idx_jobs_salary       ON job_postings(min_salary, max_salary);
        CREATE INDEX IF NOT EXISTS idx_jobs_series       ON job_postings(series_code);
        CREATE INDEX IF NOT EXISTS idx_jobs_department   ON job_postings(department);
        CREATE INDEX IF NOT EXISTS idx_jobs_grade        ON job_postings(job_grade);
        CREATE INDEX IF NOT EXISTS idx_jobs_country      ON job_postings(location_country);
        CREATE INDEX IF NOT EXISTS idx_jobs_date         ON job_postings(date_posted);
        CREATE INDEX IF NOT EXISTS idx_jobs_country_date ON job_postings(location_country, date_posted);
    """)
    conn.commit()
    conn.close()
