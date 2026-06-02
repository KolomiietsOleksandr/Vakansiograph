import logging
import threading
import time
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

_STATIC_PATHS = [
    "/api/overview",
    "/api/insights/hero-stats",
    "/api/trends/insights",
    "/api/trends/skill-demand",
    "/api/trends/posting-volume",
    "/api/trends/category-salary",
    "/api/trends/countries",
    "/api/trends/skill-roi",
    "/api/trends/skill-roi?limit=15",
    "/api/categories/summary",
    "/api/locations",
    "/api/salaries?group_by=department",
    "/api/salaries?group_by=state",
    "/api/salaries?group_by=grade",
    "/api/skills/top?limit=8",
    "/api/skills/top?limit=14",
    "/api/skills/top?limit=20",
    "/api/skills/top?limit=100",
    "/api/skills/top?limit=300",
    "/api/jobs/recent?limit=5",
    "/api/jobs/recent?limit=8",
]


def _warm(app):
    hit = 0
    with app.test_client() as client:
        for path in _STATIC_PATHS:
            try:
                client.get(path)
                hit += 1
            except Exception as e:
                logger.warning("[warmer] %s → %s", path, e)

        countries_data = []
        try:
            r = client.get("/api/trends/countries")
            if r.status_code == 200:
                countries_data = r.get_json() or []
        except Exception as e:
            logger.warning("[warmer] /api/trends/countries → %s", e)

        logger.info("[warmer] countries to warm: %d", len(countries_data))
        for item in countries_data:
            code = item.get("country", "")
            if not code:
                continue
            try:
                client.get(f"/api/trends/country-stats?country={code}")
                client.get(f"/api/trends/posting-volume-by-country?country={code}")
                hit += 2
            except Exception as e:
                logger.warning("[warmer] country %s → %s", code, e)

        skills_data = []
        try:
            r = client.get("/api/skills/top?limit=50")
            if r.status_code == 200:
                skills_data = r.get_json() or []
        except Exception as e:
            logger.warning("[warmer] /api/skills/top?limit=50 → %s", e)

        logger.info("[warmer] skills to warm: %d", len(skills_data))
        for item in skills_data:
            name = item.get("skill", "")
            if not name:
                continue
            q = urlencode({"skill": name})
            try:
                client.get(f"/api/trends/skill-detail?{q}")
                client.get(f"/api/trends/skill-country-breakdown?{q}")
                client.get(f"/api/trends/skill-timeline?{q}&country=ALL")
                hit += 3
            except Exception as e:
                logger.warning("[warmer] skill %s → %s", name, e)

    logger.info("[warmer] done — %d endpoints warmed", hit)


def start_cache_warmer(app, delay: int = 0):
    def _run():
        if delay:
            time.sleep(delay)
        logger.info("[warmer] starting cache warm-up…")
        try:
            _warm(app)
        except Exception:
            logger.exception("[warmer] warm-up failed")

    t = threading.Thread(target=_run, daemon=True, name="cache-warmer")
    t.start()
