import datetime
import enum

from sqlalchemy import Date, Enum, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ProjectEventType(str, enum.Enum):
    PROGRESS = "progress"
    MILESTONE = "milestone"
    SETBACK = "setback"
    REFLECTION = "reflection"
    START = "start"
    PAUSE = "pause"


class ProjectEvent(TimestampMixin, Base):
    __tablename__ = "project_events"
    __table_args__ = (
        Index("ix_project_events_project_entry_date", "project_id", "entry_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
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
    event_type: Mapped[ProjectEventType] = mapped_column(Enum(ProjectEventType))
    content: Mapped[str] = mapped_column(Text)

    project: Mapped["Project"] = relationship(back_populates="events")  # noqa: F821
