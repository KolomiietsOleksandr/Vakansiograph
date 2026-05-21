import hashlib
import json
import logging
from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    return text.lower().strip()


def hash_key(*args) -> str:
    combined = json.dumps(args, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(combined.encode()).hexdigest()


class DiskCache:
    def __init__(self, cache_dir: str | Path):
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def get(self, key: str):
        path = self._path(key)
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Cache read error for key %s: %s", key, e)
        return None

    def set(self, key: str, value) -> None:
        path = self._path(key)
        try:
            with open(path, "w") as f:
                json.dump(value, f, ensure_ascii=False)
        except OSError as e:
            logger.warning("Cache write error for key %s: %s", key, e)


def retry_with_backoff(max_attempts: int = 3, min_wait: float = 1.0, max_wait: float = 60.0):
    """Decorator for exponential backoff retry using tenacity."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        reraise=True,
    )
