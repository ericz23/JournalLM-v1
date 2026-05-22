"""Journal embedding pipeline using Gemini embeddings + sqlite-vec.

Step 9 refactor:
- `build_canonical_source` builds the text to hash/chunk based on
  EMBEDDING_CHUNK_MODE (journal_only | journal_plus_structured).
- `embed_journals` uses `embed_input_hash` to skip unchanged entries
  instead of checking existing_dates; purges + rebuilds on mismatch.
- `SemanticHit` gains `chunk_index` for richer context metadata.
- `EmbedResult` gains `purged_dates` / `reembedded_dates` lists.
- `mark_embeddings_stale_for_date` NULLs `embed_input_hash` (fast
  invalidation path used by shredder on journal_plus_structured mode).
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import logging
import re
import struct
from dataclasses import dataclass, field

from google import genai
from google.genai import types
from sqlalchemy import and_, delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.journal_embedding import JournalEmbedding
from app.models.journal_entry import JournalEntry
from app.models.journal_reflection import JournalReflection
from app.models.life_event import LifeEvent

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "gemini-embedding-001"
CHUNK_TARGET = 500   # target tokens per chunk (~4 chars/token)
CHUNK_OVERLAP = 80   # overlap in tokens between consecutive chunks
CHARS_PER_TOKEN = 4

# Prefix length used for deduplication in retrieval.py
DEDUP_PREFIX_LEN = 160


# ── Client ──────────────────────────────────────────────────────────


def _build_client() -> genai.Client:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _serialize_float32(vec: list[float]) -> bytes:
    """Convert a list of floats to the compact binary format sqlite-vec expects."""
    return struct.pack(f"{len(vec)}f", *vec)


# ── Text normalization ───────────────────────────────────────────────


def normalize_journal_raw(text_: str) -> str:
    """Strip BOM, normalize newlines to \\n, strip trailing whitespace per line."""
    # Remove BOM
    text_ = text_.lstrip("\ufeff")
    # Normalize Windows/Mac newlines
    text_ = text_.replace("\r\n", "\n").replace("\r", "\n")
    # Strip trailing whitespace from each line
    text_ = "\n".join(line.rstrip() for line in text_.split("\n"))
    return text_.strip()


# ── Canonical source builder ─────────────────────────────────────────


async def build_canonical_source(
    db: AsyncSession,
    entry: JournalEntry,
) -> str:
    """Return the text to hash and chunk for this entry.

    - journal_only mode (default): normalized raw_content.
    - journal_plus_structured mode: append a structured digest of life_events
      and journal_reflections after the raw prose, but only when the entry
      has been shredded (processed_at is not None). If unshredded, or if there
      are no events/reflections, returns the journal-only canonical form so
      the hash stays stable.
    """
    canonical = normalize_journal_raw(entry.raw_content)

    if (
        settings.EMBEDDING_CHUNK_MODE == "journal_plus_structured"
        and entry.processed_at is not None
    ):
        events = (await db.execute(
            select(LifeEvent)
            .where(LifeEvent.entry_date == entry.entry_date)
            .order_by(LifeEvent.id)
        )).scalars().all()

        reflections = (await db.execute(
            select(JournalReflection)
            .where(JournalReflection.entry_date == entry.entry_date)
            .order_by(JournalReflection.id)
        )).scalars().all()

        if events or reflections:
            lines: list[str] = [
                "",
                f"--- JournalLM structured digest ({entry.entry_date}) ---",
            ]

            if events:
                lines.append("Life events:")
                for ev in events:
                    sentiment = ev.sentiment.value if ev.sentiment else "n/a"
                    lines.append(f"- [{ev.category.value}] {ev.description} (sentiment: {sentiment})")

            if reflections:
                lines.append("Reflections:")
                for ref in reflections:
                    # Single-line escape: collapse newlines within content preview
                    preview = re.sub(r"\s+", " ", ref.content[:400]).strip()
                    lines.append(f"- [{ref.topic}] {preview}")

            lines.append("--- End digest ---")
            canonical = canonical + "\n" + "\n".join(lines)

    return canonical


def compute_embed_hash(canonical: str) -> str:
    """SHA-256 hex of UTF-8 encoded canonical source."""
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Chunking ─────────────────────────────────────────────────────────


def chunk_canonical(canonical: str) -> list[str]:
    """Split the canonical source into overlapping chunks."""
    return chunk_text(canonical)


def chunk_text(text_: str) -> list[str]:
    """Split text into overlapping chunks of ~CHUNK_TARGET tokens."""
    target_chars = CHUNK_TARGET * CHARS_PER_TOKEN
    overlap_chars = CHUNK_OVERLAP * CHARS_PER_TOKEN

    text_ = text_.strip()
    if not text_:
        return []

    if len(text_) <= target_chars:
        return [text_]

    chunks: list[str] = []
    start = 0
    while start < len(text_):
        end = start + target_chars

        if end < len(text_):
            break_at = text_.rfind("\n", start, end)
            if break_at == -1 or break_at <= start:
                break_at = text_.rfind(". ", start, end)
            if break_at > start:
                end = break_at + 1

        chunk = text_[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text_):
            break
        start = end - overlap_chars

    return chunks


# ── Embedding API ────────────────────────────────────────────────────


async def _embed_texts(client: genai.Client, texts: list[str]) -> list[list[float]]:
    """Call Gemini embedding API for a batch of texts."""
    result = await client.aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    return [e.values for e in result.embeddings]


async def _embed_query(client: genai.Client, query: str) -> list[float]:
    result = await client.aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=[query],
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    return result.embeddings[0].values


# ── Staleness helper ─────────────────────────────────────────────────


async def mark_embeddings_stale_for_date(
    db: AsyncSession,
    entry_date: datetime.date,
) -> None:
    """NULL the embed_input_hash for entry_date, flagging it for rebuild.

    Fast path — does not delete vec rows. The next embed_journals pass will
    purge stale rows before inserting new ones when hash mismatches. Caller
    owns the commit.
    """
    await db.execute(
        update(JournalEntry)
        .where(JournalEntry.entry_date == entry_date)
        .values(embed_input_hash=None)
        .execution_options(synchronize_session=False)
    )


# ── Purge ────────────────────────────────────────────────────────────


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


# ── Core embed helpers ───────────────────────────────────────────────


async def _embed_entry(
    db: AsyncSession,
    entry: JournalEntry,
    client: genai.Client,
    canonical: str,
    new_hash: str,
) -> int:
    """Purge, embed, persist chunks, set embed_input_hash. Returns chunk count."""
    await purge_entry_embeddings(db, entry.entry_date)

    chunks = chunk_canonical(canonical)
    if not chunks:
        return 0

    embeddings = await _embed_texts(client, chunks)

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

    entry.embed_input_hash = new_hash
    logger.info(
        "embed date=%s chunks=%d hash_old=null hash_new=%s",
        entry.entry_date, len(chunks), new_hash[:8],
    )
    return len(chunks)


async def embed_entry_if_stale(
    db: AsyncSession,
    entry: JournalEntry,
    client: genai.Client,
) -> tuple[bool, int]:
    """If embed_input_hash matches the canonical source, skip.

    Returns (was_reembedded, n_chunks). On mismatch or NULL hash, purges
    old vectors, embeds fresh chunks, sets the new hash.
    """
    canonical = await build_canonical_source(db, entry)
    new_hash = compute_embed_hash(canonical)

    if entry.embed_input_hash == new_hash:
        return False, 0

    n = await _embed_entry(db, entry, client, canonical, new_hash)
    return True, n


# ── Result types ─────────────────────────────────────────────────────


@dataclass
class EmbedResult:
    entries_processed: int = 0
    chunks_created: int = 0
    skipped: int = 0
    purged_dates: list[datetime.date] = field(default_factory=list)
    reembedded_dates: list[datetime.date] = field(default_factory=list)


# ── Public pipeline ──────────────────────────────────────────────────


async def embed_journals(db: AsyncSession) -> EmbedResult:
    """Generate / refresh embeddings for all shredded journal entries.

    Skips entries whose embed_input_hash already matches the current canonical
    source (Q4-safe: re-shred sets hash NULL to force rebuild).
    """
    client = _build_client()
    result = EmbedResult()

    entries = (await db.execute(
        select(JournalEntry)
        .where(JournalEntry.processed_at.is_not(None))
        .order_by(JournalEntry.entry_date)
    )).scalars().all()

    for entry in entries:
        try:
            canonical = await build_canonical_source(db, entry)
            new_hash = compute_embed_hash(canonical)

            if entry.embed_input_hash == new_hash:
                result.skipped += 1
                continue

            # Hash mismatch or NULL — rebuild.
            result.purged_dates.append(entry.entry_date)
            n_chunks = await _embed_entry(db, entry, client, canonical, new_hash)
            result.reembedded_dates.append(entry.entry_date)
            result.entries_processed += 1
            result.chunks_created += n_chunks

            await db.commit()
            await asyncio.sleep(0.2)

        except Exception as exc:
            logger.error("Embedding failed for %s: %s", entry.entry_date, exc)
            await db.rollback()

    chunk_mode = settings.EMBEDDING_CHUNK_MODE
    logger.info(
        "embed summary processed=%d reembedded=%d skipped=%d purged=%d chunk_mode=%s",
        result.entries_processed,
        len(result.reembedded_dates),
        result.skipped,
        len(result.purged_dates),
        chunk_mode,
    )
    return result


async def embed_single_entry(
    db: AsyncSession,
    entry_date: datetime.date,
) -> tuple[bool, int]:
    """Embed a single entry by date (used for EMBEDDING_SYNC_AFTER_SHRED).

    Returns (was_reembedded, n_chunks). No-op if hash is still current.
    """
    entry = (await db.execute(
        select(JournalEntry).where(JournalEntry.entry_date == entry_date)
    )).scalar_one_or_none()

    if entry is None or entry.processed_at is None:
        return False, 0

    client = _build_client()
    reembedded, n = await embed_entry_if_stale(db, entry, client)
    if reembedded:
        await db.commit()
    return reembedded, n


# ── Semantic search ──────────────────────────────────────────────────


@dataclass
class SemanticHit:
    entry_date: str
    chunk_text: str
    score: float
    chunk_index: int = 0


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
            if meta is None:
                logger.warning("Semantic hit rowid=%d has no metadata row — possible orphan vec", row_id)
            continue
        if not meta.chunk_text:
            logger.warning("Semantic hit date=%s chunk_index=%d has empty chunk_text", meta.entry_date, meta.chunk_index)
            continue
        results.append(SemanticHit(
            entry_date=meta.entry_date.isoformat(),
            chunk_text=meta.chunk_text,
            score=round(1.0 - distances[row_id], 4),
            chunk_index=meta.chunk_index,
        ))

    return results
