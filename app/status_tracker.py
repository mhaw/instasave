import json
from pathlib import Path

STATUS_PATH = Path("logs/status.json")

def update_status(data: dict):
    STATUS_PATH.write_text(json.dumps(data, indent=2))

def get_status() -> dict:
    if STATUS_PATH.exists():
        content = STATUS_PATH.read_text().strip()
        if content:
            return json.loads(content)
    return {"message": "Status not initialized."}
