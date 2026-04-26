import os
import time
import sqlite3
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Adzuna supported country codes ───────────────────────────────────────────
COUNTRIES = [
    "gb", "au", "at", "be", "br", "ca", "de",
    "fr", "in", "it", "mx", "nl", "nz", "pl",
    "sg", "za",
]

BASE_URL = "https://api.adzuna.com/v1/api/jobs"


class AdzunaParser:
    def __init__(self):
        self.app_id  = os.getenv("ADZUNA_APP_ID")
        self.app_key = os.getenv("ADZUNA_APP_KEY")

        if not self.app_id or not self.app_key:
            raise EnvironmentError(
                "ADZUNA_APP_ID and ADZUNA_APP_KEY must be set in .env"
            )

        self.results_per_page = int(os.getenv("RESULTS_PER_PAGE", 50))
        self.max_pages        = int(os.getenv("MAX_PAGES", 5))
        self.delay            = float(os.getenv("REQUEST_DELAY", 1.0))
        self.countries        = os.getenv("COUNTRIES", ",".join(COUNTRIES)).split(",")

        # Resolve DB path the same way the rest of the project does
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.db_path = os.getenv(
            "DATABASE_PATH",
            os.getenv("DB_PATH", str(base_dir / "app" / "labor_market.db"))
        )

        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _get(self, url: str, params: dict) -> dict | None:
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError:
            log.error("HTTP error %s → %s", resp.status_code, url)
        except requests.exceptions.RequestException as e:
            log.error("Request failed: %s", e)
        return None

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_job(self, raw: dict, country: str) -> dict:
        """Map Adzuna fields to the job_postings table schema."""
        location = raw.get("location", {})
        category = raw.get("category", {})
        company  = raw.get("company",  {})

        area_parts = location.get("area", [])
        location_city  = location.get("display_name", "")
        location_state = area_parts[-1] if area_parts else ""

        description = raw.get("description", "")

        return {
            "position_id":          raw.get("id"),
            "title":                raw.get("title"),
            "organization":         company.get("display_name", ""),
            "department":           category.get("label", ""),
            "location_city":        location_city,
            "location_state":       location_state,
            "location_country":     country.upper(),
            "min_salary":           raw.get("salary_min") or 0.0,
            "max_salary":           raw.get("salary_max") or 0.0,
            "salary_type":          "Per Year",
            "job_grade":            "",
            "series_code":          category.get("tag", ""),
            "series_group":         "",
            "qualification_summary": description,
            "major_duties":         "",
            "education_requirements": "",
            "travel_percentage":    "",
            "telework_eligible":    False,
            "date_posted":          raw.get("created", ""),
            "date_closing":         "",
            "url":                  raw.get("redirect_url", ""),
            "who_may_apply":        "",
            "hiring_path":          raw.get("contract_time", ""),
            "total_openings":       1,
            "job_type":             "Private",
        }

    def _fetch_page(self, country: str, page: int) -> tuple[list[dict], int]:
        url = f"{BASE_URL}/{country}/search/{page}"
        params = {
            "app_id":           self.app_id,
            "app_key":          self.app_key,
            "results_per_page": self.results_per_page,
            "content-type":     "application/json",
        }

        data = self._get(url, params)
        if not data:
            return [], 0

        total   = data.get("count", 0)
        results = data.get("results", [])
        jobs    = [self._parse_job(r, country) for r in results]
        return jobs, total

    # ── DB helpers ────────────────────────────────────────────────────────────

    def _upsert_jobs(self, conn: sqlite3.Connection, jobs: list[dict]) -> int:
        cur = conn.cursor()
        saved = 0
        for job in jobs:
            if not job.get("position_id"):
                continue
            cur.execute("""
                INSERT OR REPLACE INTO job_postings
                    (position_id, title, organization, department,
                     location_city, location_state, location_country,
                     min_salary, max_salary, salary_type,
                     job_grade, series_code, series_group,
                     qualification_summary, major_duties,
                     education_requirements, travel_percentage,
                     telework_eligible, date_posted, date_closing,
                     url, who_may_apply, hiring_path,
                     total_openings, job_type)
                VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                job["position_id"], job["title"], job["organization"],
                job["department"], job["location_city"], job["location_state"],
                job["location_country"], job["min_salary"], job["max_salary"],
                job["salary_type"], job["job_grade"], job["series_code"],
                job["series_group"], job["qualification_summary"],
                job["major_duties"], job["education_requirements"],
                job["travel_percentage"], job["telework_eligible"],
                job["date_posted"], job["date_closing"], job["url"],
                job["who_may_apply"], job["hiring_path"],
                job["total_openings"], job["job_type"],
            ))
            saved += 1
        conn.commit()
        return saved

    # ── Runner ────────────────────────────────────────────────────────────────

    def run(self):
        log.info("Adzuna parser started")
        log.info("DB path      : %s", self.db_path)
        log.info("Countries    : %s", ", ".join(c.upper() for c in self.countries))
        log.info("Pages/country: %d  |  Per page: %d", self.max_pages, self.results_per_page)

        total_saved = 0

        conn = sqlite3.connect(self.db_path, timeout=60)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            for country in self.countries:
                country = country.strip().lower()
                log.info("── Country: %s ──────────────────────", country.upper())

                for page in range(1, self.max_pages + 1):
                    jobs, total_on_api = self._fetch_page(country, page)

                    if not jobs:
                        log.info("  [%s] page %d — no results, stopping", country, page)
                        break

                    saved = self._upsert_jobs(conn, jobs)
                    total_saved += saved
                    log.info(
                        "  [%s] page %d/%d — fetched %d, saved %d (API total: %s)",
                        country.upper(), page, self.max_pages,
                        len(jobs), saved, total_on_api,
                    )

                    fetched_so_far = page * self.results_per_page
                    if fetched_so_far >= total_on_api:
                        log.info("  [%s] All available jobs fetched.", country.upper())
                        break

                    time.sleep(self.delay)
        finally:
            conn.close()

        log.info("Done. Total new/updated jobs saved: %d", total_saved)


if __name__ == "__main__":
    AdzunaParser().run()
