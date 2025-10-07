
import json
from pathlib import Path
from datetime import datetime, timezone

STATUS_PATH = Path("logs/status.json")
STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
MAX_HISTORY = 5

def update_status(data: dict):
    now = datetime.now(timezone.utc)
    status = get_status()
    
    # Initialize status if it's the first time
    if "start_time" not in status:
        status["start_time"] = now.isoformat()

    # Update fields
    status.update(data)
    status["last_updated"] = now.isoformat()

    # Update history
    if "message" in data:
        history = status.get("history", [])
        history.insert(0, f"{now.isoformat()} - {data['message']}")
        status["history"] = history[:MAX_HISTORY]

    STATUS_PATH.write_text(json.dumps(status, indent=2))

def get_status() -> dict:
    if not STATUS_PATH.exists():
        return {"message": "Status not initialized."}

    content = STATUS_PATH.read_text().strip()
    if not content:
        return {"message": "Status file is empty."}

    status = json.loads(content)
    now = datetime.now(timezone.utc)

    if "start_time" in status:
        start_time = datetime.fromisoformat(status["start_time"])
        status["elapsed_time"] = str(now - start_time)

    processed = status.get("processed", 0)
    total = status.get("total", 0)

    if total > 0 and processed > 0:
        status["progress_percentage"] = f"{(processed / total) * 100:.2f}%"
        
        if "start_time" in status:
            elapsed_seconds = (now - start_time).total_seconds()
            if elapsed_seconds > 0:
                time_per_item = elapsed_seconds / processed
                remaining_items = total - processed
                remaining_seconds = remaining_items * time_per_item
                
                # Format remaining time
                m, s = divmod(remaining_seconds, 60)
                h, m = divmod(m, 60)
                status["time_remaining"] = f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

    return status

