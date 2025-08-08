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
            download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tags TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS post_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            media_path TEXT NOT NULL,
            FOREIGN KEY (post_id) REFERENCES saved_posts (id)
        )
    """)
    conn.commit()
    conn.close()
