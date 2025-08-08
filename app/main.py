# app/main.py
# GEMINI-TARGET: imports-and-setup v1
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Depends, Query
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
import logging
import sqlite3
import os
import json
from pathlib import Path
from typing import Generator, List, Dict, Any
from datetime import datetime

from .scraper import start_scraping_thread
from .database import init_db
from .status_tracker import get_status
from .config import settings

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

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

app.mount("/media", StaticFiles(directory=settings.MEDIA_ROOT), name="media")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
# GEMINI-END: imports-and-setup


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
        if (settings.MEDIA_ROOT / sub).is_file():
            out.append(sub)
    return out

def get_db() -> Generator[sqlite3.Connection, None, None]:
    # Allow usage across threads
    conn = sqlite3.connect(settings.DATABASE_URL, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
# GEMINI-END: helpers


# --- lifecycle ---------------------------------------------------------------
# GEMINI-TARGET: startup v2
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Path(settings.LOGS_DIR).mkdir(parents=True, exist_ok=True)
    init_db()
    logging.basicConfig(level=logging.INFO)
    logging.info("Database initialized.")
    yield
    # Shutdown (if any)

app = FastAPI(lifespan=lifespan)
# GEMINI-END: startup


# --- UI routes ---------------------------------------------------------------
# GEMINI-TARGET: home-route v1
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "messages": get_flash_messages(request),
            "get_flash_messages": get_flash_messages,
        },
    )
# GEMINI-END: home-route


# GEMINI-TARGET: scrape-history-route v1
@app.get("/scrape/history", response_class=HTMLResponse)
async def scrape_history(request: Request) -> HTMLResponse:
    entries: List[Dict[str, Any]] = []
    log_dir: Path = settings.LOGS_DIR
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
        "scrape_history.html", {"entries": entries, "get_flash_messages": get_flash_messages}
    )
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
    background_tasks.add_task(start_scraping_thread, date_range)
    set_flash_message(
        request,
        "Scraping initiated successfully! Check status page for updates.",
        "success",
    )
    return RedirectResponse(url="/scrape/status/live", status_code=302)

@app.get("/scrape/status", response_class=JSONResponse)
async def scrape_status() -> JSONResponse:
    return JSONResponse(get_status())

@app.get("/scrape/status/live", response_class=HTMLResponse)
def live_status(request: Request) -> HTMLResponse:
    status = get_status()
    try:
        log_content = (settings.LOGS_DIR / "scraper.log").read_text()
    except FileNotFoundError:
        log_content = "Log file not found."
    return templates.TemplateResponse(
        request,
        "status.html",
        {
            "status": json.dumps(status, indent=2),
            "log_content": log_content,
            "get_flash_messages": get_flash_messages,
        },
    )
# GEMINI-END: scrape-controls


# --- posts listing -----------------------------------------------------------
# GEMINI-TARGET: posts-route v1
@app.get("/posts", response_class=HTMLResponse)
async def view_posts(
    request: Request,
    q: str = Query("", description="Search query for captions or tags"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(getattr(settings, "POSTS_PER_PAGE", 25), ge=1, le=100, description="Posts per page"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    cursor = conn.cursor()

    base_count = "SELECT COUNT(*) FROM posts"
    base_query = "SELECT id, url, caption, timestamp, media_paths FROM posts"

    params: List[Any] = []
    where = ""
    if q:
        where = " WHERE caption LIKE ?"
        like = f"%{q}%"
        params.extend([like])

    order_by = "DESC" if sort_order.lower() == "desc" else "ASC"
    count_sql = base_count + where
    query_sql = f"{base_query}{where} ORDER BY timestamp {order_by} LIMIT ? OFFSET ?"

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


# --- logs & assets -----------------------------------------------------------
# GEMINI-TARGET: logs-endpoint v1
@app.get("/logs")
def get_logs() -> Response:
    try:
        content = (settings.LOGS_DIR / "scraper.log").read_text()
        return Response(content, media_type="text/plain")
    except FileNotFoundError:
        return Response("Log file not found", status_code=404)
# GEMINI-END: logs-endpoint


# GEMINI-TARGET: favicon v1
@app.get("/favicon.ico")
def favicon() -> FileResponse:
    path = Path("static/favicon.ico")
    if path.is_file():
        return FileResponse(path)
    # Return 204 if not provided, avoids 404 noise in logs
    return Response(status_code=204)
# GEMINI-END: favicon