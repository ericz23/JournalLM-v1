import datetime

from sqlalchemy import Date, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class JournalEntry(TimestampMixin, Base):
    """Source layer — stores the original, unprocessed journal text.

    `entry_date` is the natural key that links journal prose to its
    extracted events, reflections, and same-day health metrics.
    """

    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[datetime.date] = mapped_column(Date, unique=True, index=True)
    raw_content: Mapped[str] = mapped_column(Text)
    file_hash: Mapped[str] = mapped_column(String(64))
    processed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    life_events: Mapped[list["LifeEvent"]] = relationship(  # noqa: F821
        back_populates="journal_entry", cascade="all, delete-orphan"
    )
    reflections: Mapped[list["JournalReflection"]] = relationship(  # noqa: F821
        back_populates="journal_entry", cascade="all, delete-orphan"
    )
