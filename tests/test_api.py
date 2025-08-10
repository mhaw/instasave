import pytest
from fastapi.testclient import TestClient
from app.main import app as main_app # Import the main app as main_app
from app.database import init_db
from app.main import get_db
from app.config import settings
import sqlite3
from pathlib import Path

# Use a test database for tests
TEST_DATABASE_URL = "./test_instasave.db"

@pytest.fixture(scope="module")
def test_client():
    # Override the get_db dependency to use the test database
    def override_get_db():
        conn = sqlite3.connect(TEST_DATABASE_URL, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    main_app.dependency_overrides[get_db] = override_get_db

    # Initialize the test database before tests
    if Path(TEST_DATABASE_URL).exists():
        Path(TEST_DATABASE_URL).unlink()
    init_db(db_url=TEST_DATABASE_URL)

    with TestClient(main_app) as client:
        yield client

    # Clean up the test database after tests
    if Path(TEST_DATABASE_URL).exists():
        Path(TEST_DATABASE_URL).unlink()

    # Clear dependency overrides
    main_app.dependency_overrides.clear()


def test_read_main(test_client):
    response = test_client.get("/")
    assert response.status_code == 200
    assert "<h1>Welcome to InstaSave!</h1>" in response.text

def test_read_posts(test_client):
    response = test_client.get("/posts")
    assert response.status_code == 200
    assert "<h1>Saved Instagram Posts</h1>" in response.text

def test_read_scrape_status(test_client):
    response = test_client.get("/scrape/status/live")
    assert response.status_code == 200
    assert "<h1>Scraping Progress</h1>" in response.text

def test_read_scrape_history(test_client):
    response = test_client.get("/scrape/history")
    assert response.status_code == 200
    assert "<h1>Scrape History</h1>" in response.text


def test_posts_pagination(test_client):
    # Setup: Insert more posts than the default page size
    conn = sqlite3.connect(TEST_DATABASE_URL)
    cursor = conn.cursor()
    for i in range(30):
        cursor.execute(
            "INSERT INTO posts (url, caption, timestamp, media_paths) VALUES (?, ?, ?, ?)",
            (f"http://instasave.com/post{i}", f"Caption {i}", 1672531200 + i, "[]")
        )
    conn.commit()
    conn.close()

    # Test page 1
    response = test_client.get("/posts?page=1&limit=10")
    assert response.status_code == 200
    assert "Caption 29" in response.text
    assert "Caption 20" in response.text
    assert "Caption 19" not in response.text

    # Test page 2
    response = test_client.get("/posts?page=2&limit=10")
    assert response.status_code == 200
    assert "Caption 19" in response.text
    assert "Caption 10" in response.text
    assert "Caption 9" not in response.text
    assert "Caption 29" not in response.text

    # Test invalid page number
    response = test_client.get("/posts?page=0")
    assert response.status_code == 422 # Unprocessable Entity

    # Cleanup
    conn = sqlite3.connect(TEST_DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM posts")
    conn.commit()
    conn.close()

def test_posts_search(test_client):
    # Setup: Insert some test posts
    conn = sqlite3.connect(TEST_DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO posts (url, caption, timestamp, media_paths) VALUES (?, ?, ?, ?)",
        ("http://instasave.com/post1", "A post about cats", 1672531200, "[]")
    )
    cursor.execute(
        "INSERT INTO posts (url, caption, timestamp, media_paths) VALUES (?, ?, ?, ?)",
        ("http://instasave.com/post2", "A post about dogs", 1672531201, "[]")
    )
    conn.commit()
    conn.close()

    # Test search for "cats"
    response = test_client.get("/posts?q=cats")
    assert response.status_code == 200
    assert "A post about cats" in response.text
    assert "A post about dogs" not in response.text

    # Test search for "dogs"
    response = test_client.get("/posts?q=dogs")
    assert response.status_code == 200
    assert "A post about dogs" in response.text
    assert "A post about cats" not in response.text

    # Test search with no results
    response = test_client.get("/posts?q=birds")
    assert response.status_code == 200
    assert "No posts found." in response.text

    # Cleanup
    conn = sqlite3.connect(TEST_DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM posts")
    conn.commit()
    conn.close()

def test_posts_sorting(test_client):
    # Setup: Insert some test posts
    conn = sqlite3.connect(TEST_DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO posts (url, caption, timestamp, media_paths) VALUES (?, ?, ?, ?)",
        ("http://instasave.com/post1", "Oldest post", 1672531200, "[]")
    )
    cursor.execute(
        "INSERT INTO posts (url, caption, timestamp, media_paths) VALUES (?, ?, ?, ?)",
        ("http://instasave.com/post2", "Newest post", 1672531201, "[]")
    )
    conn.commit()
    conn.close()

    # Test default sort (desc)
    response = test_client.get("/posts")
    assert response.status_code == 200
    # Find the indices of the posts
    newest_index = response.text.find("Newest post")
    oldest_index = response.text.find("Oldest post")
    assert newest_index != -1 and oldest_index != -1
    assert newest_index < oldest_index

    # Test sort asc
    response = test_client.get("/posts?sort_order=asc")
    assert response.status_code == 200
    # Find the indices of the posts
    newest_index = response.text.find("Newest post")
    oldest_index = response.text.find("Oldest post")
    assert newest_index != -1 and oldest_index != -1
    assert oldest_index < newest_index

    # Cleanup
    conn = sqlite3.connect(TEST_DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM posts")
    conn.commit()
    conn.close()

def test_posts_lightbox_html(test_client):
    response = test_client.get("/posts")
    assert response.status_code == 200
    assert '<div class="lightbox-overlay" id="lightboxOverlay">' in response.text
    assert '<div class="lightbox-content">' in response.text
    assert '<a href="#" class="lightbox-close" id="lightboxClose">&times;</a>' in response.text
    assert '<div id="lightboxMedia"></div>' in response.text
