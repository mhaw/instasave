import sqlite3

def init_db():
    conn = sqlite3.connect("data/instasave.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_url TEXT NOT NULL,
            post_pk INTEGER NOT NULL UNIQUE,
            caption TEXT,
            media_path TEXT,
            download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
