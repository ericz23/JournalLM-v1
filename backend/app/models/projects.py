import datetime
import enum

from sqlalchemy import Date, Enum, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ProjectStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_status_last_seen_date", "status", "last_seen_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    aliases_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus),
        default=ProjectStatus.ACTIVE,
        server_default=ProjectStatus.ACTIVE.value,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    first_seen_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    last_seen_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    mention_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    events: Mapped[list["ProjectEvent"]] = relationship(  # noqa: F821
        back_populates="project",
        cascade="all, delete-orphan",
    )
