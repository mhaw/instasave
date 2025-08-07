# InstaSave
A simple Instagram post scraper that logs in via Playwright, scrapes your saved posts, and downloads images locally.

## ✨ Features
- Real-time scrape status with auto-refresh
- Downloaded media saved locally
- Supports login and cookie reuse
- Dockerized for ease of use
- Enhanced Post Display: View saved posts in a responsive grid layout.
- Rich Metadata: Each post displays its caption, original Instagram post link, and download date.
- Caption Preview: Captions are truncated with a "Show More" button for cleaner display.
- Interactive Media Lightbox: Click on any post to view its media (image or video) in a full-screen, interactive lightbox.
- Pagination: Navigate through all your saved posts with easy-to-use pagination controls.
- Sorting Options: Sort posts by newest or oldest first.
- Hashtag Extraction: Automatically extracts and stores hashtags from post captions.

## 📸 Screenshot
![screenshot](docs/ui.png)

## 💻 Local Setup
```bash
git clone https://github.com/mhaw/instasave.git
cd instasave
docker compose up --build
```

## 📂 Folder Overview
*   `app/` — FastAPI app, routes, scraper logic, templates
*   `data/` — Downloaded media
*   `logs/` — JSON logs of scrape metadata
*   `status.json` — Last scrape metadata

# InstaSave

## 📌 Project Purpose

InstaSave is a Python-based web app that:
- Logs into a **personal Instagram account** using **Playwright**
- Scrapes metadata from **saved posts**
- Downloads associated media locally (`/media/YYYY-MM-DD`)
- Stores everything in **SQLite**
- Provides a simple **searchable web UI** with advanced features like pagination, sorting, media lightbox, and caption previews.
- Fully runs in **Docker** and includes **pytest** test coverage

---

## ✨ Features

*   **Enhanced Post Display:** View saved posts in a responsive grid layout.
*   **Rich Metadata:** Each post displays its caption, original Instagram post link, and download date.
*   **Caption Preview:** Captions are truncated with a "Show More" button for cleaner display.
*   **Interactive Media Lightbox:** Click on any post to view its media (image or video) in a full-screen, interactive lightbox.
*   **Pagination:** Navigate through all your saved posts with easy-to-use pagination controls.
*   **Sorting Options:** Sort posts by newest or oldest first.
*   **Hashtag Extraction:** Automatically extracts and stores hashtags from post captions.

## ✨ Feature Wishlist
*   **AI transcription:** get a transcription of any audio
*   **AI classification and tagging** classify posts into topical buckets and extract relevant tags and keywords
*   **URL extraction** Automatically extracts any URLs from text and/or uses an AI agent to identify referenced links
---

## ⚙️ Stack Overview

| Component     | Tech                |
|---------------|---------------------|
| Web Server    | FastAPI             |
| Scraper       | Playwright (Chromium) |
| Database      | SQLite (via sqlite3) |
| UI            | Jinja2 + HTML/CSS + JavaScript |
| Container     | Docker + Docker Compose |
| Tests         | Pytest              |

---

## 🛠️ Setup Instructions

1. Copy `.env.template` ➜ `.env`  
   Add Instagram test credentials:
   ```env
   IG_USERNAME=your_test_username
   IG_PASSWORD=your_test_password
   ```
	2.	Build and start the app:

```bash
docker-compose up --build --force-recreate
```


	3.	Go to:
	•	Home: http://localhost:8000
	•	Scrape: Click button on homepage
	•	View results: http://localhost:8000/posts
	4.	Run tests:

```bash
docker-compose run --rm app pytest
```



⸻

📂 File Structure

```
instasave/
├── app/
│   ├── main.py              # FastAPI routes
│   ├── scraper.py           # Playwright scraping + media download
│   ├── templates/           # posts.html, index.html, status.html (Jinja templates)
├── media/                   # Downloaded media
├── tests/
│   └── test_scraper.py      # Pytest DB logic tests
├── docker-compose.yml       # Orchestration
├── Dockerfile               # Python + Playwright install
├── requirements.txt         # Python deps
├── pytest.ini               # Test config
└── .env.template            # Env var example
```


⸻

🔐 Important Notes
	•	No 2FA on test account
	•	Reuses insta_cookies.json to avoid login each time
	•	Logs stored in stdout (can be redirected for Docker logs)

⸻

🧪 Future Enhancements (Optional)
	•	Export to JSON, CSV, or Firestore
	•	Download all carousel images
	•	AI caption summarization
	•	Multi-user support (private use only for now)
	•	More robust tag management (e.g., separate tags table)
	•	AI tagging of posts

---
