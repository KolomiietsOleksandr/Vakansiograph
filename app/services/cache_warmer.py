import logging
import threading
import time
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 30

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


def _get(base_url: str, path: str) -> dict | None:
    try:
        r = requests.get(f"{base_url}{path}", timeout=_TIMEOUT)
        return r.json() if r.ok else None
    except Exception as e:
        logger.warning("[warmer] %s → %s", path, e)
        return None


def _warm(base_url: str):
    hit = 0

    for path in _STATIC_ENDPOINTS:
        _get(base_url, path)
        hit += 1

    countries_data = _get(base_url, "/api/trends/countries") or []
    logger.info("[warmer] countries to warm: %d", len(countries_data))
    for item in countries_data:
        code = item.get("country", "")
        if not code:
            continue
        _get(base_url, f"/api/trends/country-stats?country={code}")
        _get(base_url, f"/api/trends/posting-volume-by-country?country={code}")
        hit += 2

    skills_data = _get(base_url, "/api/skills/top?limit=50") or []
    logger.info("[warmer] skills to warm: %d", len(skills_data))
    for item in skills_data:
        name = item.get("skill", "")
        if not name:
            continue
        q = urlencode({"skill": name})
        _get(base_url, f"/api/trends/skill-detail?{q}")
        _get(base_url, f"/api/trends/skill-country-breakdown?{q}")
        _get(base_url, f"/api/trends/skill-timeline?{q}&country=ALL")
        hit += 3

    logger.info("[warmer] done — %d endpoints warmed", hit)


def start_cache_warmer(delay: int = 15):
    base_url = "http://localhost:5001"

    def _run():
        time.sleep(delay)
        logger.info("[warmer] starting cache warm-up…")
        _warm(base_url)

    t = threading.Thread(target=_run, daemon=True, name="cache-warmer")
    t.start()
