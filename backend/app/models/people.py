import datetime

from sqlalchemy import Date, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Person(TimestampMixin, Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    aliases_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    relationship_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    last_seen_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    mention_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    mentions: Mapped[list["PersonMention"]] = relationship(  # noqa: F821
        back_populates="person",
        cascade="all, delete-orphan",
    )
