from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import Response, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import logging
import sqlite3
import os

from .scraper import start_scraping_thread
from .database import init_db
from .status_tracker import get_status
import json
from pathlib import Path

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")
app.mount("/media", StaticFiles(directory="media"), name="media")

@app.on_event("startup")
async def startup_event():
    # Ensure logs directory exists
    if not os.path.exists("logs"):
        os.makedirs("logs")
    init_db()
    logging.basicConfig(level=logging.INFO)
    logging.info("Database initialized.")

@app.get("/scrape/history", response_class=HTMLResponse)
async def scrape_history(request: Request):
    entries = []
    log_dir = Path("logs")
    for log_file in sorted(log_dir.glob("*.json"), reverse=True):
        data = json.loads(log_file.read_text())
        entries.append({
            "filename": log_file.name,
            "timestamp": data.get("timestamp", "unknown"),
            "total": len(data.get("posts", [])),
            "errors": len([p for p in data.get("posts", []) if p.get("error")]),
        })
    return templates.TemplateResponse("scrape_history.html", {
        "request": request,
        "entries": entries,
    })

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/scrape", response_class=JSONResponse)
async def run_scraper_endpoint(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    date_range = data.get("date_range", "all")
    background_tasks.add_task(start_scraping_thread, date_range)
    return RedirectResponse("/scrape/status/live", status_code=302)

@app.get("/scrape/status", response_class=JSONResponse)
async def scrape_status():
    return get_status()

@app.get("/scrape/status/live", response_class=HTMLResponse)
def live_status(request: Request):
    status = get_status()
    log_content = ""
    try:
        with open("logs/scraper.log", "r") as f:
            log_content = f.read()
    except FileNotFoundError:
        log_content = "Log file not found."

    return templates.TemplateResponse(
        "status.html",
        {
            "request": request,
            "status": json.dumps(status, indent=2),
            "log_content": log_content,
        },
    )


def load_scrape_log():
    conn = sqlite3.connect("data/instasave.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM saved_posts ORDER BY id DESC")
    posts = cursor.fetchall()
    conn.close()
    return [dict(post) for post in posts]

@app.get("/posts", response_class=HTMLResponse)
async def view_posts(request: Request, q: str = "", page: int = 1, limit: int = 50, sort_order: str = "desc"):
    posts = load_scrape_log()
    print(f"Type of posts list: {type(posts)}")

    for post in posts:
        print(f"Type of individual post: {type(post)}")
        # Create a new field with the correct relative path for the template
        post["display_media_path"] = post["media_path"].replace("media/", "")

    if q:
        q_lower = q.lower()
        posts = [p for p in posts if q_lower in p["caption"].lower() or (p["tags"] and q_lower in p["tags"].lower())]

    # Apply sorting based on sort_order
    if sort_order == "asc":
        posts.reverse() # Since load_scrape_log fetches DESC, reverse for ASC

    POSTS_PER_PAGE = 20 # As per new instructions
    start = (page - 1) * POSTS_PER_PAGE
    end = start + POSTS_PER_PAGE
    paginated_posts = posts[start:end]
    total_pages = (len(posts) + POSTS_PER_PAGE - 1) // POSTS_PER_PAGE

    return templates.TemplateResponse(
        "posts.html",
        {
            "request": request,
            "posts": paginated_posts,
            "query": q,
            "current_page": page,
            "total_pages": total_pages,
            "limit": POSTS_PER_PAGE, # Use POSTS_PER_PAGE as the limit
            "sort_order": sort_order
        }
    )

@app.get("/logs")
def get_logs():
    try:
        with open("logs/scraper.log", "r") as f:
            return Response(f.read(), media_type="text/plain")
    except FileNotFoundError:
        return Response("Log file not found", status_code=404)