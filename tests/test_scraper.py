import os
import sqlite3
import pytest
from pathlib import Path

from app.database import init_db

DB_FILE = "instasave.db"

def test_database_initialization():
    # Remove existing DB
    if Path(DB_FILE).exists():
        os.remove(DB_FILE)

    # Run DB initializer
    init_db()
    assert Path(DB_FILE).exists(), "Database file should be created."

    # Check table schema
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='saved_posts';")
    table = cursor.fetchone()
    conn.close()

    assert table is not None, "saved_posts table should exist."

def test_insert_sample_post():
    sample_post = {
        "url": "https://instagram.com/p/test123",
        "caption": "Sample Caption",
        "timestamp": "2024-08-06T12:00:00",
        "media_url": "/media/2024-08-06/sample.jpg"
    }

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO saved_posts (url, caption, timestamp, media_url)
        VALUES (?, ?, ?, ?)
    """, (
        sample_post["url"],
        sample_post["caption"],
        sample_post["timestamp"],
        sample_post["media_url"]
    ))
    conn.commit()

    cursor.execute("SELECT * FROM saved_posts WHERE url = ?", (sample_post["url"],))
    result = cursor.fetchone()
    conn.close()

    assert result is not None, "Sample post should be inserted into the database."
