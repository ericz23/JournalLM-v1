import datetime
import enum

from sqlalchemy import Date, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class EventCategory(str, enum.Enum):
    SOCIAL = "SOCIAL"
    LEARNING = "LEARNING"
    DIETARY = "DIETARY"
    FITNESS = "FITNESS"
    WORK = "WORK"
    HEALTH = "HEALTH"
    TRAVEL = "TRAVEL"
    PERSONAL = "PERSONAL"


class LifeEvent(TimestampMixin, Base):
    """Atomic Event layer — discrete, categorized occurrences
    extracted from journal prose by the Shredder.

    Linked to `journal_entries` via `entry_date` FK so that events,
    reflections, and health metrics all share the same date axis.
    """

    __tablename__ = "life_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[datetime.date] = mapped_column(
        Date, ForeignKey("journal_entries.entry_date"), index=True
    )
    category: Mapped[EventCategory] = mapped_column(Enum(EventCategory))
    description: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Range: -1.0 (negative) to 1.0 (positive)"
    )
    source_snippet: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="Original prose fragment for provenance"
    )

    journal_entry: Mapped["JournalEntry"] = relationship(  # noqa: F821
        back_populates="life_events"
    )
