from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.journal_entry import JournalEntry
from app.models.journal_reflection import JournalReflection
from app.models.life_event import LifeEvent
from app.services.shredder import get_extraction_results, run_shredder

router = APIRouter(prefix="/shredder", tags=["shredder"])


# ── Schemas ──────────────────────────────────────────────────────────


class EntryResultSchema(BaseModel):
    entry_date: str
    events_extracted: int
    reflections_extracted: int
    error: str | None


class ShredderRunResponse(BaseModel):
    processed: int
    failed: int
    skipped: int
    entries: list[EntryResultSchema]


class ShredderStatusResponse(BaseModel):
    total_entries: int
    processed: int
    unprocessed: int
    total_life_events: int
    total_reflections: int


class EventSchema(BaseModel):
    id: int
    category: str
    description: str
    metadata: dict
    sentiment: str | None
    source_snippet: str | None


class ReflectionSchema(BaseModel):
    id: int
    topic: str
    content: str
    is_actionable: bool


class ExtractionResultResponse(BaseModel):
    entry_date: str
    life_events: list[EventSchema]
    reflections: list[ReflectionSchema]


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("/run", response_model=ShredderRunResponse)
async def shredder_run_all(db: AsyncSession = Depends(get_db)):
    result = await run_shredder(db)
    return ShredderRunResponse(
        processed=result.processed,
        failed=result.failed,
        skipped=result.skipped,
        entries=[
            EntryResultSchema(
                entry_date=e.entry_date,
                events_extracted=e.events_extracted,
                reflections_extracted=e.reflections_extracted,
                error=e.error,
            )
            for e in result.entries
        ],
    )


@router.post("/run/{entry_date}", response_model=ShredderRunResponse)
async def shredder_run_single(
    entry_date: datetime.date,
    db: AsyncSession = Depends(get_db),
):
    entry = (
        await db.execute(
            select(JournalEntry).where(JournalEntry.entry_date == entry_date)
        )
    ).scalar_one_or_none()

    if entry is None:
        raise HTTPException(404, f"No journal entry for {entry_date}")

    result = await run_shredder(db, target_date=entry_date)
    return ShredderRunResponse(
        processed=result.processed,
        failed=result.failed,
        skipped=result.skipped,
        entries=[
            EntryResultSchema(
                entry_date=e.entry_date,
                events_extracted=e.events_extracted,
                reflections_extracted=e.reflections_extracted,
                error=e.error,
            )
            for e in result.entries
        ],
    )


@router.get("/status", response_model=ShredderStatusResponse)
async def shredder_status(db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count(JournalEntry.id)))).scalar() or 0
    processed = (
        await db.execute(
            select(func.count(JournalEntry.id)).where(
                JournalEntry.processed_at.is_not(None)
            )
        )
    ).scalar() or 0
    total_events = (
        await db.execute(select(func.count(LifeEvent.id)))
    ).scalar() or 0
    total_reflections = (
        await db.execute(select(func.count(JournalReflection.id)))
    ).scalar() or 0

    return ShredderStatusResponse(
        total_entries=total,
        processed=processed,
        unprocessed=total - processed,
        total_life_events=total_events,
        total_reflections=total_reflections,
    )


@router.get("/results/{entry_date}", response_model=ExtractionResultResponse)
async def shredder_results(
    entry_date: datetime.date,
    db: AsyncSession = Depends(get_db),
):
    entry = (
        await db.execute(
            select(JournalEntry).where(JournalEntry.entry_date == entry_date)
        )
    ).scalar_one_or_none()

    if entry is None:
        raise HTTPException(404, f"No journal entry for {entry_date}")

    data = await get_extraction_results(db, entry_date)
    return data
