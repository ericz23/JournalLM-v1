import datetime
import enum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ProposalEntityType(str, enum.Enum):
    PERSON = "person"
    PROJECT = "project"


class ProposalStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED_NEW = "accepted_new"
    MERGED_EXISTING = "merged_existing"
    DISMISSED = "dismissed"
    REJECTED = "rejected"
    BLOCKED = "blocked"


class EntityProposal(TimestampMixin, Base):
    __tablename__ = "entity_proposals"
    __table_args__ = (
        Index("ix_entity_proposals_status_entity_type_created_at", "status", "entity_type", "created_at"),
        Index("ix_entity_proposals_surface_name_entity_type", "surface_name", "entity_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[ProposalEntityType] = mapped_column(Enum(ProposalEntityType))
    status: Mapped[ProposalStatus] = mapped_column(
        Enum(ProposalStatus),
        default=ProposalStatus.PENDING,
        server_default=ProposalStatus.PENDING.value,
    )
    surface_name: Mapped[str] = mapped_column(String(200))
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
    payload_json: Mapped[str] = mapped_column(Text)
    candidate_matches_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
