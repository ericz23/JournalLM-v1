"""The Shredder — Agentic Event Extraction via Gemini.

Sends unprocessed journal entries to Gemini and writes structured
life_events + journal_reflections to the database.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from dataclasses import dataclass, field

from google import genai
from google.genai import types
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.journal_entry import JournalEntry
from app.models.journal_reflection import JournalReflection
from app.models.life_event import EventCategory, LifeEvent, SentimentLabel

logger = logging.getLogger(__name__)

# ── Pydantic schemas for Gemini's structured output ─────────────────


class EventMetadata(BaseModel):
    participants: list[str] | None = None
    location: str | None = None
    restaurant: str | None = None
    dishes: list[str] | None = None
    meal_type: str | None = None
    activity: str | None = None
    distance: str | None = None
    duration: str | None = None
    project: str | None = None
    subject: str | None = None
    milestone: str | None = None
    metric_name: str | None = None
    metric_value: str | None = None
    notes: str | None = None


class ExtractedEvent(BaseModel):
    category: str
    description: str
    metadata: EventMetadata
    sentiment_score: float
    source_snippet: str


class ExtractedReflection(BaseModel):
    topic: str
    content: str
    is_actionable: bool


class ExtractionResponse(BaseModel):
    life_events: list[ExtractedEvent]
    reflections: list[ExtractedReflection]


# ── System prompt ────────────────────────────────────────────────────

SYSTEM_INSTRUCTION = """\
You are a structured data extraction agent for a personal journal intelligence system called JournalLM.

Your task: read a single daily journal entry and extract two types of structured data.

━━━ 1. LIFE EVENTS ━━━

Each life event is ONE discrete, atomic occurrence — not a summary of the day.

Categories (use EXACTLY these uppercase strings):
• SOCIAL    — Interactions with specific people (meals together, meetings, conversations).
• DIETARY   — Any meal, restaurant visit, or notable food/drink. Always include the restaurant name or food item.
• FITNESS   — Exercise, runs, workouts, physical activity. Include distance/duration when mentioned.
• WORK      — Professional tasks, projects, client work, permits, site visits.
• LEARNING  — Study sessions, language practice, reading non-fiction, skill development.
• HEALTH    — Wearable metrics (Whoop recovery, HRV, strain), illness, medical visits, wellness practices.
• TRAVEL    — Day trips, commutes to new places, travel planning.
• PERSONAL  — Anything that doesn't fit the above (errands, hobbies, household tasks, gratitude-worthy moments).

Metadata fields — populate the ones relevant to the category:
• SOCIAL:   participants, location, notes
• DIETARY:  restaurant, dishes, meal_type (breakfast/lunch/dinner/snack), location
• FITNESS:  activity, distance, duration, metric_name, metric_value, notes
• WORK:     project, notes
• LEARNING: subject, milestone, notes
• HEALTH:   metric_name, metric_value, notes
• TRAVEL:   location, notes
• PERSONAL: notes

Sentiment scoring (-1.0 to 1.0):
  -1.0 = deeply negative  |  -0.5 = frustrated/disappointed  |  0.0 = neutral factual mention
   0.5 = positive/enjoyable  |  0.8 = very positive  |  1.0 = euphoric/peak experience

Rules:
• A single bullet point may produce MULTIPLE events. "Lunch at Lula Cafe with Sam" → one DIETARY event AND one SOCIAL event.
• source_snippet must be a VERBATIM quote (or close paraphrase) from the journal text that supports this event. Keep it under 120 characters.
• Do NOT hallucinate. Only extract what is explicitly stated or clearly implied in the text.
• Side-project progress items are WORK or LEARNING events depending on context.
• Gratitude items: extract as PERSONAL events with positive sentiment, but only if they reference a concrete occurrence (e.g., "Lula Cafe's seasonal soup" → DIETARY event if not already captured; "The post-rain crispness of the air" → skip, too abstract).

━━━ 2. REFLECTIONS ━━━

Reflections are qualitative insights, mental shifts, or personal takeaways.

Rules:
• Extract from "Personal Learnings & Notes" sections and any introspective passages.
• topic: a 2–5 word theme label (e.g., "Work Environment", "Training Discipline", "Design Philosophy").
• content: the actual insight in 1–3 sentences. Preserve the author's voice.
• is_actionable: set to true ONLY when the author explicitly states an intention to change behavior. Look for phrases like "I need to", "I should", "I want to", "I'm going to", "next time I will".
• Do NOT convert individual gratitude bullet points into reflections.
• Do NOT create reflections that merely summarize events — only extract genuine insights or mental shifts.

━━━ OUTPUT ━━━

Return a JSON object with two arrays: "life_events" and "reflections".
"""


# ── Gemini client & extraction ───────────────────────────────────────


def _build_client() -> genai.Client:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=settings.GEMINI_API_KEY)


_MAX_RETRIES = 3
_RETRY_BACKOFF = [2.0, 5.0, 10.0]


async def _call_gemini(
    client: genai.Client,
    entry_date: datetime.date,
    raw_content: str,
) -> ExtractionResponse:
    user_prompt = f"Journal date: {entry_date.isoformat()}\n\n{raw_content}"

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = await client.aio.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=ExtractionResponse,
                    temperature=0.2,
                ),
            )

            if response.parsed is not None:
                return response.parsed

            return ExtractionResponse.model_validate_json(response.text)

        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BACKOFF[attempt]
                logger.warning(
                    "Gemini attempt %d failed for %s (%s), retrying in %.0fs",
                    attempt + 1, entry_date, exc, wait,
                )
                await asyncio.sleep(wait)

    raise last_exc  # type: ignore[misc]


_VALID_CATEGORIES = {c.value for c in EventCategory}


def _coerce_category(raw: str) -> EventCategory:
    upper = raw.strip().upper()
    if upper in _VALID_CATEGORIES:
        return EventCategory(upper)
    logger.warning("Unknown category '%s' from Gemini, falling back to PERSONAL", raw)
    return EventCategory.PERSONAL


def _score_to_label(score: float | None) -> SentimentLabel | None:
    if score is None:
        return None
    if score > 0.3:
        return SentimentLabel.POSITIVE
    if score < -0.3:
        return SentimentLabel.NEGATIVE
    return SentimentLabel.NEUTRAL


# ── Per-entry processing ─────────────────────────────────────────────


@dataclass
class EntryResult:
    entry_date: str
    events_extracted: int = 0
    reflections_extracted: int = 0
    error: str | None = None


@dataclass
class ShredderResult:
    processed: int = 0
    failed: int = 0
    skipped: int = 0
    entries: list[EntryResult] = field(default_factory=list)


async def _process_single_entry(
    db: AsyncSession,
    entry: JournalEntry,
    client: genai.Client,
) -> EntryResult:
    entry_date = entry.entry_date
    raw_content = entry.raw_content
    result = EntryResult(entry_date=entry_date.isoformat())

    try:
        await db.execute(
            delete(LifeEvent).where(LifeEvent.entry_date == entry_date)
        )
        await db.execute(
            delete(JournalReflection).where(
                JournalReflection.entry_date == entry_date
            )
        )

        extraction = await _call_gemini(client, entry_date, raw_content)

        for ev in extraction.life_events:
            db.add(
                LifeEvent(
                    entry_date=entry_date,
                    category=_coerce_category(ev.category),
                    description=ev.description,
                    metadata_json=ev.metadata.model_dump_json(exclude_none=True),
                    sentiment=_score_to_label(max(-1.0, min(1.0, ev.sentiment_score))),
                    source_snippet=ev.source_snippet[:500] if ev.source_snippet else None,
                )
            )
        result.events_extracted = len(extraction.life_events)

        for ref in extraction.reflections:
            db.add(
                JournalReflection(
                    entry_date=entry_date,
                    topic=ref.topic[:200],
                    content=ref.content,
                    is_actionable=ref.is_actionable,
                )
            )
        result.reflections_extracted = len(extraction.reflections)

        entry.processed_at = datetime.datetime.now(datetime.timezone.utc)
        entry.shredder_version = "v2.0"
        await db.commit()

    except Exception as exc:
        await db.rollback()
        result.error = str(exc)
        logger.exception("Shredder failed for %s", entry_date)

    return result


# ── Public API ───────────────────────────────────────────────────────


async def run_shredder(
    db: AsyncSession,
    *,
    target_date: datetime.date | None = None,
) -> ShredderResult:
    client = _build_client()
    overall = ShredderResult()

    if target_date is not None:
        q = select(JournalEntry).where(JournalEntry.entry_date == target_date)
    else:
        q = select(JournalEntry).where(JournalEntry.processed_at.is_(None))

    entries = (await db.execute(q.order_by(JournalEntry.entry_date))).scalars().all()

    if not entries:
        return overall

    for i, entry in enumerate(entries):
        if target_date is None and entry.processed_at is not None:
            overall.skipped += 1
            continue

        entry_result = await _process_single_entry(db, entry, client)
        overall.entries.append(entry_result)

        if entry_result.error:
            overall.failed += 1
        else:
            overall.processed += 1

        if i < len(entries) - 1:
            await asyncio.sleep(1.0)

    return overall


async def get_extraction_results(
    db: AsyncSession,
    entry_date: datetime.date,
) -> dict:
    events_q = select(LifeEvent).where(LifeEvent.entry_date == entry_date)
    events = (await db.execute(events_q)).scalars().all()

    reflections_q = select(JournalReflection).where(
        JournalReflection.entry_date == entry_date
    )
    reflections = (await db.execute(reflections_q)).scalars().all()

    return {
        "entry_date": entry_date.isoformat(),
        "life_events": [
            {
                "id": e.id,
                "category": e.category.value,
                "description": e.description,
                "metadata": json.loads(e.metadata_json) if e.metadata_json else {},
                "sentiment": e.sentiment.value if e.sentiment else None,
                "source_snippet": e.source_snippet,
            }
            for e in events
        ],
        "reflections": [
            {
                "id": r.id,
                "topic": r.topic,
                "content": r.content,
                "is_actionable": r.is_actionable,
            }
            for r in reflections
        ],
    }
