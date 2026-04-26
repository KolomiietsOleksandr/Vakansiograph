"""
Database connection utilities
"""

import sqlite3
from app.config import Config


def get_db_connection():
    """Get SQLite database connection with WAL mode for concurrency safety"""
    conn = sqlite3.connect(Config.DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def execute_query(query: str, params: tuple = ()):
    """Execute a SELECT query and return results"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    return results


def execute_single(query: str, params: tuple = ()):
    """Execute a SELECT query and return single result"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = cursor.fetchone()
    conn.close()
    return result
