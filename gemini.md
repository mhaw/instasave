# 🧠 Gemini Instructions: InstaSave (Agent-Safe, No Playwright)

## TL;DR for the Agent
- **Don’t assume single matches** — *count first*.
- **Edit by anchors** (unique markers), not brittle substrings.
- **Be idempotent** — re-runs should produce **0 changes** when state is correct.
- **Fail loudly** — print match counts, line numbers, and why you stopped.

---

## 1) Project Snapshot
**Purpose**
- Log into a *personal* Instagram account using an **existing session** (cookies/.env creds handled by the app, no headless browser).
- Pull **Saved posts** metadata and download associated media.
- Store metadata in **SQLite**.
- Serve a simple **FastAPI + Jinja** UI.
- Run under **Docker**; **pytest** included.

**Stack**
| Area | Tech |
|---|---|
| Web | FastAPI, Jinja2 |
| Data | SQLite (sqlite3) |
| Auth/Session | Re-usable session cookies and/or login helper (no Playwright) |
| Ops | Docker, Docker Compose, pytest |
| Logging | stdout and optional file logs in `settings.LOGS_DIR` |

**Paths**
```
instasave/
├─ app/
│  ├─ main.py            # routes
│  ├─ scraper.py         # Instagram fetch + media download (no browser)
│  ├─ settings.py        # env + paths
│  └─ templates/         # posts.html
├─ media/                # /media/YYYY-MM-DD
├─ tests/                # pytest
├─ Dockerfile
├─ docker-compose.yml
├─ requirements.txt
└─ .env.template
```

---

## 2) Runbook

### Setup
```bash
cp .env.template .env
# Required (example):
# IG_USERNAME=...
# IG_PASSWORD=...            # if used; otherwise rely on cookies
# IG_COOKIES_PATH=insta_cookies.json
# DB_PATH=/app/data/instasave.db
# LOGS_DIR=/app/logs
```

### Build & start
```bash
docker-compose up --build
```

### Use
- Home: http://localhost:8000
- Posts: http://localhost:8000/posts
- Trigger scrape via UI button

### Tests
```bash
docker-compose run --rm app pytest -q
```

**Notes**
- Prefer **cookies** to avoid repeated logins.
- App logs to stdout; optionally also to `LOGS_DIR/scraper.log`.

---

## 3) Agent Guardrails (prevent “Expected 1, Found 2”)

### A) Preflight: count before editing
```bash
# Show occurrences + line numbers
grep -n '@app.get("/logs")' app/main.py || true
```
If count ≠ 1, **do not** run a naive replace.

### B) Prefer anchor-based edits
Humans add stable markers; agent edits **between** them.

**Pattern**
```python
# GEMINI-TARGET: logs-endpoint v1
@app.get("/logs")
def get_logs():
    ...
# GEMINI-END: logs-endpoint
```

**Safe replace (idempotent)**
```jsonc
{
  "action": "replace_block_between",
  "file_path": "app/main.py",
  "start_marker": "# GEMINI-TARGET: logs-endpoint",
  "end_marker": "# GEMINI-END: logs-endpoint",
  "new_block": "# GEMINI-TARGET: logs-endpoint v2\n@app.get(\"/logs\")\ndef get_logs():\n    return {\"status\": \"ok\"}\n# GEMINI-END: logs-endpoint",
  "must_find_start": true,
  "must_find_end": true
}
```

### C) If no anchors exist, create them first (two-step)
1) Insert a marker above the **first intended** match:
```jsonc
{
  "action": "insert_above_first_match",
  "file_path": "app/main.py",
  "pattern": "^@app\\.get\\(\"/logs\"\\)",
  "insert": "# GEMINI-TARGET: logs-endpoint\n",
  "expected_insertions_min": 0,
  "expected_insertions_max": 1
}
```
2) Replace via anchors (as in **B**).

### D) Regex replaces must bound the count
```jsonc
{
  "action": "regex_replace",
  "file_path": "app/main.py",
  "pattern": "(?s)# GEMINI-TARGET: logs-endpoint.*?# GEMINI-END: logs-endpoint",
  "replacement": "# GEMINI-TARGET: logs-endpoint\\n...new block...\\n# GEMINI-END: logs-endpoint",
  "expected_replacements_min": 0,
  "expected_replacements_max": 1
}
```

### E) Idempotency checklist
Each mutation should:
- Do nothing if target state already present
- Be safe to re-run
- Print: `changed=0/1`, `file`, and `lines=[start:end]`

---

## 4) Implementation Notes & Known Gotchas

### 4.1 Saved-post **carousels** (multi-image/video)
- Iterate media items by a stable key (`media_id`), not by position.
- For each item, compute a deterministic filename:
  - `YYYY-MM-DD/{media_id}_{index}.{ext}`
- Store a per-item checksum (e.g., SHA256) to avoid duplicates/idempotent re-runs.

### 4.2 HTTP 206 **Partial Content** (range responses)
- If server responds with 206, ensure requests include correct `Range` logic **or** fall back to a full re-fetch.
- Verify `Content-Length` and final file size matches headers; if mismatch, retry with backoff and resume logic.
- Write to a temp file, then **atomic rename** to final path on success.

### 4.3 Timeouts / Retries / Backoff
- Use sane defaults (e.g., connect=10s, read=60s).
- Exponential backoff on 429/5xx with jitter.
- Cap retries; log last error cause.

### 4.4 Deduplication & Re-runs
- Primary key: `media_id` (or composite of `post_id` + `index`).
- Unique constraint in SQLite to prevent duplicate rows.
- On conflict: update metadata but skip re-download if checksum unchanged.

### 4.5 Filenames & Collisions
- Always include `media_id` in filenames; never rely only on timestamps or captions.
- Keep extensions derived from `Content-Type` when possible.

### 4.6 Logging
- Log **start/finish** per post and per media item with IDs.
- For download: log URL, headers (redact auth), bytes written, checksum.
- Keep a rotating file handler if `LOGS_DIR` is configured.

### 4.7 Pagination & Session
- Respect server-side paging cursors; **don’t** hammer endpoints.
- Refresh cookies if expired; fail early with a helpful error message.

---

## 5) Copy-Paste Fix Patterns

### 5.1 Replace a route safely (with anchors)
```jsonc
{
  "steps": [
    {
      "action": "ensure_anchor_block_exists",
      "file_path": "app/main.py",
      "anchor_name": "logs-endpoint",
      "start_marker": "# GEMINI-TARGET: logs-endpoint",
      "end_marker": "# GEMINI-END: logs-endpoint",
      "fallback_insertion_hint_regex": "^@app\\.get\\(\"/logs\"\\)"
    },
    {
      "action": "replace_block_between",
      "file_path": "app/main.py",
      "start_marker": "# GEMINI-TARGET: logs-endpoint",
      "end_marker": "# GEMINI-END: logs-endpoint",
      "new_block": "# GEMINI-TARGET: logs-endpoint\\n@app.get(\"/logs\")\\ndef get_logs():\\n    return {\"ok\": true}\\n# GEMINI-END: logs-endpoint"
    }
  ]
}
```

### 5.2 Insert after a unique line
```jsonc
{
  "action": "insert_after_match",
  "file_path": "app/main.py",
  "pattern": "^from fastapi import FastAPI.*$",
  "insert": "\\nfrom typing import Optional\\n",
  "expected_insertions_min": 0,
  "expected_insertions_max": 1
}
```

### 5.3 Upsert a config file
```jsonc
{
  "action": "upsert_file",
  "file_path": "app/logging.yaml",
  "content_sha256": "EXPECTED_HASH_OF_CONTENT",
  "content": "version: 1\\nhandlers:\\n  ...\\n"
}
```

### 5.4 Replace only if checksum matches
```jsonc
{
  "action": "replace_if_fingerprint_matches",
  "file_path": "app/main.py",
  "old_fingerprint": "sha256:abcdef123...",
  "new_content": "...",
  "on_mismatch": "abort_with_diff"
}
```

---

## 6) On Multiple Matches: Abort with Guidance
When count > 1:
- **Abort, don’t guess.**
- Print:
  - the **count**
  - **line numbers** for each match
  - a one-liner to add anchors

**Example message**
> Found 2 occurrences of `@app.get("/logs")` in `app/main.py` at lines 102 and 241.  
> Add `# GEMINI-TARGET: logs-endpoint` above the intended block and re-run.

---

## 7) Diagnostics to Run Before/After Edits
```bash
# Count candidate strings
grep -n '@app.get("/logs")' app/main.py || true

# Find anchors
grep -n 'GEMINI-TARGET' app/*.py || true

# Show function starts
grep -n '^def ' app/*.py || true

# Run tests
docker-compose run --rm app pytest -q || true
```

---

## 8) Backups & Rollback (Agent)
- After each mutation, print a compact changelog:
  - `file`, `changed=0/1`, `lines=[start:end]`, `reason`
- Keep `.gemini_backups/` with timestamped originals.
- If tests fail, **revert** the last change from backup.
- Prune backups **only** on overall success.

---

## 9) Reminders for Gemini
- Respect Instagram limits; use backoff and cursors.
- Validate `.env` before use; fail early with clear errors.
- Jinja rendering via FastAPI `TemplateResponse`.
- SQLite is MVP; plan for Firestore later if needed.
