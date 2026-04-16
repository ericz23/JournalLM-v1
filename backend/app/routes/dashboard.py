"""Dashboard API — aggregated endpoints for the Slate Intelligence dashboard."""

from __future__ import annotations

import datetime
import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.journal_entry import JournalEntry
from app.models.journal_reflection import JournalReflection
from app.models.life_event import EventCategory, LifeEvent
from app.services.narrative import get_or_generate_narrative

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _resolve_week(ref: datetime.date) -> tuple[datetime.date, datetime.date]:
    """Return (start, end) for the rolling 7-day window ending on `ref`."""
    return ref - datetime.timedelta(days=6), ref


async def _get_latest_date(db: AsyncSession) -> datetime.date | None:
    return (await db.execute(
        select(func.max(JournalEntry.entry_date))
    )).scalar()


@router.get("/data")
async def dashboard_data(
    db: AsyncSession = Depends(get_db),
    ref_date: datetime.date | None = Query(None, description="Reference date (defaults to latest entry)"),
):
    """Single endpoint returning all dashboard widget data."""
    latest = await _get_latest_date(db)
    if latest is None:
        return {
            "has_data": False,
            "date_range": None,
            "dining": [],
            "reflections": [],
            "learning": [],
        }

    ref = ref_date or latest
    start, end = _resolve_week(ref)

    events = (await db.execute(
        select(LifeEvent)
        .where(LifeEvent.entry_date >= start, LifeEvent.entry_date <= end)
        .order_by(LifeEvent.entry_date.desc(), LifeEvent.id)
    )).scalars().all()

    reflections = (await db.execute(
        select(JournalReflection)
        .where(JournalReflection.entry_date >= start, JournalReflection.entry_date <= end)
        .order_by(JournalReflection.entry_date.desc())
    )).scalars().all()

    dining: list[dict] = []
    learning: list[dict] = []

    for e in events:
        meta = json.loads(e.metadata_json) if e.metadata_json else {}

        if e.category == EventCategory.DIETARY:
            restaurant = meta.get("restaurant")
            if restaurant:
                dining.append({
                    "date": e.entry_date.isoformat(),
                    "restaurant": restaurant,
                    "dishes": meta.get("dishes", []),
                    "meal_type": meta.get("meal_type", ""),
                    "sentiment": e.sentiment_score,
                    "description": e.description,
                })

        elif e.category == EventCategory.LEARNING:
            learning.append({
                "date": e.entry_date.isoformat(),
                "subject": meta.get("subject", ""),
                "milestone": meta.get("milestone", ""),
                "description": e.description,
                "sentiment": e.sentiment_score,
            })

    reflection_list: list[dict] = []
    for r in reflections:
        reflection_list.append({
            "date": r.entry_date.isoformat(),
            "topic": r.topic,
            "content": r.content,
            "is_actionable": r.is_actionable,
        })

    return {
        "has_data": True,
        "date_range": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "dining": dining,
        "reflections": reflection_list,
        "learning": learning,
    }


@router.get("/narrative")
async def narrative(
    db: AsyncSession = Depends(get_db),
    ref_date: datetime.date | None = Query(None),
):
    """Return the cached (or freshly generated) weekly narrative."""
    latest = await _get_latest_date(db)
    ref = ref_date or latest or datetime.date.today()
    return await get_or_generate_narrative(db, reference_date=ref)
