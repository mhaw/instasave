import sqlite3
import os

DB_FILE = "data/instasave.db"
MIGRATIONS_DIR = "migrations"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(MIGRATIONS_DIR, exist_ok=True)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    apply_migrations()

def apply_migrations():
    with get_db_connection() as conn:
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
