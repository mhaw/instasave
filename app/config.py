import os
from pathlib import Path

class Settings:
    DATABASE_URL: str = "data/instasave.db"
    MEDIA_ROOT: Path = Path("media")
    LOGS_DIR: Path = Path("logs")
    POSTS_PER_PAGE: int = 20
    SECRET_KEY: str = "your-secret-key" # CHANGE THIS IN PRODUCTION!
    VERBOSE: bool = os.getenv("INSTASAVE_VERBOSE", "False").lower() == "true"

settings = Settings()