import datetime

from sqlalchemy import Date, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.life_event import SentimentLabel


class PersonMention(TimestampMixin, Base):
    __tablename__ = "person_mentions"
    __table_args__ = (
        Index("ix_person_mentions_person_entry_date", "person_id", "entry_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"),
        index=True,
    )
    entry_date: Mapped[datetime.date] = mapped_column(
        Date,
        ForeignKey("journal_entries.entry_date"),
        index=True,
    )
    life_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("life_events.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    context_snippet: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sentiment: Mapped[SentimentLabel | None] = mapped_column(
        Enum(SentimentLabel),
        nullable=True,
    )

    person: Mapped["Person"] = relationship(back_populates="mentions")  # noqa: F821
