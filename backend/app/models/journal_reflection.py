import datetime

from sqlalchemy import Boolean, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class JournalReflection(TimestampMixin, Base):
    """Narrative layer — qualitative takeaways and mental shifts
    extracted from journal prose.

    Also keyed on `entry_date` to keep the unified date axis.
    """

    __tablename__ = "journal_reflections"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[datetime.date] = mapped_column(
        Date, ForeignKey("journal_entries.entry_date"), index=True
    )
    topic: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    is_actionable: Mapped[bool] = mapped_column(Boolean, default=False)

    journal_entry: Mapped["JournalEntry"] = relationship(  # noqa: F821
        back_populates="reflections"
    )
