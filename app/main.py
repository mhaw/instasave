from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import Response, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import logging
import sqlite3
import os

from .scraper import start_scraping_thread
from .database import init_db
from .status_tracker import get_status
import json

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

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/scrape", response_class=JSONResponse)
async def run_scraper_endpoint(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    date_range = data.get("date_range", "all")
    background_tasks.add_task(start_scraping_thread, date_range)
    return {"message": f"Scraping for {date_range} started in the background."}

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


@app.get("/posts", response_class=HTMLResponse)
async def view_posts(request: Request, q: str = "", page: int = 1, limit: int = 50, sort_order: str = "desc"):
    conn = sqlite3.connect("data/instasave.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    offset = (page - 1) * limit

    order_by = "DESC" if sort_order == "desc" else "ASC"

    if q:
        cursor.execute(f"SELECT * FROM saved_posts WHERE caption LIKE ? ORDER BY id {order_by} LIMIT ? OFFSET ?", (f"%{q}%", limit, offset))
        total_posts_cursor = conn.execute("SELECT COUNT(*) FROM saved_posts WHERE caption LIKE ?", (f"%{q}%",))
    else:
        cursor.execute(f"SELECT * FROM saved_posts ORDER BY id {order_by} LIMIT ? OFFSET ?", (limit, offset))
        total_posts_cursor = conn.execute("SELECT COUNT(*) FROM saved_posts")
    
    results = cursor.fetchall()
    total_posts = total_posts_cursor.fetchone()[0]
    conn.close()

    total_pages = (total_posts + limit - 1) // limit

    return templates.TemplateResponse(
        "posts.html",
        {
            "request": request,
            "posts": results,
            "query": q,
            "current_page": page,
            "total_pages": total_pages,
            "limit": limit,
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