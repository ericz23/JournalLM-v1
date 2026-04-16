import datetime

from sqlalchemy import Date, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class JournalEmbedding(Base):
    __tablename__ = "journal_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[datetime.date] = mapped_column(
        Date, ForeignKey("journal_entries.entry_date"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text)
