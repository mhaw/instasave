import pytest
from fastapi.testclient import TestClient
from app.main import app as main_app # Import the main app as main_app
from app.database import init_db, get_db
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

    with TestClient(main_app, lifespan="on") as client:
        yield client

    # Clean up the test database after tests
    if Path(TEST_DATABASE_URL).exists():
        Path(TEST_DATABASE_URL).unlink()

    # Clear dependency overrides
    main_app.dependency_overrides.clear()


def test_read_main(test_client):
    response = test_client.get("/")
    assert response.status_code == 200
    assert "<h1 class=\"text-3xl font-bold mb-4\">Welcome to InstaSave!</h1>" in response.text

def test_read_posts(test_client):
    response = test_client.get("/posts")
    assert response.status_code == 200
    assert "<h1>Saved Instagram Posts</h1>" in response.text

def test_read_scrape_status(test_client):
    response = test_client.get("/scrape/status/live")
    assert response.status_code == 200
    assert "<h2>Scraping Progress</h2>" in response.text

def test_read_scrape_history(test_client):
    response = test_client.get("/scrape/history")
    assert response.status_code == 200
    assert "<h1 class=\"text-2xl mb-4\">Scrape History</h1>" in response.text