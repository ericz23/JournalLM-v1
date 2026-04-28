import datetime

from sqlalchemy import Date, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class NarrativeCache(TimestampMixin, Base):
    """Stores cached AI-generated weekly narrative summaries.

    V2 (Step 7) keys on `window_end` (rolling 7-day window) so the dashboard
    payload and the narrative talk about the same window. The legacy
    `week_start` / `week_end` columns are kept nullable to preserve V1 rows
    that were keyed Monday–Sunday; new code always populates `window_end`
    plus mirrors `week_start` / `week_end` for backwards compatibility.

    `stale_at` is set by Step 7 invalidation hooks (post-shred, post-inbox
    action) and cleared on regeneration.
    """

    __tablename__ = "narrative_cache"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Legacy V1 columns — remain populated to keep the existing unique
    # constraint on `week_start` valid. New rows write
    # `week_start = window_end - 6` and `week_end = window_end`.
    week_start: Mapped[datetime.date] = mapped_column(Date, unique=True, index=True)
    week_end: Mapped[datetime.date] = mapped_column(Date)

    # V2 rolling-window key. Nullable for legacy rows; new code always sets it.
    window_end: Mapped[datetime.date | None] = mapped_column(
        Date, unique=True, index=True, nullable=True
    )
    stale_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    content: Mapped[str] = mapped_column(Text)
    model_used: Mapped[str] = mapped_column(String(100))
