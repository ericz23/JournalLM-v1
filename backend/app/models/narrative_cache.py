import datetime

from sqlalchemy import Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class NarrativeCache(TimestampMixin, Base):
    """Stores cached AI-generated weekly narrative summaries.

    Keyed by week_start (Monday) so each week has at most one cached narrative.
    Regenerated when new data is ingested for that week.
    """

    __tablename__ = "narrative_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    week_start: Mapped[datetime.date] = mapped_column(Date, unique=True, index=True)
    week_end: Mapped[datetime.date] = mapped_column(Date)
    content: Mapped[str] = mapped_column(Text)
    model_used: Mapped[str] = mapped_column(String(100))
