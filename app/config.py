import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    DATABASE_PATH = os.getenv("DATABASE_PATH", os.getenv("DB_PATH", os.path.join(BASE_DIR, "app", "labor_market.db")))
    JSON_SORT_KEYS = False
    JSONIFY_PRETTYPRINT_REGULAR = True
    CORS_ORIGINS = "*"


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False
    LOG_LEVEL = "DEBUG"


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    LOG_LEVEL = "INFO"


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    DATABASE_PATH = ":memory:"
