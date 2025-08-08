
import os
import sqlite3
import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.database import init_db
from app.scraper import save_post_to_db, download_media, _download_single_media, scrape_saved_posts
from app.status_tracker import get_status, update_status

DB_FILE = "data/test_instasave.db"
MEDIA_DIR = Path("media_test")

@pytest.fixture(scope="function")
def db_connection():
    if Path(DB_FILE).exists():
        os.remove(DB_FILE)
    with patch('app.database.DB_FILE', DB_FILE):
        init_db()
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        yield conn
        conn.close()
        if Path(DB_FILE).exists():
            os.remove(DB_FILE)

@pytest.fixture
def mock_instagrapi_client():
    with patch('app.scraper.Client') as mock_client:
        yield mock_client

@pytest.fixture
def mock_requests_session():
    with patch('app.scraper.requests.Session') as mock_session:
        yield mock_session


def test_carousel_post(db_connection, mock_requests_session):
    mock_post = MagicMock()
    mock_post.code = "testcarousel"
    mock_post.caption_text = "A test carousel"
    mock_post.taken_at.isoformat.return_value = "2025-08-08T12:00:00"
    mock_post.media_type = 8  # Carousel
    mock_post.pk = "carousel123"

    # Mock the resources for the carousel
    mock_resource1 = MagicMock()
    mock_resource1.pk = "res1"
    mock_resource1.thumbnail_url = "http://example.com/res1.jpg"
    mock_resource1.media_type = 1

    mock_resource2 = MagicMock()
    mock_resource2.pk = "res2"
    mock_resource2.video_url = "http://example.com/res2.mp4"
    mock_resource2.media_type = 2

    mock_post.resources = [mock_resource1, mock_resource2]

    with patch('app.scraper._download_single_media') as mock_download:
        mock_download.side_effect = [
            "2025-08-08/res1.jpg",
            "2025-08-08/res2.mp4"
        ]
        save_post_to_db(mock_requests_session, mock_post)

    cursor = db_connection.cursor()
    cursor.execute("SELECT * FROM posts WHERE url = ?", (f"https://www.instagram.com/p/{mock_post.code}/",))
    result = cursor.fetchone()

    assert result is not None
    media_paths = json.loads(result['media_paths'])
    assert len(media_paths) == 2
    assert "2025-08-08/res1.jpg" in media_paths
    assert "2025-08-08/res2.mp4" in media_paths

