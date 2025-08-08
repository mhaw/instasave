import os
import sqlite3
import pytest
import json
from pathlib import Path

from app.database import init_db

DB_FILE = "data/instasave.db"

@pytest.fixture(scope="module")
def db_connection():
    if Path(DB_FILE).exists():
        os.remove(DB_FILE)
    init_db()
    conn = sqlite3.connect(DB_FILE)
    yield conn
    conn.close()
    if Path(DB_FILE).exists():
        os.remove(DB_FILE)

def test_database_initialization(db_connection):
    cursor = db_connection.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='posts';")
    table = cursor.fetchone()
    assert table is not None, "posts table should exist."

def test_insert_sample_post(db_connection):
    sample_post = {
        "url": "https://instagram.com/p/test123",
        "caption": "Sample Caption #sample #test",
        "timestamp": "2024-08-06T12:00:00",
        "media_paths": json.dumps(["2024-08-06/sample.jpg"])
    }

    cursor = db_connection.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO posts (url, caption, timestamp, media_paths)
        VALUES (?, ?, ?, ?)
    """, (
        sample_post["url"],
        sample_post["caption"],
        sample_post["timestamp"],
        sample_post["media_paths"]
    ))
    db_connection.commit()

    post_id = cursor.lastrowid

    cursor.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", ("sample",))
    cursor.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", ("test",))
    db_connection.commit()

    cursor.execute("SELECT id FROM tags WHERE name = ?", ("sample",))
    tag_id_1 = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM tags WHERE name = ?", ("test",))
    tag_id_2 = cursor.fetchone()[0]

    cursor.execute("INSERT OR IGNORE INTO post_tags (post_id, tag_id) VALUES (?, ?)", (post_id, tag_id_1))
    cursor.execute("INSERT OR IGNORE INTO post_tags (post_id, tag_id) VALUES (?, ?)", (post_id, tag_id_2))
    db_connection.commit()

    cursor.execute("SELECT * FROM posts WHERE url = ?", (sample_post["url"],))
    result = cursor.fetchone()
    
    assert result is not None
    assert result[1] == sample_post["url"]
    assert result[2] == sample_post["caption"]
    assert result[3] == sample_post["timestamp"]
    assert result[4] == sample_post["media_paths"]

    cursor.execute("SELECT t.name FROM tags t JOIN post_tags pt ON t.id = pt.tag_id WHERE pt.post_id = ?", (post_id,))
    tags = {row[0] for row in cursor.fetchall()}
    assert tags == {"sample", "test"}
