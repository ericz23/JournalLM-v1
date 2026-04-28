"""Journal embedding pipeline using Gemini embeddings + sqlite-vec.

Chunks journal entries, generates embeddings via gemini-embedding-001
(3072-d), persists them in a vec0 virtual table, and provides KNN
search for thematic retrieval.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import struct
from dataclasses import dataclass

from google import genai
from google.genai import types
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.journal_embedding import JournalEmbedding
from app.models.journal_entry import JournalEntry

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "gemini-embedding-001"
CHUNK_TARGET = 500  # target tokens per chunk (approximated as ~4 chars/token)
CHUNK_OVERLAP = 80  # overlap in tokens between consecutive chunks
CHARS_PER_TOKEN = 4


def _build_client() -> genai.Client:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _serialize_float32(vec: list[float]) -> bytes:
    """Convert a list of floats to the compact binary format sqlite-vec expects."""
    return struct.pack(f"{len(vec)}f", *vec)


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks of ~CHUNK_TARGET tokens."""
    target_chars = CHUNK_TARGET * CHARS_PER_TOKEN
    overlap_chars = CHUNK_OVERLAP * CHARS_PER_TOKEN

    text = text.strip()
    if not text:
        return []

    if len(text) <= target_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + target_chars

        if end < len(text):
            break_at = text.rfind("\n", start, end)
            if break_at == -1 or break_at <= start:
                break_at = text.rfind(". ", start, end)
            if break_at > start:
                end = break_at + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break
        start = end - overlap_chars

    return chunks


async def _embed_texts(client: genai.Client, texts: list[str]) -> list[list[float]]:
    """Call Gemini embedding API for a batch of texts."""
    result = await client.aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
        ),
    )
    return [e.values for e in result.embeddings]


async def _embed_query(client: genai.Client, query: str) -> list[float]:
    result = await client.aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=[query],
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
        ),
    )
    return result.embeddings[0].values


@dataclass
class EmbedResult:
    entries_processed: int = 0
    chunks_created: int = 0
    skipped: int = 0


async def purge_entry_embeddings(db: AsyncSession, entry_date: datetime.date) -> int:
    """Delete journal_embeddings rows + matching vec_journal_chunks rowids for entry_date.

    Returns the number of chunk rows removed. Caller is responsible for committing.
    """
    ids = (await db.execute(
        select(JournalEmbedding.id).where(JournalEmbedding.entry_date == entry_date)
    )).scalars().all()

    if not ids:
        return 0

    placeholders = ",".join(str(int(i)) for i in ids)
    await db.execute(
        text(f"DELETE FROM vec_journal_chunks WHERE rowid IN ({placeholders})")
    )
    await db.execute(
        delete(JournalEmbedding).where(JournalEmbedding.entry_date == entry_date)
    )

    return len(ids)


async def embed_journals(db: AsyncSession) -> EmbedResult:
    """Generate embeddings for all journal entries that lack them."""
    client = _build_client()
    result = EmbedResult()

    existing_dates = set(
        (await db.execute(
            select(JournalEmbedding.entry_date).distinct()
        )).scalars().all()
    )

    entries = (await db.execute(
        select(JournalEntry)
        .where(JournalEntry.processed_at.is_not(None))
        .order_by(JournalEntry.entry_date)
    )).scalars().all()

    for entry in entries:
        if entry.entry_date in existing_dates:
            result.skipped += 1
            continue

        chunks = chunk_text(entry.raw_content)
        if not chunks:
            continue

        try:
            embeddings = await _embed_texts(client, chunks)
        except Exception as exc:
            logger.error("Embedding failed for %s: %s", entry.entry_date, exc)
            continue

        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            embedding_row = JournalEmbedding(
                entry_date=entry.entry_date,
                chunk_index=i,
                chunk_text=chunk,
            )
            db.add(embedding_row)
            await db.flush()

            await db.execute(
                text("INSERT INTO vec_journal_chunks(rowid, embedding) VALUES (:rowid, :embedding)"),
                {"rowid": embedding_row.id, "embedding": _serialize_float32(emb)},
            )

        result.entries_processed += 1
        result.chunks_created += len(chunks)

        await asyncio.sleep(0.2)

    await db.commit()
    return result


@dataclass
class SemanticHit:
    entry_date: str
    chunk_text: str
    score: float


async def semantic_search(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
) -> list[SemanticHit]:
    """Embed the query and find the top-k most similar journal chunks via sqlite-vec KNN."""
    client = _build_client()

    query_vec = await _embed_query(client, query)
    query_blob = _serialize_float32(query_vec)

    knn_rows = (await db.execute(
        text("""
            SELECT rowid, distance
            FROM vec_journal_chunks
            WHERE embedding MATCH :query AND k = :k
            ORDER BY distance
        """),
        {"query": query_blob, "k": top_k},
    )).fetchall()

    if not knn_rows:
        return []

    matched_ids = [row[0] for row in knn_rows]
    distances = {row[0]: row[1] for row in knn_rows}

    meta_rows = (await db.execute(
        select(JournalEmbedding).where(JournalEmbedding.id.in_(matched_ids))
    )).scalars().all()

    meta_by_id = {m.id: m for m in meta_rows}

    results: list[SemanticHit] = []
    for row_id in matched_ids:
        meta = meta_by_id.get(row_id)
        if not meta:
            continue
        results.append(SemanticHit(
            entry_date=meta.entry_date.isoformat(),
            chunk_text=meta.chunk_text,
            score=round(1.0 - distances[row_id], 4),
        ))

    return results
