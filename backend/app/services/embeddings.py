"""Journal embedding pipeline using Gemini text-embedding-004.

Chunks journal entries, generates 768-d embeddings, persists them,
and provides cosine-similarity search for thematic retrieval.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

import numpy as np
from google import genai
from google.genai import types
from sqlalchemy import delete, select
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
            db.add(JournalEmbedding(
                entry_date=entry.entry_date,
                chunk_index=i,
                chunk_text=chunk,
                embedding_json=json.dumps(emb),
            ))

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
    """Embed the query and find the top-k most similar journal chunks."""
    client = _build_client()

    all_embeddings = (await db.execute(
        select(JournalEmbedding)
    )).scalars().all()

    if not all_embeddings:
        return []

    query_vec = np.array(await _embed_query(client, query), dtype=np.float32)

    scores: list[tuple[float, JournalEmbedding]] = []
    for emb_row in all_embeddings:
        doc_vec = np.array(json.loads(emb_row.embedding_json), dtype=np.float32)
        cos_sim = float(np.dot(query_vec, doc_vec) / (
            np.linalg.norm(query_vec) * np.linalg.norm(doc_vec) + 1e-9
        ))
        scores.append((cos_sim, emb_row))

    scores.sort(key=lambda x: x[0], reverse=True)

    return [
        SemanticHit(
            entry_date=row.entry_date.isoformat(),
            chunk_text=row.chunk_text,
            score=round(sim, 4),
        )
        for sim, row in scores[:top_k]
    ]
