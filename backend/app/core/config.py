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

    BACKFILL_RATE_LIMIT_SECONDS: float = 1.0
    BACKFILL_LOG_DIR: str = str(PROJECT_ROOT / "data" / "backfill_logs")
    BACKFILL_SNAPSHOT_DIR: str | None = None

    # Step 7 §19 — dashboard data-layer tunables.
    DASHBOARD_INNER_CIRCLE_CAP: int = 6
    DASHBOARD_ACTIVE_PROJECTS_CAP: int = 8
    DASHBOARD_DORMANCY_DAYS: int = 14
    DASHBOARD_PROJECT_RECENT_DAYS: int = 28
    NARRATIVE_REFLECTION_LOOKBACK_DAYS: int = 28

    FRONTEND_URL: str = "http://localhost:3000"

    model_config = {"env_file": str(PROJECT_ROOT.parent / ".env"), "extra": "ignore"}


settings = Settings()
