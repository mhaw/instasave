import os
import logging
import sqlite3

os.makedirs("logs", exist_ok=True)  # Ensure logs folder exists
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
import requests
from instagrapi import Client
from instagrapi.types import Media
from queue import Queue
from threading import Thread

from .status_tracker import update_status, get_status
from .config import VERBOSE

def vprint(msg):
    if VERBOSE:
        logger.info(f"[VERBOSE] {msg}")

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
DB_FILE = "data/instasave.db"
MEDIA_DIR = Path("media")

post_queue = Queue()
scraping_thread = None

import re

def download_media(media: Media, timestamp: datetime):
    try:
        if not media.thumbnail_url:
            return ""
        date_folder = timestamp.strftime("%Y-%m-%d")
        save_dir = MEDIA_DIR / date_folder
        save_dir.mkdir(parents=True, exist_ok=True)

        filename = media.pk
        extension = "jpg" # Default to jpg
        if media.media_type == 2 and media.video_url:
            extension = "mp4"
            url = media.video_url
        else:
            url = media.thumbnail_url

        local_path = save_dir / f"{filename}.{extension}"

        if not local_path.exists():
            response = requests.get(url, timeout=15)
            with open(local_path, "wb") as f:
                f.write(response.content)
            vprint(f"Downloaded media to {local_path}")
        return str(local_path)
    except Exception as e:
        logger.error(f"Failed to download media for post {media.pk}: {e}")
        return ""

def save_post_to_db(post: Media):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        media_path = download_media(post, post.taken_at)

        # Extract hashtags
        caption_text = post.caption_text if post.caption_text else ""
        hashtags = re.findall(r"#(\w+)", caption_text)
        tags_str = ",".join(hashtags) # Store as comma-separated string

        cursor.execute("""
            INSERT OR IGNORE INTO saved_posts (post_url, post_pk, caption, media_path, download_date, tags)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            f"https://www.instagram.com/p/{post.code}/",
            post.pk,
            caption_text,
            media_path,
            post.taken_at.isoformat(),
            tags_str
        ))
        conn.commit()
        conn.close()
        if cursor.rowcount > 0:
            vprint(f"Saved post to DB: {post.code}")
        else:
            logger.warning(f"Post already exists in DB: {post.code}")
    except Exception as e:
        logger.error(f"Error saving post to DB: {e}")

def worker():
    while True:
        post = post_queue.get()
        if post is None:
            break
        save_post_to_db(post)
        update_status({"processed": get_status().get("processed", 0) + 1})
        post_queue.task_done()

def start_scraping_thread(date_range):
    global scraping_thread
    if scraping_thread and scraping_thread.is_alive():
        logger.warning("Scraping is already in progress.")
        return

    update_status({"current": "starting", "processed": 0, "queue": 0, "total": 0})

    scraping_thread = Thread(target=scrape_saved_posts, args=(date_range,))
    scraping_thread.start()

def scrape_saved_posts(date_range):
    update_status({"current": "initializing_instagrapi"})
    cl = Client()
    vprint("Instagrapi client initialized.")
    try:
        update_status({"current": "logging_in"})
        cl.login(IG_USERNAME, IG_PASSWORD)
        vprint("Login successful.")

        update_status({"current": "fetching_saved_posts"})
        saved_posts = []
        collections = cl.collections()
        for collection in collections:
            vprint(f"Fetching posts from collection: {collection.name}")
            medias = cl.collection_medias(collection.id)
            saved_posts.extend(medias)

        vprint(f"Found {len(saved_posts)} saved posts.")
        update_status({"total": len(saved_posts)})

        for post in saved_posts:
            post_queue.put(post)

        update_status({"current": "processing_queue", "queue": len(saved_posts)})

        worker_thread = Thread(target=worker)
        worker_thread.start()

        post_queue.join()
        post_queue.put(None)
        worker_thread.join()

        update_status({"current": "complete"})
        vprint("Scraping complete.")

    except Exception as e:
        logger.error(f"An error occurred during scraping: {e}")
        update_status({"current": "error"})
    finally:
        cl.logout()
