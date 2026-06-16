import requests
import time
import json
import logging
import sqlite3
import os
from datetime import datetime
from typing import Optional, Generator
from dataclasses import dataclass, field, asdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Завантажує конфігурацію."""
    config = {}
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    config[key.strip()] = val.strip()
    
    config["USAJOBS_API_KEY"] = os.environ.get("USAJOBS_API_KEY", config.get("USAJOBS_API_KEY", ""))
    config["USAJOBS_EMAIL"] = os.environ.get("USAJOBS_EMAIL", config.get("USAJOBS_EMAIL", ""))
    config["DB_PATH"] = os.environ.get("DB_PATH", config.get("DB_PATH", "labor_market.db"))
    return config


@dataclass
class JobPosting:
    position_id: str
    title: str
    organization: str
    department: str
    location_city: str
    location_state: str
    location_country: str
    min_salary: float
    max_salary: float
    salary_type: str
    job_grade: str
    series_code: str
    series_group: str
    qualification_summary: str
    major_duties: str
    required_skills: list = field(default_factory=list)
    education_requirements: str = ""
    travel_percentage: str = ""
    telework_eligible: bool = False
    date_posted: str = ""
    date_closing: str = ""
    url: str = ""
    who_may_apply: str = ""
    hiring_path: str = ""
    total_openings: int = 1
    job_type: str = ""
    raw_data: dict = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw_data", None)
        return d


class USAJobsClient:

    BASE_URL = "https://data.usajobs.gov/api/search"
    REQUEST_DELAY = 0.5

    def __init__(self, api_key: str, email: str):
        if not api_key or api_key == "your-api-key-here":
            raise ValueError(
                "\n\n"
                "========================================================\n"
                "  USAJOBS API KEY не налаштований!\n"
                "\n"
                "  1. Зайдіть: https://developer.usajobs.gov/APIRequest/Index\n"
                "  2. Заповніть форму реєстрації\n"
                "  3. Отримайте ключ на email\n"
                "  4. Створіть файл .env у корені проекту:\n"
                "     USAJOBS_API_KEY=ваш-ключ\n"
                "     USAJOBS_EMAIL=ваш-email\n"
                "========================================================\n"
            )

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization-Key": api_key,
            "User-Agent": email,
            "Host": "data.usajobs.gov",
        })
        self._last_request_time = 0.0
        self._request_count = 0

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()
        self._request_count += 1

    def _request(self, url: str, params: dict) -> dict:
        max_retries = 3
        for attempt in range(max_retries):
            self._rate_limit()
            try:
                resp = self.session.get(url, params=params, timeout=30)

                if resp.status_code == 429:
                    wait = 2 ** attempt * 10
                    logger.warning(f"Rate limited (429). Чекаємо {wait}с...")
                    time.sleep(wait)
                    continue
                if resp.status_code == 503:
                    logger.warning(f"Сервер недоступний (503). Retry {attempt+1}/{max_retries}")
                    time.sleep(5)
                    continue

                resp.raise_for_status()
                return resp.json()

            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error: {e}. Retry {attempt+1}/{max_retries}")
                time.sleep(2 ** attempt * 2)
            except requests.exceptions.Timeout:
                logger.error(f"Timeout. Retry {attempt+1}/{max_retries}")
                time.sleep(2 ** attempt * 2)
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                if attempt == max_retries - 1:
                    raise
        return {}

    def search(
        self,
        keyword: str = "",
        location: str = "",
        results_per_page: int = 500,
        page: int = 1,
        date_posted: int = 90,
        sort_field: str = "DatePosted",
        sort_direction: str = "Desc",
    ) -> dict:
        """
        Пошук ВСІХ вакансій (федеральні + приватні).
        БЕЗ фільтра по OPM категоріям!
        """
        params = {
            "ResultsPerPage": min(results_per_page, 500),
            "Page": page,
            "SortField": sort_field,
            "SortDirection": sort_direction,
        }
        if keyword:
            params["Keyword"] = keyword
        if location:
            params["LocationName"] = location
        if date_posted:
            params["DatePosted"] = date_posted

        data = self._request(self.BASE_URL, params)
        if not data:
            return {"total_count": 0, "pages": 0, "current_page": page, "jobs": []}

        search_result = data.get("SearchResult", {})
        search_items = search_result.get("SearchResultItems", [])
        total = int(search_result.get("SearchResultCountAll", 0))
        pages = min(
            (total + results_per_page - 1) // results_per_page if results_per_page > 0 else 1,
            10000 // results_per_page
        )
        jobs = [self._parse_job(item) for item in search_items]

        logger.info(f"Стор. {page}/{pages} — {len(jobs)} вак. (всього: {total}, запитів: {self._request_count})")
        return {"total_count": total, "pages": pages, "current_page": page, "jobs": jobs}

    def search_all(self, max_pages: int = 20, **kwargs) -> Generator[JobPosting, None, None]:
        """Пошук всіх сторінок."""
        page = 1
        total_yielded = 0
        while page <= max_pages:
            result = self.search(page=page, **kwargs)
            if not result["jobs"]:
                break
            for job in result["jobs"]:
                yield job
                total_yielded += 1
            if total_yielded >= 9500:
                logger.warning(f"Наближаємося до ліміту 10K.")
                break
            if page >= result["pages"]:
                break
            page += 1

    def _parse_job(self, item: dict) -> JobPosting:
        matched = item.get("MatchedObjectDescriptor", {})

        _COUNTRY_NAME_TO_ISO = {
            "united states": "US", "united kingdom": "GB", "australia": "AU",
            "germany": "DE", "france": "FR", "canada": "CA", "india": "IN",
            "brazil": "BR", "netherlands": "NL", "poland": "PL", "italy": "IT",
            "mexico": "MX", "belgium": "BE", "austria": "AT", "new zealand": "NZ",
            "singapore": "SG", "south africa": "ZA", "russia": "RU", "japan": "JP",
        }

        locations = matched.get("PositionLocation", [])
        city, state, country = "", "", "US"
        if locations:
            loc = locations[0]
            city = loc.get("CityName", "")
            state = loc.get("CountrySubDivisionCode", "")
            raw_country = loc.get("CountryCode", "US") or "US"
            country = _COUNTRY_NAME_TO_ISO.get(raw_country.lower(), raw_country.upper())[:2]

        remuneration = matched.get("PositionRemuneration", [{}])
        salary_data = remuneration[0] if remuneration else {}
        min_salary = float(salary_data.get("MinimumRange", 0) or 0)
        max_salary = float(salary_data.get("MaximumRange", 0) or 0)
        salary_type = salary_data.get("Description", "Per Year")

        job_grade = matched.get("JobGrade", [{}])
        grade_code = job_grade[0].get("Code", "") if job_grade else ""

        job_category = matched.get("JobCategory", [{}])
        series_code = job_category[0].get("Code", "") if job_category else ""
        series_group = series_code[:2] + "00" if len(series_code) >= 4 else ""

        user_area = matched.get("UserArea", {}).get("Details", {})
        quality = matched.get("QualificationSummary", "")
        duties = user_area.get("MajorDuties", [""])
        if isinstance(duties, list):
            duties = " | ".join(d for d in duties if d)

        telework = user_area.get("TeleworkEligible", False)
        if isinstance(telework, str):
            telework = telework.lower() in ("true", "yes", "1")

        who_may = user_area.get("WhoMayApply", {})
        if isinstance(who_may, dict):
            who_may = who_may.get("Name", "")

        hiring_path_val = user_area.get("HiringPath", [""])
        if isinstance(hiring_path_val, list):
            hiring_path_val = ", ".join(hiring_path_val)

        total_openings = user_area.get("TotalOpenings", "1")
        try:
            total_openings = int(total_openings)
        except (ValueError, TypeError):
            total_openings = 1

        job_type = self._determine_job_type(matched.get("OrganizationName", ""), who_may)

        skills = self._extract_skills_from_text(f"{quality} {duties} {matched.get('PositionTitle', '')}")

        return JobPosting(
            position_id=matched.get("PositionID", ""),
            title=matched.get("PositionTitle", ""),
            organization=matched.get("OrganizationName", ""),
            department=matched.get("DepartmentName", ""),
            location_city=city, location_state=state, location_country=country,
            min_salary=min_salary, max_salary=max_salary, salary_type=salary_type,
            job_grade=grade_code, series_code=series_code, series_group=series_group,
            qualification_summary=quality, major_duties=duties,
            required_skills=skills,
            education_requirements=user_area.get("Education", ""),
            travel_percentage=user_area.get("TravelCode", ""),
            telework_eligible=telework,
            date_posted=matched.get("PublicationStartDate", ""),
            date_closing=matched.get("ApplicationCloseDate", ""),
            url=matched.get("PositionURI", ""),
            who_may_apply=who_may, hiring_path=hiring_path_val,
            total_openings=total_openings,
            job_type=job_type,
            raw_data=item,
        )

    @staticmethod
    def _determine_job_type(org_name: str, who_may_apply: str) -> str:
        org_lower = org_name.lower()

        if any(dept in org_lower for dept in [
            "department of", "agency", "federal", "usda", "hhs", "dod", "va",
            "social security", "national", "office of", "administration",
            "service", "bureau", "commission", "board", "corps"
        ]):
            return "Federal"
        
        if any(state in org_lower for state in [
            "state of", "department of state", "legislature", "university of"
        ]):
            return "State"
        
        if any(corp in org_lower for corp in [
            "inc", "llc", "corp", "company", "ltd", "group", "solutions"
        ]):
            return "Private"
        
        if any(nonprofit in org_lower for nonprofit in [
            "foundation", "non-profit", "nonprofit", "charity", "association"
        ]):
            return "Non-Profit"
        
        return "Other"

    @staticmethod
    def _extract_skills_from_text(text: str) -> list:
        skill_patterns = [
            "python", "java", "javascript", "typescript", "sql", "c++", "c#",
            "machine learning", "deep learning", "nlp", "data analysis",
            "data science", "cloud computing", "aws", "azure", "gcp",
            "docker", "kubernetes", "terraform", "devops", "git", "linux",
            "react", "angular", "node.js", "postgresql", "mongodb",
            "cybersecurity", "network security", "information security",
            "artificial intelligence", "computer vision",
            "civil engineering", "mechanical engineering", "electrical engineering",
            "structural analysis", "autocad", "solidworks",
            "construction management", "surveying", "geotechnical",
            "patient care", "clinical", "nursing", "pharmacy", "diagnostics",
            "healthcare", "public health", "epidemiology",
            "mental health", "rehabilitation", "occupational therapy",
            "financial analysis", "accounting", "auditing", "budgeting",
            "procurement", "contracting", "cost analysis", "financial reporting",
            "project management", "program management", "strategic planning",
            "policy analysis", "regulatory compliance", "stakeholder engagement",
            "change management", "risk management", "quality assurance",
            "recruitment", "training", "employee relations", "labor relations",
            "performance management", "workforce planning",
            "legal research", "litigation", "regulatory analysis",
            "contract law", "administrative law", "compliance",
            "research methodology", "laboratory", "field research",
            "statistical analysis", "data collection", "scientific writing",
            "environmental assessment", "chemistry", "biology",
            "supply chain", "logistics", "inventory management",
            "warehouse management", "distribution",
            "investigation", "law enforcement", "intelligence analysis",
            "surveillance", "forensics", "security clearance",
            "communication", "leadership", "problem solving",
            "critical thinking", "teamwork", "writing",
            "public speaking", "negotiation", "analytical thinking",
            "excel", "powerpoint", "tableau", "power bi", "sap",
            "sharepoint", "microsoft office",
            "agile", "scrum", "lean", "six sigma",
        ]
        text_lower = text.lower()
        return list(set(skill for skill in skill_patterns if skill in text_lower))


class DataCollector:
    def __init__(self, client: USAJobsClient, db_path: str = "labor_market.db"):
        self.client = client
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path, timeout=60)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS job_postings (
                position_id TEXT PRIMARY KEY,
                title TEXT NOT NULL, organization TEXT, department TEXT,
                location_city TEXT, location_state TEXT,
                location_country TEXT DEFAULT 'US',
                min_salary REAL, max_salary REAL, salary_type TEXT,
                job_grade TEXT, series_code TEXT, series_group TEXT,
                qualification_summary TEXT, major_duties TEXT,
                education_requirements TEXT, travel_percentage TEXT,
                telework_eligible BOOLEAN DEFAULT FALSE,
                date_posted DATE, date_closing DATE, url TEXT,
                who_may_apply TEXT, hiring_path TEXT,
                total_openings INTEGER DEFAULT 1,
                job_type TEXT DEFAULT 'Other',
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS job_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id TEXT NOT NULL, skill_raw TEXT NOT NULL,
                skill_esco_uri TEXT, skill_esco_label TEXT, skill_esco_type TEXT,
                FOREIGN KEY (position_id) REFERENCES job_postings(position_id)
            );
            CREATE TABLE IF NOT EXISTS collection_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT, keyword TEXT,
                total_found INTEGER, jobs_collected INTEGER,
                started_at TIMESTAMP, finished_at TIMESTAMP,
                status TEXT DEFAULT 'success', error_message TEXT
            );
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date DATE NOT NULL,
                job_type TEXT,
                total_postings INTEGER,
                avg_min_salary REAL, avg_max_salary REAL,
                remote_percentage REAL, top_skills TEXT,
                top_locations TEXT, total_openings INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_date ON job_postings(date_posted);
            CREATE INDEX IF NOT EXISTS idx_jobs_state ON job_postings(location_state);
            CREATE INDEX IF NOT EXISTS idx_jobs_type ON job_postings(job_type);
            CREATE INDEX IF NOT EXISTS idx_skills_raw ON job_skills(skill_raw);
        """)
        conn.commit()
        conn.close()
        logger.info(f"БД ініціалізована: {self.db_path}")

    def collect_all(self, max_pages=20, date_posted=90):
        """Збір ВСІХ вакансій з USAJOBS без фільтрів!"""
        logger.info(f"🔄 Збір ВСІХ вакансій за останні {date_posted} днів...")
        start_time = datetime.now()
        collected = 0
        conn = sqlite3.connect(self.db_path, timeout=60)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        cur = conn.cursor()
        
        try:
            for job in self.client.search_all(max_pages=max_pages, date_posted=date_posted):
                cur.execute("""
                    INSERT OR REPLACE INTO job_postings
                    (position_id,title,organization,department,location_city,location_state,
                     location_country,min_salary,max_salary,salary_type,job_grade,series_code,
                     series_group,qualification_summary,major_duties,education_requirements,
                     travel_percentage,telework_eligible,date_posted,date_closing,url,
                     who_may_apply,hiring_path,total_openings,job_type)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (job.position_id, job.title, job.organization, job.department,
                      job.location_city, job.location_state, job.location_country,
                      job.min_salary, job.max_salary, job.salary_type, job.job_grade,
                      job.series_code, job.series_group, job.qualification_summary,
                      job.major_duties, job.education_requirements, job.travel_percentage,
                      job.telework_eligible, job.date_posted, job.date_closing, job.url,
                      job.who_may_apply, job.hiring_path, job.total_openings, job.job_type))
                
                for skill in job.required_skills:
                    cur.execute("INSERT INTO job_skills (position_id, skill_raw) VALUES (?,?)",
                                (job.position_id, skill))
                collected += 1
                
                if collected % 100 == 0:
                    logger.info(f"  ... {collected} вакансій збрано")
            
            cur.execute("""INSERT INTO collection_log (query,total_found,
                jobs_collected,started_at,finished_at,status)
                VALUES (?,?,?,?,?,'success')
            """, ("ALL_USAJOBS", collected, collected, start_time, datetime.now()))
            conn.commit()
            logger.info(f"✅ Збір завершено: {collected} вакансій")
        except Exception as e:
            logger.error(f"Помилка: {e}")
            cur.execute("""INSERT INTO collection_log (query,total_found,
                jobs_collected,started_at,finished_at,status,error_message)
                VALUES (?,0,0,?,?,'error',?)
            """, ("ALL_USAJOBS", start_time, datetime.now(), str(e)))
            conn.commit()
        finally:
            conn.close()
        
        return collected

    def create_snapshot(self):
        """Створити снімок ринку."""
        conn = sqlite3.connect(self.db_path, timeout=60)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        cur = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        
        cur.execute("""
            SELECT COUNT(*), AVG(min_salary), AVG(max_salary),
                SUM(CASE WHEN telework_eligible THEN 1 ELSE 0 END)*100.0/MAX(COUNT(*),1),
                SUM(total_openings)
            FROM job_postings
        """)
        row = cur.fetchone()
        
        if row and row[0] > 0:
            cur.execute("""SELECT skill_raw, COUNT(*) FROM job_skills
                GROUP BY skill_raw ORDER BY 2 DESC LIMIT 20
            """)
            top_skills = json.dumps([{"skill": r[0], "count": r[1]} for r in cur.fetchall()])
            
            cur.execute("""SELECT location_state, COUNT(*) FROM job_postings
                WHERE location_state!='' GROUP BY location_state ORDER BY 2 DESC LIMIT 20
            """)
            top_locs = json.dumps([{"state": r[0], "count": r[1]} for r in cur.fetchall()])
            
            cur.execute("SELECT DISTINCT job_type FROM job_postings")
            for (job_type,) in cur.fetchall():
                cur.execute("""
                    SELECT COUNT(*), AVG(min_salary), AVG(max_salary),
                        SUM(CASE WHEN telework_eligible THEN 1 ELSE 0 END)*100.0/MAX(COUNT(*),1),
                        SUM(total_openings)
                    FROM job_postings WHERE job_type = ?
                """, (job_type,))
                type_row = cur.fetchone()
                if type_row and type_row[0] > 0:
                    cur.execute("""INSERT OR REPLACE INTO market_snapshots
                        (snapshot_date, job_type, total_postings, avg_min_salary,
                         avg_max_salary, remote_percentage, top_skills, top_locations, total_openings)
                        VALUES (?,?,?,?,?,?,?,?,?)
                    """, (today, job_type, type_row[0], type_row[1], type_row[2], 
                          type_row[3], top_skills, top_locs, type_row[4]))
        
        conn.commit()
        conn.close()
        logger.info(f"Снімок ринку створений для {today}")

    def get_stats(self):
        """Статистика збору."""
        conn = sqlite3.connect(self.db_path, timeout=60)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        cur = conn.cursor()
        stats = {}
        
        for label, q in [
            ("total_postings", "SELECT COUNT(*) FROM job_postings"),
            ("federal", "SELECT COUNT(*) FROM job_postings WHERE job_type='Federal'"),
            ("private", "SELECT COUNT(*) FROM job_postings WHERE job_type='Private'"),
            ("state", "SELECT COUNT(*) FROM job_postings WHERE job_type='State'"),
            ("non_profit", "SELECT COUNT(*) FROM job_postings WHERE job_type='Non-Profit'"),
            ("unique_orgs", "SELECT COUNT(DISTINCT organization) FROM job_postings"),
            ("unique_skills", "SELECT COUNT(DISTINCT skill_raw) FROM job_skills"),
            ("errors", "SELECT COUNT(*) FROM collection_log WHERE status='error'"),
        ]:
            cur.execute(q)
            result = cur.fetchone()
            stats[label] = result[0] if result else 0
        
        conn.close()
        stats["api_requests"] = self.client._request_count
        return stats


if __name__ == "__main__":
    config = load_config()
    client = USAJobsClient(config["USAJOBS_API_KEY"], config["USAJOBS_EMAIL"])
    collector = DataCollector(client, config["DB_PATH"])
    
    print("\n" + "="*60)
    print("🔄 Збір ВСІХ вакансій USAJOBS (федеральні + приватні)")
    print("="*60 + "\n")
    
    collector.collect_all(max_pages=20, date_posted=90)
    collector.create_snapshot()
    
    print("\n📊 Статистика:")
    for k, v in collector.get_stats().items():
        print(f"  {k}: {v}")
    print()
