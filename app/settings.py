from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Literal
from pathlib import Path

class Settings(BaseSettings):
    IG_USERNAME: str = Field(..., min_length=1)
    IG_PASSWORD: str = Field(..., min_length=1)
    IG_COOKIES_PATH: Path = Path("insta_cookies.json")
    IG_SESSIONID_PATH: Path = Path("insta_sessionid.txt")
    SCRAPE_PAGE_SIZE: int = Field(50, ge=1, le=200)
    HEADLESS: bool = True
    LOG_LEVEL: Literal['DEBUG','INFO','WARNING','ERROR','CRITICAL'] = 'INFO'
    POSTS_PER_PAGE: int = Field(20, ge=1, le=100)
    DATABASE_URL: str = "data/instasave.db"
    MEDIA_ROOT: Path = Path("media")
    LOGS_DIR: Path = Path("logs")
    SECRET_KEY: str = Field("your-secret-key-please-change-me", min_length=1)

    class Config:
        env_file = '.env'
        extra = 'ignore'

def load_settings() -> 'Settings':
    return Settings()
