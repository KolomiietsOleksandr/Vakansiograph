import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

JOOBLE_BASE_URL = "https://jooble.org/api/"
RESULTS_PER_PAGE = 20

# Broad categories to get diverse Ukrainian vacancies.
# Empty string = all jobs. Specific keywords fill gaps in niche categories.
SEARCH_KEYWORDS = [
    "",
    "розробник",
    "інженер",
    "менеджер",
    "аналітик",
    "дизайнер",
    "бухгалтер",
    "маркетинг",
    "юрист",
    "продажі",
]

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub(" ", text).strip()


def _parse_salary(salary_str: str) -> tuple[float, float]:
    """Parse Jooble salary string (e.g. '17 600 UAH' or '20 000 – 35 000 UAH')."""
    if not salary_str:
        return 0.0, 0.0
    cleaned = salary_str.replace("\xa0", "").replace(" ", "").replace(",", "")
    nums = re.findall(r"\d+", cleaned)
    vals = [float(n) for n in nums if len(n) >= 3]
    if len(vals) >= 2:
        return min(vals), max(vals)
    if len(vals) == 1:
        return vals[0], vals[0]
    return 0.0, 0.0


class JoobleParser:
    def __init__(self):
        self.api_key = os.getenv("JOOBLE_API_KEY", "")
        if not self.api_key:
            raise EnvironmentError("JOOBLE_API_KEY must be set in environment")

        self.gemini_key = os.getenv("GEMINI_API_KEY", "")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.max_requests = int(os.getenv("JOOBLE_MAX_REQUESTS", 500))
        self.delay = float(os.getenv("JOOBLE_REQUEST_DELAY", 0.5))

        base_dir = Path(__file__).resolve().parent.parent.parent
        self.db_path = os.getenv(
            "DATABASE_PATH",
            os.getenv("DB_PATH", str(base_dir / "app" / "labor_market.db")),
        )

        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self._request_count = 0

    # ── Jooble HTTP ───────────────────────────────────────────────────────────

    def _post(self, payload: dict) -> dict | None:
        if self._request_count >= self.max_requests:
            return None
        url = f"{JOOBLE_BASE_URL}{self.api_key}"
        try:
            time.sleep(self.delay)
            resp = self.session.post(url, json=payload, timeout=20)
            resp.raise_for_status()
            self._request_count += 1
            return resp.json()
        except requests.exceptions.RequestException as e:
            log.error("[JOOBLE] Request failed: %s", e)
            return None

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_job(self, raw: dict) -> dict | None:
        job_id = str(raw.get("id", "")).strip()
        if not job_id:
            return None

        title = _strip_html(raw.get("title", ""))
        snippet = _strip_html(raw.get("snippet", ""))
        min_sal, max_sal = _parse_salary(raw.get("salary", ""))
        updated = raw.get("updated", "")
        date_posted = updated[:10] if updated and len(updated) >= 10 else ""

        return {
            "position_id": f"jooble_{job_id}",
            "title": title,
            "organization": raw.get("company", ""),
            "department": "",
            "location_city": raw.get("location", ""),
            "location_state": "",
            "location_country": "UA",
            "min_salary": min_sal,
            "max_salary": max_sal,
            # Salary in UAH — analytics filter (min_salary > 20000) treats them
            # correctly for UAH ranges; USD analytics are filtered by salary_type.
            "salary_type": "Per Month" if min_sal else "Per Year",
            "job_grade": "",
            "series_code": "",
            "series_group": "",
            "qualification_summary": f"{title} {snippet}".strip(),
            "major_duties": "",
            "education_requirements": "",
            "travel_percentage": "",
            "telework_eligible": False,
            "date_posted": date_posted,
            "date_closing": "",
            "url": raw.get("link", ""),
            "who_may_apply": "",
            "hiring_path": raw.get("type", ""),
            "total_openings": 1,
            "job_type": "Jooble",
            "_snippet": snippet,  # not stored in DB, used for skill extraction
        }

    # ── Skill extraction via Gemini ───────────────────────────────────────────

    def _extract_skills(self, jobs: list[dict]) -> dict[str, list[str]]:
        """Extract skills from Ukrainian job postings, return English skill names."""
        if not self.gemini_key or not jobs:
            return {}
        try:
            from google import genai as _genai

            client = _genai.Client(api_key=self.gemini_key)
            postings = [
                {
                    "id": j["position_id"],
                    "title": j["title"],
                    "text": j.get("_snippet", ""),
                }
                for j in jobs
            ]
            prompt = (
                "You are a skill extraction expert. "
                "Extract professional skills from Ukrainian job postings. "
                "Return skill names in English (translate from Ukrainian when needed). "
                "Include: programming languages, tools, frameworks, methodologies, "
                "domain skills, soft skills, certifications.\n\n"
                f"Job postings: {json.dumps(postings, ensure_ascii=False)}\n\n"
                'Return ONLY valid JSON: '
                '{"results": [{"id": "<position_id>", "skills": ["skill1", "skill2"]}]}'
            )
            resp = client.models.generate_content(model=self.gemini_model, contents=prompt)
            text = resp.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1].lstrip("json").strip()
            data = json.loads(text)
            return {r["id"]: r.get("skills", []) for r in data.get("results", [])}
        except Exception:
            log.exception("[JOOBLE] Gemini skill extraction failed")
            return {}

    # ── DB ────────────────────────────────────────────────────────────────────

    def _save_page(self, conn: sqlite3.Connection, jobs: list[dict]) -> int:
        """Upsert jobs; extract and store skills only for brand-new rows."""
        cur = conn.cursor()
        new_jobs: list[dict] = []

        for job in jobs:
            snippet = job.pop("_snippet", "")
            cur.execute(
                """
                INSERT OR IGNORE INTO job_postings
                    (position_id, title, organization, department,
                     location_city, location_state, location_country,
                     min_salary, max_salary, salary_type,
                     job_grade, series_code, series_group,
                     qualification_summary, major_duties,
                     education_requirements, travel_percentage,
                     telework_eligible, date_posted, date_closing,
                     url, who_may_apply, hiring_path,
                     total_openings, job_type)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
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
                ),
            )
            if cur.rowcount > 0:
                job["_snippet"] = snippet
                new_jobs.append(job)

        conn.commit()

        if not new_jobs:
            return 0

        skills_map = self._extract_skills(new_jobs)

        for job in new_jobs:
            for skill in skills_map.get(job["position_id"], []):
                skill = skill.strip()
                if not skill:
                    continue
                try:
                    cur.execute(
                        "INSERT INTO job_skills (position_id, skill_raw) VALUES (?,?)",
                        (job["position_id"], skill),
                    )
                except Exception:
                    pass

        conn.commit()
        if not self.gemini_key:
            log.warning(
                "[JOOBLE] GEMINI_API_KEY not set — %d jobs saved without skills",
                len(new_jobs),
            )
        return len(new_jobs)

    # ── Runner ────────────────────────────────────────────────────────────────

    def run(self) -> int:
        log.info(
            "[JOOBLE] Parser started | max_requests=%d | db=%s",
            self.max_requests, self.db_path,
        )
        total_saved = 0
        conn = sqlite3.connect(self.db_path, timeout=60)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        try:
            for keyword in SEARCH_KEYWORDS:
                if self._request_count >= self.max_requests:
                    log.info("[JOOBLE] Request limit reached (%d)", self.max_requests)
                    break

                log.info("[JOOBLE] Keyword: '%s'", keyword or "(all)")
                page = 1

                while self._request_count < self.max_requests:
                    payload = {
                        "keywords": keyword,
                        "location": "Україна",
                        "page": page,
                        "ResultOnPage": RESULTS_PER_PAGE,
                    }
                    data = self._post(payload)
                    if not data:
                        break

                    raw_jobs = data.get("jobs", [])
                    if not raw_jobs:
                        break

                    jobs = [j for j in (self._parse_job(r) for r in raw_jobs) if j]
                    saved = self._save_page(conn, jobs)
                    total_saved += saved

                    log.info(
                        "[JOOBLE]   page=%d fetched=%d new=%d requests=%d/%d",
                        page, len(jobs), saved, self._request_count, self.max_requests,
                    )

                    total_count = data.get("totalCount", 0)
                    if not raw_jobs or page * RESULTS_PER_PAGE >= total_count:
                        break
                    page += 1

        finally:
            conn.close()

        log.info(
            "[JOOBLE] Done | new_jobs=%d requests=%d/%d",
            total_saved, self._request_count, self.max_requests,
        )
        return total_saved
