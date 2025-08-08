import os
import logging
import sqlite3
import json
import re
import signal
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
import requests
from instagrapi import Client
from instagrapi.types import Media
from queue import Queue, Empty
from threading import Thread, Lock
from tenacity import retry, stop_after_attempt, wait_exponential

os.makedirs("logs", exist_ok=True)
MEDIA_ROOT = Path("media")
DB_FILE = "data/instasave.db"
LOCK_FILE = Path("scraper.lock")

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/scraper.log")
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")
VERBOSE = os.getenv("VERBOSE", "false").lower() == "true"

post_queue = Queue()
dead_letter_queue = []
scraping_thread = None
scraping_lock = Lock()
shutdown_flag = False

def vprint(msg):
    if VERBOSE:
        logger.info(f"[VERBOSE] {msg}")

def save_media_bytes(date_str: str, filename: str, content: bytes) -> str:
    subdir = MEDIA_ROOT / date_str
    subdir.mkdir(parents=True, exist_ok=True)
    (subdir / filename).write_bytes(content)
    return f"{date_str}/{filename}"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def _download_single_media(session: requests.Session, media_item: Media, timestamp: datetime):
    if not media_item.thumbnail_url:
        return ""
    date_str = timestamp.strftime("%Y-%m-%d")
    
    filename = f"{media_item.pk}.jpg"
    url = media_item.thumbnail_url

    if media_item.media_type == 2 and media_item.video_url:
        filename = f"{media_item.pk}.mp4"
        url = media_item.video_url

    response = session.get(url, timeout=15)
    response.raise_for_status()
    subpath = save_media_bytes(date_str, filename, response.content)
    vprint(f"Downloaded media to {subpath}")
    return subpath

from concurrent.futures import ThreadPoolExecutor, as_completed

def download_media(session: requests.Session, post: Media, timestamp: datetime):
    media_paths = []
    if post.media_type == 8:  # Carousel
        if hasattr(post, 'resources') and post.resources:
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_media = {executor.submit(_download_single_media, session, media_item, timestamp): media_item for media_item in post.resources}
                for future in as_completed(future_to_media):
                    media_item = future_to_media[future]
                    try:
                        path = future.result()
                        if path:
                            media_paths.append(path)
                    except Exception as e:
                        logger.error(f"Failed to download media for post {media_item.pk}: {e}")
    else:  # Single photo or video
        try:
            path = _download_single_media(session, post, timestamp)
            if path:
                media_paths.append(path)
        except Exception as e:
            logger.error(f"Failed to download media for post {post.pk}: {e}")
    return json.dumps(media_paths)

from app.database import get_db_connection

def save_post_to_db(session: requests.Session, post: Media):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            caption_text = post.caption_text if post.caption_text else ""
            media_paths_json = download_media(session, post, post.taken_at)

            cursor.execute("""
                INSERT OR IGNORE INTO posts (url, caption, timestamp, media_paths)
                VALUES (?, ?, ?, ?)
            """, (
                f"https://www.instagram.com/p/{post.code}/",
                caption_text,
                post.taken_at.isoformat(),
                media_paths_json
            ))
            conn.commit()

            if cursor.lastrowid:
                post_id = cursor.lastrowid
                vprint(f"Saved post to DB: {post.code}")

                hashtags = re.findall(r"#(\w+)", caption_text)
                for tag_name in hashtags:
                    cursor.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
                    conn.commit()
                    cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                    tag_id = cursor.fetchone()['id']
                    cursor.execute("INSERT OR IGNORE INTO post_tags (post_id, tag_id) VALUES (?, ?)", (post_id, tag_id))
                    conn.commit()
            else:
                logger.warning(f"Post already exists in DB: {post.code}")

    except Exception as e:
        logger.error(f"Error saving post to DB: {e}")
        dead_letter_queue.append(post)

from app.status_tracker import update_status, get_status

def worker(session: requests.Session):
    while not shutdown_flag:
        try:
            post = post_queue.get(timeout=1)
            if post is None:
                break
            save_post_to_db(session, post)
            processed_count = get_status().get("processed", 0) + 1
            update_status({"processed": processed_count, "message": f"Processing post {post.code}"})
            post_queue.task_done()
        except Empty:
            continue

def start_scraping_thread(date_range):
    global scraping_thread
    if not scraping_lock.acquire(blocking=False):
        logger.warning("Scraping is already in progress.")
        return

    if LOCK_FILE.exists():
        logger.warning("Lockfile exists, another process may be running.")
        scraping_lock.release()
        return
        
    LOCK_FILE.touch()

    scraping_thread = Thread(target=scrape_saved_posts, args=(date_range,))
    scraping_thread.start()

def scrape_saved_posts(date_range):
    global shutdown_flag
    shutdown_flag = False
    update_status({"message": "Scrape starting...", "processed": 0, "total": 0, "history": []})
    
    cl = Client()
    try:
        update_status({"message": "Logging in to Instagram..."})
        cl.login(IG_USERNAME, IG_PASSWORD)
        
        saved_posts = []
        # ... (rest of the logic for fetching posts)

        update_status({"total": len(saved_posts), "message": f"Found {len(saved_posts)} posts to process."})

        with requests.Session() as session:
            worker_thread = Thread(target=worker, args=(session,)) 
            worker_thread.start()

            post_queue.join()
            post_queue.put(None)
            worker_thread.join()

        update_status({"message": "Scrape complete."})

    except Exception as e:
        logger.error(f"An error occurred during scraping: {e}")
        update_status({"message": f"Error: {e}"})
    finally:
        cl.logout()
        if dead_letter_queue:
            logger.warning(f"Dumping {len(dead_letter_queue)} failed posts to dead_letter.log")
            with open("logs/dead_letter.log", "a") as f:
                for post in dead_letter_queue:
                    f.write(f"{datetime.now().isoformat()} - {post.pk}\n")
        
        LOCK_FILE.unlink(missing_ok=True)
        scraping_lock.release()

def signal_handler(sig, frame):
    global shutdown_flag
    logger.info("Shutdown signal received. Finishing current tasks...")
    shutdown_flag = True

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
