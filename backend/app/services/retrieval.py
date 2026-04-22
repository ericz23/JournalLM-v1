"""Two-stage retrieval pipeline: intent classification then parallel retrieval.

Stage 1: Gemini classifies the user query into structured filters.
Stage 2: Structured SQL retrieval + semantic search, merged into a context block.
"""

from __future__ import annotations

import datetime
import json
import logging
from dataclasses import dataclass, field
from enum import Enum

from google import genai
from google.genai import types
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.health_metric import HealthMetric
from app.models.journal_entry import JournalEntry
from app.models.journal_reflection import JournalReflection
from app.models.life_event import EventCategory, LifeEvent
from app.services.embeddings import SemanticHit, semantic_search

logger = logging.getLogger(__name__)

# ── Intent classification ────────────────────────────────────────────


class QueryType(str, Enum):
    FACTUAL = "FACTUAL"
    THEMATIC = "THEMATIC"
    META = "META"


class ParsedIntent(BaseModel):
    query_type: str  # FACTUAL | THEMATIC | META
    date_start: str | None = None  # ISO date
    date_end: str | None = None  # ISO date
    categories: list[str] = []
    keywords: list[str] = []


INTENT_SYSTEM_PROMPT = """\
You are a query parser for a personal journal system. The journal data covers \
dates from {date_min} to {date_max}. Today is {today}.

Given the user's question, extract structured filters as JSON.

Fields:
- query_type: "FACTUAL" for questions about specific events/facts/dates, \
"THEMATIC" for open-ended reflections/patterns/trends, "META" for questions \
about the system itself or greetings.
- date_start / date_end: ISO dates (YYYY-MM-DD) if the query references a \
time period. Convert relative references ("last week", "yesterday", \
"October 3rd") to absolute dates based on today={today} and the available \
data range {date_min} to {date_max}. For "last Tuesday" etc., resolve to the \
most recent such day that falls within the data range. If no specific date is \
mentioned, leave null.
- categories: relevant event categories from [SOCIAL, DIETARY, FITNESS, WORK, \
LEARNING, HEALTH, TRAVEL, PERSONAL]. Only include if the query clearly targets \
specific categories.
- keywords: important entity names (people, restaurants, projects, places) \
mentioned in the query. Extract proper nouns and specific terms.

Return ONLY the JSON object, no other text.
"""


def _build_client() -> genai.Client:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=settings.GEMINI_API_KEY)


async def _get_date_range(db: AsyncSession) -> tuple[str, str]:
    date_min = (await db.execute(select(func.min(JournalEntry.entry_date)))).scalar()
    date_max = (await db.execute(select(func.max(JournalEntry.entry_date)))).scalar()
    return (
        date_min.isoformat() if date_min else "unknown",
        date_max.isoformat() if date_max else "unknown",
    )


async def classify_intent(
    db: AsyncSession, query: str
) -> ParsedIntent:
    client = _build_client()
    date_min, date_max = await _get_date_range(db)
    today = datetime.date.today().isoformat()

    system = INTENT_SYSTEM_PROMPT.format(
        date_min=date_min, date_max=date_max, today=today,
    )

    try:
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=query,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=ParsedIntent,
                temperature=0.0,
            ),
        )
        if response.parsed is not None:
            return response.parsed
        return ParsedIntent.model_validate_json(response.text)
    except Exception as exc:
        logger.warning("Intent classification failed: %s — defaulting to THEMATIC", exc)
        return ParsedIntent(query_type="THEMATIC")


# ── Structured retrieval ─────────────────────────────────────────────


@dataclass
class ContextItem:
    type: str  # "life_event" | "reflection" | "health_metric" | "journal_chunk"
    date: str
    content: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "date": self.date,
            "content": self.content,
            "metadata": self.metadata,
        }


async def _retrieve_life_events(
    db: AsyncSession, intent: ParsedIntent
) -> list[ContextItem]:
    q = select(LifeEvent)

    if intent.date_start:
        try:
            d = datetime.date.fromisoformat(intent.date_start)
            q = q.where(LifeEvent.entry_date >= d)
        except ValueError:
            pass
    if intent.date_end:
        try:
            d = datetime.date.fromisoformat(intent.date_end)
            q = q.where(LifeEvent.entry_date <= d)
        except ValueError:
            pass

    valid_cats = {c.value for c in EventCategory}
    cats = [c.upper() for c in intent.categories if c.upper() in valid_cats]
    if cats:
        q = q.where(LifeEvent.category.in_([EventCategory(c) for c in cats]))

    q = q.order_by(LifeEvent.entry_date, LifeEvent.id).limit(50)
    rows = (await db.execute(q)).scalars().all()

    items: list[ContextItem] = []
    for e in rows:
        meta = json.loads(e.metadata_json) if e.metadata_json else {}
        meta["category"] = e.category.value
        meta["sentiment"] = e.sentiment.value if e.sentiment else None

        if intent.keywords:
            text_blob = (e.description + " " + json.dumps(meta)).lower()
            if not any(kw.lower() in text_blob for kw in intent.keywords):
                continue

        items.append(ContextItem(
            type="life_event",
            date=e.entry_date.isoformat(),
            content=e.description,
            metadata=meta,
        ))

    return items


async def _retrieve_reflections(
    db: AsyncSession, intent: ParsedIntent
) -> list[ContextItem]:
    q = select(JournalReflection)

    if intent.date_start:
        try:
            d = datetime.date.fromisoformat(intent.date_start)
            q = q.where(JournalReflection.entry_date >= d)
        except ValueError:
            pass
    if intent.date_end:
        try:
            d = datetime.date.fromisoformat(intent.date_end)
            q = q.where(JournalReflection.entry_date <= d)
        except ValueError:
            pass

    q = q.order_by(JournalReflection.entry_date).limit(30)
    rows = (await db.execute(q)).scalars().all()

    items: list[ContextItem] = []
    for r in rows:
        if intent.keywords:
            text_blob = (r.topic + " " + r.content).lower()
            if not any(kw.lower() in text_blob for kw in intent.keywords):
                continue

        items.append(ContextItem(
            type="reflection",
            date=r.entry_date.isoformat(),
            content=f"[{r.topic}] {r.content}",
            metadata={"topic": r.topic, "is_actionable": r.is_actionable},
        ))

    return items


async def _retrieve_health_metrics(
    db: AsyncSession, intent: ParsedIntent
) -> list[ContextItem]:
    needs_health = any(
        c.upper() in ("HEALTH", "FITNESS") for c in intent.categories
    ) or any(
        kw.lower() in ("recovery", "hrv", "sleep", "strain", "whoop", "health")
        for kw in intent.keywords
    )
    if not needs_health and intent.query_type != "FACTUAL":
        return []

    q = select(HealthMetric)

    if intent.date_start:
        try:
            d = datetime.date.fromisoformat(intent.date_start)
            q = q.where(HealthMetric.entry_date >= d)
        except ValueError:
            pass
    if intent.date_end:
        try:
            d = datetime.date.fromisoformat(intent.date_end)
            q = q.where(HealthMetric.entry_date <= d)
        except ValueError:
            pass

    q = q.order_by(HealthMetric.entry_date).limit(30)
    rows = (await db.execute(q)).scalars().all()

    items: list[ContextItem] = []
    for h in rows:
        parts = []
        if h.recovery_score is not None:
            parts.append(f"Recovery: {h.recovery_score}%")
        if h.hrv_rmssd is not None:
            parts.append(f"HRV: {h.hrv_rmssd}ms")
        if h.sleep_performance_pct is not None:
            parts.append(f"Sleep: {h.sleep_performance_pct}%")
        if h.sleep_duration_minutes is not None:
            hrs = h.sleep_duration_minutes // 60
            mins = h.sleep_duration_minutes % 60
            parts.append(f"Sleep duration: {hrs}h{mins}m")
        if h.day_strain is not None:
            parts.append(f"Strain: {h.day_strain}")
        if h.calories_total is not None:
            parts.append(f"Calories: {h.calories_total}")

        if not parts:
            continue

        items.append(ContextItem(
            type="health_metric",
            date=h.entry_date.isoformat(),
            content=", ".join(parts),
            metadata={"source": h.source},
        ))

    return items


# ── Full retrieval pipeline ──────────────────────────────────────────


@dataclass
class RetrievalResult:
    intent: ParsedIntent
    context_items: list[ContextItem] = field(default_factory=list)
    date_range: tuple[str, str] = ("unknown", "unknown")


async def retrieve(db: AsyncSession, query: str) -> RetrievalResult:
    intent = await classify_intent(db, query)
    date_range = await _get_date_range(db)

    result = RetrievalResult(intent=intent, date_range=date_range)

    events = await _retrieve_life_events(db, intent)
    reflections = await _retrieve_reflections(db, intent)
    health = await _retrieve_health_metrics(db, intent)

    result.context_items.extend(events)
    result.context_items.extend(reflections)
    result.context_items.extend(health)

    if intent.query_type in ("THEMATIC", "META") or len(result.context_items) < 3:
        try:
            hits: list[SemanticHit] = await semantic_search(db, query, top_k=5)
            seen_texts = {item.content[:100] for item in result.context_items}
            for hit in hits:
                if hit.chunk_text[:100] not in seen_texts:
                    result.context_items.append(ContextItem(
                        type="journal_chunk",
                        date=hit.entry_date,
                        content=hit.chunk_text,
                        metadata={"similarity": hit.score},
                    ))
        except Exception as exc:
            logger.warning("Semantic search failed (embeddings may not exist): %s", exc)

    return result
