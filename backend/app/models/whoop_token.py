import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class WhoopToken(TimestampMixin, Base):
    """Single-row table persisting the Whoop OAuth 2.0 tokens.

    Local-first, single-user app — only one active credential set.
    The row with id=1 is the canonical token; upsert on that key.
    """

    __tablename__ = "whoop_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str] = mapped_column(String(500))
    whoop_user_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
