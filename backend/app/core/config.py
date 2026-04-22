from pathlib import Path
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    APP_NAME: str = "JournalLM"
    DEBUG: bool = True

    DATABASE_URL: str = f"sqlite:///{PROJECT_ROOT / 'journallm.db'}"

    WHOOP_CLIENT_ID: str = ""
    WHOOP_CLIENT_SECRET: str = ""
    WHOOP_REDIRECT_URI: str = "http://localhost:8080/api/whoop/callback"
    WHOOP_SCOPES: str = "offline read:profile read:recovery read:cycles read:sleep read:workout"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    RESOLUTION_ENABLED: bool = True

    JOURNAL_SOURCE_DIR: str = str(PROJECT_ROOT.parent / "synthetic_journals")

    FRONTEND_URL: str = "http://localhost:3000"

    model_config = {"env_file": str(PROJECT_ROOT.parent / ".env"), "extra": "ignore"}


settings = Settings()
