from __future__ import annotations

import json
import logging
import struct
from collections.abc import AsyncGenerator

import sqlite_vec
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 3072

_sqlite_url = settings.DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

engine = create_async_engine(_sqlite_url, echo=settings.DEBUG)


@event.listens_for(engine.sync_engine, "connect")
def _load_vec_extension(dbapi_connection, connection_record):
    """Load sqlite-vec into every new SQLite connection."""
    raw_conn = getattr(dbapi_connection, "driver_connection", dbapi_connection)
    if hasattr(raw_conn, "_conn"):
        raw_conn = raw_conn._conn
    raw_conn.enable_load_extension(True)
    sqlite_vec.load(raw_conn)
    raw_conn.enable_load_extension(False)


async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


def _serialize_float32(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


async def _migrate_embeddings_to_vec0(conn) -> None:
    """One-time migration: move JSON vectors from journal_embeddings into vec_journal_chunks."""
    has_json_col = False
    rows = (await conn.execute(text("PRAGMA table_info(journal_embeddings)"))).fetchall()
    for row in rows:
        if row[1] == "embedding_json":
            has_json_col = True
            break

    if not has_json_col:
        return

    vec_count = (await conn.execute(
        text("SELECT count(*) FROM vec_journal_chunks")
    )).scalar()

    if vec_count and vec_count > 0:
        return

    old_rows = (await conn.execute(
        text("SELECT id, embedding_json FROM journal_embeddings WHERE embedding_json IS NOT NULL")
    )).fetchall()

    if not old_rows:
        return

    logger.info("Migrating %d embeddings from JSON to vec_journal_chunks...", len(old_rows))
    for row in old_rows:
        vec = json.loads(row[1])
        await conn.execute(
            text("INSERT INTO vec_journal_chunks(rowid, embedding) VALUES (:rowid, :embedding)"),
            {"rowid": row[0], "embedding": _serialize_float32(vec)},
        )

    await conn.execute(text("""
        CREATE TABLE journal_embeddings_new (
            id INTEGER PRIMARY KEY,
            entry_date DATE NOT NULL REFERENCES journal_entries(entry_date),
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL
        )
    """))
    await conn.execute(text("""
        INSERT INTO journal_embeddings_new (id, entry_date, chunk_index, chunk_text)
        SELECT id, entry_date, chunk_index, chunk_text FROM journal_embeddings
    """))
    await conn.execute(text("DROP TABLE journal_embeddings"))
    await conn.execute(text("ALTER TABLE journal_embeddings_new RENAME TO journal_embeddings"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_journal_embeddings_entry_date ON journal_embeddings(entry_date)"))
    logger.info("Migration complete — embedding_json column removed.")


async def init_db() -> None:
    from app.models import Base  # noqa: F811

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        await conn.execute(text(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_journal_chunks "
            f"USING vec0(embedding float[{EMBEDDING_DIM}] distance_metric=cosine)"
        ))

        vec_version = (await conn.execute(text("SELECT vec_version()"))).scalar()
        logger.info("sqlite-vec loaded successfully (version %s)", vec_version)

        await _migrate_embeddings_to_vec0(conn)
