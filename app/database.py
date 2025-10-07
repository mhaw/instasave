import sqlite3
import os
import logging
from pathlib import Path
from functools import lru_cache

from app.settings import load_settings

MIGRATIONS_DIR = "migrations"

logger = logging.getLogger("instasave.database")

EXPECTED_POST_COLUMNS = {"id", "url", "caption", "timestamp", "media_paths", "thumbnail_path", "media_info"}


@lru_cache
def _settings():
    return load_settings()


def _default_db_url() -> str:
    return _settings().DATABASE_URL


def _ensure_parent(path: str) -> None:
    if path.startswith(':memory:'):
        return
    if path.startswith('file:'):
        return
    parent = Path(path).expanduser().resolve().parent
    parent.mkdir(parents=True, exist_ok=True)


def _validate_schema(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute('PRAGMA table_info(posts)')
    columns = {row['name'] for row in cursor.fetchall()}
    missing = EXPECTED_POST_COLUMNS - columns
    if missing:
        msg = f"Missing expected columns in posts table: {', '.join(sorted(missing))}"
        logger.error(msg, extra={'event': 'schema_validation_failed'})
        raise RuntimeError(msg)
    logger.debug('Schema validation OK', extra={'event': 'schema_validation_ok'})



def get_db_connection(db_url=None):
    target = db_url if db_url else _default_db_url()
    _ensure_parent(target)
    conn = sqlite3.connect(target, uri=target.startswith('file:'))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_url=None):
    os.makedirs(MIGRATIONS_DIR, exist_ok=True)
    with get_db_connection(db_url) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    apply_migrations(db_url)


def apply_migrations(db_url=None):
    with get_db_connection(db_url) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM migrations")
        applied_migrations = {row['name'] for row in cursor.fetchall()}

        migration_files = sorted(os.listdir(MIGRATIONS_DIR))
        for filename in migration_files:
            if filename.endswith(".sql") and filename not in applied_migrations:
                with open(os.path.join(MIGRATIONS_DIR, filename), 'r') as f:
                    sql_script = f.read()
                    cursor.executescript(sql_script)
                    cursor.execute("INSERT INTO migrations (name) VALUES (?)", (filename,))
                    conn.commit()
                    print(f"Applied migration: {filename}")
        _validate_schema(conn)
