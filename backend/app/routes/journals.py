from __future__ import annotations

import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.journal_entry import JournalEntry
from app.services.ingestion import ingest_journals

router = APIRouter(prefix="/journals", tags=["journals"])


# ── Schemas ──────────────────────────────────────────────────────────

class IngestionResponse(BaseModel):
    inserted: int
    updated: int
    skipped: int
    total_scanned: int
    errors: list[str]


class JournalSummary(BaseModel):
    id: int
    entry_date: datetime.date
    file_hash: str
    processed_at: datetime.datetime | None
    snippet: str

    model_config = {"from_attributes": True}


class JournalDetail(BaseModel):
    id: int
    entry_date: datetime.date
    raw_content: str
    file_hash: str
    processed_at: datetime.datetime | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class JournalStats(BaseModel):
    total_entries: int
    date_range_start: datetime.date | None
    date_range_end: datetime.date | None
    processed_count: int
    unprocessed_count: int


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/ingest", response_model=IngestionResponse)
async def run_ingestion(db: AsyncSession = Depends(get_db)):
    journal_dir = Path(settings.JOURNAL_SOURCE_DIR)
    result = await ingest_journals(db, journal_dir)
    return IngestionResponse(
        inserted=result.inserted,
        updated=result.updated,
        skipped=result.skipped,
        total_scanned=result.total_scanned,
        errors=result.errors or [],
    )


@router.get("", response_model=list[JournalSummary])
async def list_journals(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(JournalEntry)
        .order_by(JournalEntry.entry_date.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(q)).scalars().all()
    return [
        JournalSummary(
            id=r.id,
            entry_date=r.entry_date,
            file_hash=r.file_hash,
            processed_at=r.processed_at,
            snippet=r.raw_content[:200],
        )
        for r in rows
    ]


@router.get("/stats", response_model=JournalStats)
async def journal_stats(db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count(JournalEntry.id)))).scalar() or 0
    date_min = (await db.execute(select(func.min(JournalEntry.entry_date)))).scalar()
    date_max = (await db.execute(select(func.max(JournalEntry.entry_date)))).scalar()
    processed = (
        await db.execute(
            select(func.count(JournalEntry.id)).where(
                JournalEntry.processed_at.is_not(None)
            )
        )
    ).scalar() or 0

    return JournalStats(
        total_entries=total,
        date_range_start=date_min,
        date_range_end=date_max,
        processed_count=processed,
        unprocessed_count=total - processed,
    )


@router.get("/{entry_date}", response_model=JournalDetail)
async def get_journal(entry_date: datetime.date, db: AsyncSession = Depends(get_db)):
    q = select(JournalEntry).where(JournalEntry.entry_date == entry_date)
    row = (await db.execute(q)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No entry for {entry_date}")
    return row
