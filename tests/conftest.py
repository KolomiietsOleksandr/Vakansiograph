import pytest
from app import create_app
from app.utils.database import get_db_connection


@pytest.fixture(scope='session')
def app():
    app = create_app(config_name="testing")

    with app.app_context():
        conn = get_db_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS job_postings (
                position_id TEXT PRIMARY KEY,
                title TEXT, organization TEXT, department TEXT,
                location_city TEXT, location_state TEXT, location_country TEXT,
                min_salary REAL, max_salary REAL, salary_type TEXT,
                job_grade TEXT, series_code TEXT, series_group TEXT,
                telework_eligible INTEGER, qualification_summary TEXT,
                major_duties TEXT, date_posted TEXT, url TEXT
            );
            CREATE TABLE IF NOT EXISTS job_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id TEXT, skill_raw TEXT,
                skill_esco_uri TEXT, skill_esco_label TEXT,
                skill_esco_type TEXT, skill_category TEXT
            );
            CREATE TABLE IF NOT EXISTS collection_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_code TEXT, series_name TEXT,
                total_found INTEGER, jobs_collected INTEGER,
                started_at TEXT, finished_at TEXT, status TEXT
            );
        """)
        conn.commit()
        conn.close()

    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()
