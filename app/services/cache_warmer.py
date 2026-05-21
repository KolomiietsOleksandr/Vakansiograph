import logging
import threading
import time
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

_STATIC_ENDPOINTS = [
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


def _warm(client):
    hit = 0
    miss = 0

    for url in _STATIC_ENDPOINTS:
        try:
            client.get(url)
            hit += 1
        except Exception as e:
            logger.warning("[warmer] %s failed: %s", url, e)
            miss += 1

    try:
        resp = client.get("/api/trends/countries")
        countries = resp.get_json() or []
        country_codes = [c.get("country") or c.get("code") or c for c in countries if c]

        for code in country_codes:
            for path in ("/api/trends/country-stats", "/api/trends/posting-volume-by-country"):
                try:
                    client.get(f"{path}?country={code}")
                    hit += 1
                except Exception as e:
                    logger.warning("[warmer] %s?country=%s failed: %s", path, code, e)
                    miss += 1
    except Exception as e:
        logger.warning("[warmer] countries warming failed: %s", e)

    try:
        resp = client.get("/api/skills/top?limit=50")
        skills = resp.get_json() or []
        skill_names = [s.get("skill") or s.get("esco_label") or s for s in skills if s]

        for name in skill_names:
            if not isinstance(name, str):
                continue
            q = urlencode({"skill": name})
            for path in (
                "/api/trends/skill-detail",
                "/api/trends/skill-country-breakdown",
            ):
                try:
                    client.get(f"{path}?{q}")
                    hit += 1
                except Exception as e:
                    logger.warning("[warmer] %s?%s failed: %s", path, q, e)
                    miss += 1
            try:
                client.get(f"/api/trends/skill-timeline?{q}&country=ALL")
                hit += 1
            except Exception as e:
                logger.warning("[warmer] skill-timeline?%s failed: %s", q, e)
                miss += 1
    except Exception as e:
        logger.warning("[warmer] skills warming failed: %s", e)

    logger.info("[warmer] done — hit=%d miss=%d", hit, miss)


def start_cache_warmer(app, delay: int = 10):
    def _run():
        time.sleep(delay)
        logger.info("[warmer] starting cache warm-up…")
        with app.test_client() as client:
            _warm(client)

    t = threading.Thread(target=_run, daemon=True, name="cache-warmer")
    t.start()
