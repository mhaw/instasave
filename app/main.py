# app/main.py
# GEMINI-TARGET: imports-and-setup v1
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Depends, Query
from fastapi import Path as PathParam
from fastapi.responses import (
    Response,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    FileResponse,
)
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import sqlite3
import os
import json
from pathlib import Path
from typing import Generator, List, Dict, Any
from datetime import datetime

from functools import lru_cache
import mimetypes
import logging

from app.settings import Settings, load_settings
from app.logging_config import setup_logging
from .scraper import start_scraping_thread
from .scraper import request_stop as request_scrape_stop
from .scraper import test_login as scraper_test_login
from .database import init_db
from .status_tracker import get_status


from pathlib import Path as _Path

# GEMINI-END: imports-and-setup

MEDIA_ROOT = _Path('media')
DB_PATH = _Path('data/instasave.db') if _Path('data/instasave.db').exists() else _Path('instasave.db')

def _get_post_media_subpath_by_index(code: str, idx: int) -> str:
    conn = sqlite3.connect(get_settings().DATABASE_URL)
    try:
        cur = conn.cursor()
        cur.execute('SELECT media_paths FROM posts WHERE url LIKE ?', (f'%/p/{code}/%',))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Post not found')
        arr = json.loads(row[0] or '[]')
        if idx < 0 or idx >= len(arr):
            raise HTTPException(status_code=404, detail='Media index out of range')
        return arr[idx]
    finally:
        conn.close()


# --- helpers -----------------------------------------------------------------
# GEMINI-TARGET: helpers v1
def set_flash_message(request: Request, message: str, category: str = "info") -> None:
    if "_messages" not in request.session:
        request.session["_messages"] = []
    request.session["_messages"].append({"message": message, "category": category})

def get_flash_messages(request: Request) -> List[Dict[str, str]]:
    return request.session.pop("_messages", [])

def sanitize_media_paths(paths: List[str]) -> List[str]:
    if not paths:
        return []
    out: List[str] = []
    for p in paths:
        if not p:
            continue
        sub = str(p).strip().lstrip("/")
        if (get_settings().MEDIA_ROOT / sub).is_file():
            out.append(sub)
    return out

def get_db() -> Generator[sqlite3.Connection, None, None]:
    # Allow usage across threads
    conn = sqlite3.connect(get_settings().DATABASE_URL, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
# GEMINI-END: helpers


setup_logging()

@lru_cache
def get_settings() -> Settings:
    return load_settings()

# --- lifecycle ---------------------------------------------------------------
# GEMINI-TARGET: startup v2
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    logger = logging.getLogger("instasave.main")
    logger.info("Database initialized.")
    yield
    # Shutdown (if any)

app = FastAPI(lifespan=lifespan)
app.state.settings = get_settings()
app.add_middleware(SessionMiddleware, secret_key=app.state.settings.SECRET_KEY)


templates = Jinja2Templates(directory="app/templates")

def format_timestamp(value):
    if value is None:
        return ""
    # Assuming value is a Unix timestamp or a string that can be converted to float
    try:
        # Convert to float first, then to int for datetime.fromtimestamp
        timestamp_float = float(value)
        dt_object = datetime.fromtimestamp(timestamp_float)
        return dt_object.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        # Handle cases where value is not a valid timestamp
        return str(value) # Return as is or handle error appropriately

templates.env.filters["ts"] = format_timestamp

app.mount("/media", StaticFiles(directory=app.state.settings.MEDIA_ROOT), name="media")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/static/elements", StaticFiles(directory="app/static/elements"), name="static_elements")
# GEMINI-END: startup


# --- UI routes ---------------------------------------------------------------
# GEMINI-TARGET: home-route v1
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "messages": get_flash_messages(request),
            "get_flash_messages": get_flash_messages,
        },
    )
# GEMINI-END: home-route


# GEMINI-TARGET: scrape-history-route v1
@app.get("/scrape/history", response_class=HTMLResponse)
async def scrape_history(request: Request) -> HTMLResponse:
    entries: List[Dict[str, Any]] = []
    log_dir: Path = get_settings().LOGS_DIR
    for log_file in sorted(log_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(log_file.read_text())
        except Exception:
            data = {}
        entries.append(
            {
                "filename": log_file.name,
                "timestamp": data.get("timestamp", "unknown"),
                "total": len(data.get("posts", [])),
                "errors": len([p for p in data.get("posts", []) if p.get("error")]),
            }
        )
    return templates.TemplateResponse(
        request,
        "scrape_history.html",
        {
            "request": request,
            "entries": entries,
            "get_flash_messages": get_flash_messages,
        },
    )

# --- auth helpers ------------------------------------------------------------
@app.get("/auth", response_class=HTMLResponse)
def auth_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "auth.html",
        {
            "request": request,
            "messages": get_flash_messages(request),
            "get_flash_messages": get_flash_messages,
        },
    )

@app.post("/auth/session")
async def set_sessionid(request: Request):
    form = await request.form()
    sessionid = str(form.get("sessionid", "")).strip()
    if not sessionid:
        set_flash_message(request, "Session ID is required.", "error")
        return RedirectResponse(url="/auth", status_code=302)
    # Persist to configured path
    try:
        path = get_settings().IG_SESSIONID_PATH
        path.write_text(sessionid)
        set_flash_message(request, f"Session ID saved to {path}.", "success")
    except Exception as e:
        set_flash_message(request, f"Failed to save Session ID: {e}", "error")
        return RedirectResponse(url="/auth", status_code=302)
    return RedirectResponse(url="/scrape/status/live", status_code=302)

@app.post("/auth/test", response_class=HTMLResponse)
def auth_test_login(request: Request):
    result = scraper_test_login()
    if result.get("ok"):
        set_flash_message(request, f"Login OK via {result.get('method')}. User: {result.get('username')}", "success")
    else:
        set_flash_message(request, f"Login failed via {result.get('method')}: {result.get('error')}", "error")
    return RedirectResponse(url="/auth", status_code=302)
# GEMINI-END: scrape-history-route


# --- scrape controls & status ------------------------------------------------
# GEMINI-TARGET: scrape-controls v1
@app.post("/scrape")
async def run_scraper_endpoint(request: Request, background_tasks: BackgroundTasks):
    """
    Kicks off scraping on a background thread, then redirects to live status.
    Returns a redirect because the client is typically a form/button click.
    """
    form = await request.form()
    date_range = form.get("date_range", "all")
    dry_run_val = str(form.get("dry_run", "")).lower()
    dry_run = dry_run_val in ("on", "true", "1", "yes")
    background_tasks.add_task(start_scraping_thread, date_range, dry_run)
    set_flash_message(
        request,
        ("Dry run started." if dry_run else "Scraping initiated successfully!") + " Check status page for updates.",
        "success",
    )
    return RedirectResponse(url="/scrape/status/live", status_code=302)

@app.get("/scrape/status", response_class=JSONResponse)
async def scrape_status() -> JSONResponse:
    return JSONResponse(get_status())

@app.get("/scrape/summary", response_class=JSONResponse)
def scrape_summary() -> JSONResponse:
    st = get_status()
    summary = st.get("summary", {}) if isinstance(st, dict) else {}
    out = {
        "logged_in_user": st.get("logged_in_user") if isinstance(st, dict) else None,
        "processed": summary.get("processed", st.get("processed", 0) if isinstance(st, dict) else 0),
        "skipped": summary.get("skipped", 0),
        "errors": summary.get("errors", 0),
        "dry_run": summary.get("dry_run", False),
        "start_time": st.get("start_time") if isinstance(st, dict) else None,
        "last_updated": st.get("last_updated") if isinstance(st, dict) else None,
    }
    return JSONResponse(out)

@app.get("/scrape/status/live", response_class=HTMLResponse)
def live_status(request: Request) -> HTMLResponse:
    status = get_status()
    try:
        # Show scraper-only log by default
        log_content = (get_settings().LOGS_DIR / "scraper.log").read_text()
    except FileNotFoundError:
        log_content = "Scraper log file not found."
    return templates.TemplateResponse(
        request,
        "status.html",
        {
            "request": request,
            "status": json.dumps(status, indent=2),
            "status_raw": status,
            "log_content": log_content,
            "get_flash_messages": get_flash_messages,
        },
    )

@app.post("/scrape/stop")
def stop_scrape(request: Request):
    request_scrape_stop()
    set_flash_message(request, "Stop requested. The scraper will stop shortly.", "warning")
    return RedirectResponse(url="/scrape/status/live", status_code=302)

@app.get("/scrape/logs", response_class=Response)
def scrape_logs_tail(lines: int = 200) -> Response:
    """Return the last N lines of the scraper log."""
    path = get_settings().LOGS_DIR / "scraper.log"
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
            out = "".join(all_lines[-max(1, min(lines, 2000)):])
    except FileNotFoundError:
        out = "Scraper log file not found."
    return Response(content=out, media_type="text/plain")
# GEMINI-END: scrape-controls


# --- posts listing -----------------------------------------------------------
# GEMINI-TARGET: posts-route v1
@app.get("/posts", response_class=HTMLResponse)
async def view_posts(
    request: Request,
    q: str = Query("", description="Search query for captions or tags"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(None, ge=1, le=100, description="Posts per page"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if limit is None:
        limit = settings.POSTS_PER_PAGE
    cursor = conn.cursor()

    base_count = "SELECT COUNT(*) FROM posts"
    base_query = "SELECT id, url, caption, timestamp, media_paths, SUBSTR(url, INSTR(url, '/p/') + 3, LENGTH(url) - INSTR(url, '/p/') - 3) AS code FROM posts"

    params: List[Any] = []
    where = ""
    if q:
        where = " WHERE caption LIKE ?"
        like = f"%{q}%"
        params.extend([like])

    order_by = "DESC" if sort_order.lower() == "desc" else "ASC"
    count_sql = base_count + where
    # Ensure numeric ordering even if stored as TEXT
    query_sql = f"{base_query}{where} ORDER BY CAST(timestamp AS INTEGER) {order_by} LIMIT ? OFFSET ?"

    # total count
    cursor.execute(count_sql, params)
    total_posts = int(cursor.fetchone()[0])

    # paging
    offset = (page - 1) * limit
    params_q = params + [limit, offset]

    cursor.execute(query_sql, params_q)
    posts = cursor.fetchall()

    results: List[Dict[str, Any]] = []
    for row in posts:
        post = dict(row)
        if post.get("media_paths"):
            try:
                post["media_paths"] = sanitize_media_paths(json.loads(post["media_paths"]))
            except Exception:
                post["media_paths"] = []
        else:
            post["media_paths"] = []
        results.append(post)

    total_pages = max(1, (total_posts + limit - 1) // limit)

    return templates.TemplateResponse(
        request,
        "posts.html",
        {
            "request": request,
            "posts": results,
            "query": q,
            "current_page": page,
            "total_pages": total_pages,
            "limit": limit,
            "sort_order": sort_order,
            "messages": get_flash_messages(request),
            "get_flash_messages": get_flash_messages,
        },
    )
# GEMINI-END: posts-route

@app.get('/m/{code}/{idx}')
def serve_media_item(code: str = PathParam(..., min_length=1), idx: int = PathParam(..., ge=0)):
    sub = _get_post_media_subpath_by_index(code, idx)
    root = get_settings().MEDIA_ROOT.resolve()
    try:
        full = (root / sub.lstrip('/')).resolve()
    except Exception:
        raise HTTPException(status_code=404, detail='Invalid media path')
    # Ensure the file resides under MEDIA_ROOT
    if root not in full.parents:
        raise HTTPException(status_code=404, detail='Invalid media path')
    if not full.is_file():
        raise HTTPException(status_code=404, detail='Media file missing')
    mt, _ = mimetypes.guess_type(str(full))
    return FileResponse(str(full), media_type=mt or 'application/octet-stream')

# --- logs & assets -----------------------------------------------------------
# GEMINI-TARGET: favicon v1
@app.get("/favicon.ico")
def favicon() -> FileResponse:
    path = Path("app/static/elements/instasave_favicon.png")
    if path.is_file():
        return FileResponse(path)
    # Return 204 if not provided, avoids 404 noise in logs
    return Response(status_code=204)
# GEMINI-END: favicon
