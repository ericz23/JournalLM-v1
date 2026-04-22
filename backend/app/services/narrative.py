"""Weekly narrative generation with DB caching.

Generates a 2-3 sentence AI summary of a week's events and reflections,
stores the result in narrative_cache, and returns it on subsequent calls
without hitting the LLM again.
"""

from __future__ import annotations

import datetime
import json
import logging

from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.journal_reflection import JournalReflection
from app.models.life_event import LifeEvent
from app.models.narrative_cache import NarrativeCache

logger = logging.getLogger(__name__)

NARRATIVE_PROMPT = """\
You are the editorial voice of JournalLM, a personal intelligence dashboard.

Given the structured events and reflections from a person's week, write a \
2-3 sentence "Narrative Snapshot" that captures the week's trajectory. \
The tone should be warm but precise — like a personal briefing.

Focus on:
- The dominant themes (work momentum, social energy, fitness progress, etc.)
- Any notable highs or lows (sentiment extremes, breakthroughs, frustrations)
- A forward-looking thread if the reflections suggest one

Do NOT list every event. Synthesize. Write in second person ("You...").
Keep it under 80 words. No bullet points — flowing prose only.

━━━ WEEK DATA ━━━

{event_summary}

━━━ REFLECTIONS ━━━

{reflections_summary}
"""


def _build_client() -> genai.Client:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _week_bounds(reference: datetime.date) -> tuple[datetime.date, datetime.date]:
    """Return (Monday, Sunday) of the week containing `reference`."""
    monday = reference - datetime.timedelta(days=reference.weekday())
    sunday = monday + datetime.timedelta(days=6)
    return monday, sunday


async def _gather_week_data(
    db: AsyncSession,
    start: datetime.date,
    end: datetime.date,
) -> tuple[str, str]:
    events = (await db.execute(
        select(LifeEvent)
        .where(LifeEvent.entry_date >= start, LifeEvent.entry_date <= end)
        .order_by(LifeEvent.entry_date)
    )).scalars().all()

    reflections = (await db.execute(
        select(JournalReflection)
        .where(JournalReflection.entry_date >= start, JournalReflection.entry_date <= end)
        .order_by(JournalReflection.entry_date)
    )).scalars().all()

    event_lines: list[str] = []
    for e in events:
        meta = json.loads(e.metadata_json) if e.metadata_json else {}
        event_lines.append(
            f"[{e.entry_date}] {e.category.value}: {e.description} "
            f"(sentiment: {e.sentiment.value if e.sentiment else 'UNKNOWN'})"
        )

    ref_lines: list[str] = []
    for r in reflections:
        flag = " [ACTIONABLE]" if r.is_actionable else ""
        ref_lines.append(f"[{r.entry_date}] {r.topic}: {r.content}{flag}")

    return "\n".join(event_lines) or "No events.", "\n".join(ref_lines) or "No reflections."


async def get_or_generate_narrative(
    db: AsyncSession,
    reference_date: datetime.date | None = None,
) -> dict:
    """Return cached narrative or generate a fresh one."""
    if reference_date is None:
        reference_date = datetime.date.today()

    week_start, week_end = _week_bounds(reference_date)

    cached = (await db.execute(
        select(NarrativeCache).where(NarrativeCache.week_start == week_start)
    )).scalar_one_or_none()

    if cached is not None:
        return {
            "content": cached.content,
            "week_start": cached.week_start.isoformat(),
            "week_end": cached.week_end.isoformat(),
            "generated_at": cached.created_at.isoformat() if cached.created_at else None,
            "cached": True,
        }

    event_summary, reflections_summary = await _gather_week_data(db, week_start, week_end)

    if event_summary == "No events.":
        return {
            "content": "No journal data available for this week yet.",
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "generated_at": None,
            "cached": False,
        }

    prompt = NARRATIVE_PROMPT.format(
        event_summary=event_summary,
        reflections_summary=reflections_summary,
    )

    client = _build_client()
    response = await client.aio.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.5),
    )

    narrative_text = response.text.strip()

    entry = NarrativeCache(
        week_start=week_start,
        week_end=week_end,
        content=narrative_text,
        model_used=settings.GEMINI_MODEL,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    return {
        "content": narrative_text,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "generated_at": entry.created_at.isoformat() if entry.created_at else None,
        "cached": False,
    }
