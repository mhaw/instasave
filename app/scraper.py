import json
import logging
import os
import re
import signal
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Dict, Iterator, List, Optional

import requests
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import ClientForbiddenError, LoginRequired
from queue import Queue, Empty
from tenacity import retry, stop_after_attempt, wait_exponential

from app.database import get_db_connection
from app.settings import load_settings
from app.status_tracker import get_status, update_status

load_dotenv()

logger = logging.getLogger("instasave.scraper")

MEDIA_ROOT = Path("media")
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
LOCK_FILE = Path("scraper.lock")

IG_USERNAME = os.getenv("IG_USERNAME", "")
IG_PASSWORD = os.getenv("IG_PASSWORD", "")
IG_COOKIES_PATH = Path(os.getenv("IG_COOKIES_PATH", "insta_cookies.json"))
IG_SESSIONID = os.getenv("IG_SESSIONID", "")

SETTINGS = load_settings()

post_queue: "Queue[Any]" = Queue()
dead_letter_queue: List[Dict[str, Any]] = []
scraping_thread: Optional[Thread] = None
scraping_lock = Lock()
shutdown_flag = False


# ---------------------------------------------------------------------------
# media helpers
# ---------------------------------------------------------------------------

def save_media_bytes(date_str: str, filename: str, content: bytes) -> str:
    subdir = MEDIA_ROOT / date_str
    subdir.mkdir(parents=True, exist_ok=True)
    path = subdir / filename
    path.write_bytes(content)
    return f"{date_str}/{filename}"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def _download_single_media(session: requests.Session, media_item: Dict[str, Any], timestamp: datetime) -> str:
    if not media_item.get("thumbnail_url") and not media_item.get("video_url"):
        return ""
    date_str = timestamp.strftime("%Y-%m-%d")
    filename = f"{media_item.get('pk', 'media')}.jpg"
    url = media_item.get("thumbnail_url")

    if media_item.get("media_type") == 2 and media_item.get("video_url"):
        filename = f"{media_item.get('pk', 'media')}.mp4"
        url = media_item.get("video_url")

    response = session.get(url, timeout=15)
    response.raise_for_status()
    subpath = save_media_bytes(date_str, filename, response.content)
    logger.debug("Downloaded media", extra={"event": "media_downloaded", "pk": media_item.get("pk")})
    return subpath


def download_media(session: requests.Session, post: Dict[str, Any], timestamp: datetime) -> List[str]:
    media_paths: List[str] = []
    media_type = post.get("media_type")

    if media_type == 8 and post.get("resources"):
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(_download_single_media, session, media_item, timestamp): media_item
                for media_item in post.get("resources", [])
            }
            for future in as_completed(futures):
                try:
                    sub = future.result()
                    if sub:
                        media_paths.append(sub)
                except Exception:
                    logger.error(
                        "Failed carousel media download",
                        exc_info=True,
                        extra={"event": "media_download_failed", "pk": futures[future].get("pk")},
                    )
    else:
        try:
            sub = _download_single_media(session, post, timestamp)
            if sub:
                media_paths.append(sub)
        except Exception:
            logger.error(
                "Failed media download",
                exc_info=True,
                extra={"event": "media_download_failed", "pk": post.get("pk")},
            )
    return media_paths


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _ensure_list(obj: Any) -> List[Any]:
    if isinstance(obj, list):
        return obj
    if obj is None:
        return []
    return [obj]


def _safe_caption(post: Any) -> str:
    if isinstance(post, dict):
        return post.get("caption", "") or post.get("caption_text", "") or ""
    return getattr(post, "caption_text", None) or getattr(post, "caption", "") or ""


def _safe_timestamp_epoch(post: Any) -> int:
    if isinstance(post, dict):
        raw = post.get("taken_at") or post.get("device_timestamp")
        if isinstance(raw, (int, float)):
            return int(raw)
        if isinstance(raw, str):
            try:
                return int(datetime.fromisoformat(raw.replace("Z", "")).timestamp())
            except Exception:
                pass
    taken_at = getattr(post, "taken_at", None)
    if hasattr(taken_at, "timestamp"):
        try:
            return int(taken_at.timestamp())
        except Exception:
            pass
    return int(datetime.utcnow().timestamp())


def _safe_code(post: Any) -> str:
    if isinstance(post, dict):
        return post.get("code") or str(post.get("pk") or post.get("id") or "")
    return getattr(post, "code", "") or str(getattr(post, "pk", "") or getattr(post, "id", "") or "")


def _media_iterables(post: Any) -> List[Dict[str, Any]]:
    mtype = post.get("media_type") if isinstance(post, dict) else getattr(post, "media_type", None)
    if mtype == 8:
        resources = post.get("resources") if isinstance(post, dict) else getattr(post, "resources", None)
        return _ensure_list(resources)
    return [_coerce_media_dict(post)]


def _coerce_media_dict(post: Any) -> Dict[str, Any]:
    if isinstance(post, dict):
        return post
    attrs = {k: getattr(post, k, None) for k in ["pk", "media_type", "thumbnail_url", "video_url"]}
    if hasattr(post, "resources"):
        attrs["resources"] = [
            _coerce_media_dict(res)
            for res in getattr(post, "resources", [])
        ]
    return attrs


def save_post_to_db(session: requests.Session, post: Any) -> None:
    code = _safe_code(post)
    url = f"https://www.instagram.com/p/{code}/"
    caption = _safe_caption(post)
    ts_epoch = _safe_timestamp_epoch(post)
    ts_dt = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)

    media_item_dict = _coerce_media_dict(post)
    media_paths = download_media(session, media_item_dict, ts_dt)

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO posts (url, caption, timestamp, media_paths)
            VALUES (?, ?, ?, ?)
            """,
            (url, caption, ts_epoch, json.dumps(media_paths)),
        )
        if cur.rowcount == 0:
            cur.execute(
                """
                UPDATE posts SET caption = ?, timestamp = ?, media_paths = ?
                WHERE url = ?
                """,
                (caption, ts_epoch, json.dumps(media_paths), url),
            )

        tags = {match.lower() for match in re.findall(r"#([A-Za-z0-9_]+)", caption)}
        if tags:
            cur.execute("SELECT id FROM posts WHERE url = ?", (url,))
            row = cur.fetchone()
            if row:
                post_id = row[0]
                for tag in tags:
                    cur.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
                    cur.execute("SELECT id FROM tags WHERE name = ?", (tag,))
                    tag_row = cur.fetchone()
                    if tag_row:
                        cur.execute(
                            "INSERT OR IGNORE INTO post_tags (post_id, tag_id) VALUES (?, ?)",
                            (post_id, tag_row[0]),
                        )
        conn.commit()


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except Exception:
        logger.debug("Failed to unlink %s", path, exc_info=True, extra={"event": "session_cleanup_failed"})


def _load_cookies_session(client: Client) -> bool:
    if not IG_COOKIES_PATH.exists():
        return False
    try:
        logger.info("Trying cookie-based session", extra={"event": "login_attempt", "method": "cookies"})
        try:
            client.load_settings(str(IG_COOKIES_PATH))  # type: ignore[attr-defined]
        except Exception:
            data = json.loads(IG_COOKIES_PATH.read_text())
            if hasattr(client, "set_settings"):
                client.set_settings(data)  # type: ignore[attr-defined]
        client.get_timeline_feed()
        return True
    except Exception:
        logger.warning("Cookie session invalid; removing file", extra={"event": "login_cookie_failed"})
        _remove_file(IG_COOKIES_PATH)
        return False


def _load_sessionid_from_file() -> Optional[str]:
    sid_path = load_settings().IG_SESSIONID_PATH
    if sid_path.exists():
        value = sid_path.read_text().strip()
        if value:
            return value
    return None


def _login_with_sessionid(client: Client, sessionid: str, method: str) -> bool:
    try:
        logger.info("Trying sessionid login", extra={"event": "login_attempt", "method": method})
        client.login_by_sessionid(sessionid)
        return True
    except Exception:
        logger.warning("Sessionid login failed", extra={"event": "login_sessionid_failed", "method": method})
        return False


def _login_with_credentials(client: Client) -> bool:
    if not IG_USERNAME or not IG_PASSWORD:
        return False
    try:
        logger.info("Trying username/password login", extra={"event": "login_attempt", "method": "credentials"})
        client.login(IG_USERNAME, IG_PASSWORD)
        return True
    except Exception:
        logger.error("Username/password login failed", exc_info=True, extra={"event": "login_credentials_failed"})
        return False


def _persist_session_settings(client: Client) -> None:
    try:
        IG_COOKIES_PATH.write_text(json.dumps(client.get_settings()))  # type: ignore[attr-defined]
    except Exception:
        logger.warning("Failed to persist session cookies", extra={"event": "cookie_persist_failed"})


def _ensure_authenticated(client: Client) -> str:
    if _load_cookies_session(client):
        return "cookies"

    sid_from_file = _load_sessionid_from_file()
    if sid_from_file and _login_with_sessionid(client, sid_from_file, "sessionid_file"):
        _persist_session_settings(client)
        return "sessionid_file"

    if IG_SESSIONID and _login_with_sessionid(client, IG_SESSIONID, "sessionid_env"):
        _persist_session_settings(client)
        return "sessionid_env"

    if _login_with_credentials(client):
        _persist_session_settings(client)
        return "credentials"

    raise RuntimeError("Unable to authenticate with provided credentials or session id")


def test_login() -> Dict[str, Any]:
    client = Client()
    method = None
    try:
        method = _ensure_authenticated(client)
        username = getattr(client, "username", None) or IG_USERNAME
        return {"ok": True, "method": method, "username": username, "error": None}
    except Exception as exc:
        return {"ok": False, "method": method or "unknown", "username": None, "error": str(exc)}
    finally:
        try:
            client.logout()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Scraper orchestration
# ---------------------------------------------------------------------------

def request_stop() -> None:
    global shutdown_flag
    shutdown_flag = True
    try:
        update_status({"message": "Stop requested", "running": False})
    except Exception:
        pass


def start_scraping_thread(date_range: str, dry_run: bool = False) -> None:
    global scraping_thread
    if not scraping_lock.acquire(blocking=False):
        logger.warning("Scraping already in progress", extra={"event": "scrape_already_running"})
        return

    if LOCK_FILE.exists():
        logger.warning("Lock file present, aborting new scrape", extra={"event": "lockfile_exists"})
        scraping_lock.release()
        return

    try:
        LOCK_FILE.touch()
        scraping_thread = Thread(target=scrape_saved_posts, args=(date_range, dry_run), daemon=True)
        scraping_thread.start()
    except Exception:
        LOCK_FILE.unlink(missing_ok=True)
        scraping_lock.release()
        raise


def fetch_saved_items(client: Client, amount: Optional[int] = None, page_sleep: float = 0.8) -> Iterator[Dict[str, Any]]:
    fetched = 0
    max_id: Optional[str] = None
    while True:
        params: Dict[str, Any] = {"include_igtv_preview": "false"}
        if max_id:
            params["max_id"] = max_id
        data = client.private_request("feed/saved/posts/", params=params)
        items = data.get("items", []) or []
        for item in items:
            yield item
            fetched += 1
            if amount and fetched >= amount:
                return
        max_id = data.get("next_max_id")
        if not max_id:
            break
        time.sleep(page_sleep)


def ig_timestamp(item: Dict[str, Any]) -> str:
    raw = item.get("taken_at") or item.get("device_timestamp")
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(int(raw), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return datetime.utcnow().isoformat() + "Z"


def save_bytes(date_str: str, fname: str, content: bytes) -> Optional[str]:
    if not content:
        return None
    path = MEDIA_ROOT / date_str / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return f"{date_str}/{fname}"


def best_image_url(item: Dict[str, Any]) -> Optional[str]:
    iv2 = item.get("image_versions2") or item.get("image_versions2_candidates")
    if not iv2:
        return None
    candidates = iv2.get("candidates") or []
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.get("width", 0)).get("url")


def best_video_url(item: Dict[str, Any]) -> Optional[str]:
    versions = item.get("video_versions") or []
    if not versions:
        return None
    return max(versions, key=lambda v: (v.get("bitrate", 0), v.get("width", 0))).get("url")


def download_url(url: str) -> bytes:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content


def scrape_saved_posts(date_range: str, dry_run: bool = False) -> None:
    global shutdown_flag
    shutdown_flag = False
    update_status(
        {
            "message": "Dry run starting..." if dry_run else "Scrape starting...",
            "processed": 0,
            "total": 0,
            "history": [],
            "running": True,
            "summary": {"processed": 0, "skipped": 0, "errors": 0, "dry_run": dry_run},
        }
    )

    client = Client()
    try:
        update_status({"message": "Logging in to Instagram..."})
        method = _ensure_authenticated(client)
        update_status({"message": f"Logged in via {method}"})
        update_status({"logged_in_user": getattr(client, "username", None) or IG_USERNAME})

        cutoff_dt: Optional[datetime] = None
        if isinstance(date_range, str) and date_range.isdigit():
            cutoff_dt = datetime.utcnow() - timedelta(days=int(date_range))

        downloaded_count = 0
        skipped_count = 0
        error_count = 0

        try:
            for item in fetch_saved_items(client, amount=SETTINGS.SCRAPE_PAGE_SIZE):
                if shutdown_flag:
                    logger.info("Stop requested; exiting loop.", extra={"event": "stop_requested"})
                    break
                media = item.get("media") or item.get("post") or item
                media_dict = _coerce_media_dict(media)
                code = media_dict.get("code") or media_dict.get("pk") or str(media_dict.get("id", ""))
                ts_iso = ig_timestamp(media_dict)
                date_str = ts_iso[:10]

                if cutoff_dt:
                    try:
                        when = datetime.fromisoformat(ts_iso.replace("Z", ""))
                        if when < cutoff_dt:
                            logger.info("Reached cutoff date; stopping.", extra={"event": "cutoff_reached"})
                            break
                    except Exception:
                        pass

                logger.info("Post fetched", extra={"event": "post_fetched", "code": code, "media_type": media_dict.get("media_type")})

                if dry_run:
                    downloaded_count += 1
                    continue

                media_paths = []

                def add_media(obj: Dict[str, Any], suffix: str) -> None:
                    nonlocal media_paths
                    vid = best_video_url(obj)
                    if vid:
                        sub = save_bytes(date_str, f"{media_dict.get('pk', 'media')}_{suffix}.mp4", download_url(vid))
                        if sub:
                            media_paths.append(sub)
                        return
                    img = best_image_url(obj)
                    if img:
                        sub = save_bytes(date_str, f"{media_dict.get('pk', 'media')}_{suffix}.jpg", download_url(img))
                        if sub:
                            media_paths.append(sub)

                if media_dict.get("media_type") == 8:
                    for idx, res in enumerate(media_dict.get("resources", [])):
                        add_media(res, str(idx))
                else:
                    add_media(media_dict, "0")

                if not media_paths:
                    logger.warning("No downloadable media for code=%s", code, extra={"event": "no_media_found", "code": code})
                    dead_letter_queue.append(media_dict)
                    skipped_count += 1
                    continue

                try:
                    save_post_to_db(requests.Session(), media_dict)
                    downloaded_count += 1
                except Exception:
                    error_count += 1
                    logger.error("Failed to save post", exc_info=True, extra={"event": "save_failed", "code": code})

            summary = {
                "processed": downloaded_count,
                "skipped": skipped_count,
                "errors": error_count,
                "dry_run": dry_run,
            }
            update_status({"summary": summary, "processed": downloaded_count, "running": False})
            logger.info(
                "Dry run: %d items processed." if dry_run else "Saved %d posts/items.",
                downloaded_count,
                extra={"event": "dry_run_complete" if dry_run else "scrape_complete", **summary},
            )
        except ClientForbiddenError as exc:
            if "user_has_logged_out" in str(exc):
                update_status({"message": "Instagram logged us out. Refresh session cookie."})
                _remove_file(IG_COOKIES_PATH)
                sid_path = load_settings().IG_SESSIONID_PATH
                _remove_file(sid_path)
            raise

    except (RuntimeError, LoginRequired) as exc:
        logger.error("Authentication error during scraping", exc_info=True, extra={"event": "scrape_failed_auth"})
        update_status({"message": f"Authentication error: {exc}"})
    except ClientForbiddenError as exc:
        logger.error("Forbidden error during scraping", exc_info=True, extra={"event": "scrape_failed_forbidden"})
        update_status({"message": f"Instagram API rejected the request: {exc}"})
    except Exception as exc:
        logger.error("An error occurred during scraping", exc_info=True, extra={"event": "scrape_failed"})
        update_status({"message": f"Error: {exc}"})
    finally:
        try:
            client.logout()
        except Exception:
            pass
        if dead_letter_queue:
            logger.warning(
                "Dumping %d failed posts to dead_letter.log",
                len(dead_letter_queue),
                extra={"event": "dead_letter_dump", "count": len(dead_letter_queue)},
            )
            with open("logs/dead_letter.log", "a", encoding="utf-8") as fh:
                for post in dead_letter_queue:
                    pid = post.get("code") or post.get("pk") or "unknown"
                    fh.write(f"{datetime.now().isoformat()} - {pid}\n")
        LOCK_FILE.unlink(missing_ok=True)
        scraping_lock.release()


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------

def signal_handler(sig, frame) -> None:
    global shutdown_flag
    logger.info("Shutdown signal received. Finishing current tasks...", extra={"event": "shutdown_signal"})
    shutdown_flag = True


def init_signal_handlers() -> None:
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


init_signal_handlers()
