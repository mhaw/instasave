Absolutely! Here’s a gemini.md file you can drop into your repo root. It explains the app’s purpose, architecture, setup, and enhancement points — perfect for your coding assistant (human or AI):

⸻


# 🧠 Gemini Instructions: InstaSave

## 📌 Project Purpose

InstaSave is a Python-based web app that:
- Logs into a **personal Instagram account** using **Playwright**
- Scrapes metadata from **saved posts**
- Downloads associated media locally (`/media/YYYY-MM-DD`)
- Stores everything in **SQLite**
- Provides a simple **searchable web UI**
- Fully runs in **Docker** and includes **pytest** test coverage

---

## ⚙️ Stack Overview

| Component     | Tech                |
|---------------|---------------------|
| Web Server    | FastAPI             |
| Scraper       | Playwright (Chromium) |
| Database      | SQLite (via sqlite3) |
| UI            | Jinja2 + HTML/CSS   |
| Container     | Docker + Docker Compose |
| Tests         | Pytest              |

---

## 🛠️ Setup Instructions

1. Copy `.env.template` ➜ `.env`  
   Add Instagram test credentials:
   ```env
   IG_USERNAME=your_test_username
   IG_PASSWORD=your_test_password

	2.	Build and start the app:

docker-compose up --build


	3.	Go to:
	•	Home: http://localhost:8000
	•	Scrape: Click button on homepage
	•	View results: http://localhost:8000/posts
	4.	Run tests:

docker-compose run --rm app pytest



⸻

📂 File Structure

instasave/
├── app/
│   ├── main.py              # FastAPI routes
│   ├── scraper.py           # Playwright scraping + media download
│   ├── templates/           # posts.html (Jinja template)
├── media/                   # Downloaded media
├── tests/
│   └── test_scraper.py      # Pytest DB logic tests
├── docker-compose.yml       # Orchestration
├── Dockerfile               # Python + Playwright install
├── requirements.txt         # Python deps
├── pytest.ini               # Test config
└── .env.template            # Env var example


⸻

🔐 Important Notes
	•	No 2FA on test account
	•	Reuses insta_cookies.json to avoid login each time
	•	Logs stored in stdout (can be redirected for Docker logs)

⸻

🧪 Future Enhancements (Optional)
	•	Export to JSON, CSV, or Firestore
	•	Download all carousel images
	•	Add tag recommendations via LLM
	•	AI caption summarization
	•	Multi-user support (private use only for now)

⸻

🧠 Quick Reminders for Gemini
	•	Avoid triggering Instagram rate limits: add waits or delays if scraping is expanded
	•	All .env values should be validated before use
	•	FastAPI’s request object is used to serve Jinja pages
	•	SQLite is used for quick MVP portability — migrate to Firestore if scaling
