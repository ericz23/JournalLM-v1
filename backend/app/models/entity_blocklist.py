import enum

from sqlalchemy import Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.entity_proposal import ProposalEntityType


class BlocklistReason(str, enum.Enum):
    MANUAL_BLOCK = "manual_block"
    SYSTEM_NOISE = "system_noise"


class EntityBlocklist(TimestampMixin, Base):
    __tablename__ = "entity_blocklist"
    __table_args__ = (
        UniqueConstraint("entity_type", "surface_name", name="uq_entity_blocklist_type_surface"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[ProposalEntityType] = mapped_column(Enum(ProposalEntityType))
    surface_name: Mapped[str] = mapped_column(String(200))
    reason: Mapped[BlocklistReason | None] = mapped_column(
        Enum(BlocklistReason),
        nullable=True,
    )
