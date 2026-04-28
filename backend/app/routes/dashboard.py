"""Dashboard API — thin adapter over `services.dashboard` (Step 7)."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.journal_entry import JournalEntry
from app.services.dashboard import build_payload
from app.services.narrative import get_or_generate_narrative

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


async def _get_latest_date(db: AsyncSession) -> datetime.date | None:
    return (await db.execute(
        select(func.max(JournalEntry.entry_date))
    )).scalar()


@router.get("/data")
async def dashboard_data(
    db: AsyncSession = Depends(get_db),
    ref_date: datetime.date | None = Query(
        None, description="Reference date (defaults to latest entry)"
    ),
):
    """Return the curated weekly dashboard payload (Inner Circle, Active
    Projects, Dining, Reflections, Learning) for a rolling 7-day window."""
    payload = await build_payload(db, ref_date=ref_date)
    return payload.model_dump(mode="json")


@router.get("/narrative")
async def narrative(
    db: AsyncSession = Depends(get_db),
    ref_date: datetime.date | None = Query(None),
):
    """Return the cached (or freshly generated) weekly narrative."""
    latest = await _get_latest_date(db)
    ref = ref_date or latest or datetime.date.today()
    return await get_or_generate_narrative(db, reference_date=ref)
