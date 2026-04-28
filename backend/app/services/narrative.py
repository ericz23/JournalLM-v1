"""Weekly narrative generation with DB caching — Step 7.

V2 changes (vs Step 0/V1):
- Cache key migrated from `week_start` (Mon–Sun) to `window_end` (rolling 7-day),
  matching `services/dashboard._resolve_window`.
- Prompt feeds **two** weeks of data (current + previous) plus entity rollups
  (top inner circle, top active projects).
- Narrative rows expose a `stale_at` flag. Hooks in the shredder and the
  inbox actions mark rows stale; this service regenerates them on next call
  and clears the flag.

The legacy `week_start` / `week_end` columns are still populated on new rows
to keep the V1 unique constraint valid; lookup is on `window_end` only.
"""

from __future__ import annotations

import datetime
import json
import logging

from google import genai
from google.genai import types
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.journal_reflection import JournalReflection
from app.models.life_event import LifeEvent
from app.models.narrative_cache import NarrativeCache
from app.models.people import Person
from app.models.person_mention import PersonMention
from app.models.project_event import ProjectEvent
from app.models.projects import Project, ProjectStatus
from app.services.dashboard import _resolve_window

logger = logging.getLogger(__name__)

NARRATIVE_PROMPT_V2 = """\
You are the editorial voice of JournalLM.

Compare THIS WEEK ({current_start}..{current_end}) to LAST WEEK \
({previous_start}..{previous_end}, may be empty) and write a 2–3 sentence \
"Narrative Snapshot" capturing trajectory, themes, and any forward-looking \
thread the reflections suggest.

Reference people and projects by name when relevant. Vary tone:
- Many positive events + high social/learning activity → energetic.
- Sparse data or many negative-sentiment events → gentler, less performative.

Keep under 80 words. Second person ("You..."). No bullet points, no headings.

━━━ THIS WEEK ━━━
EVENTS:
{current_events}

REFLECTIONS:
{current_reflections}

INNER CIRCLE:
{current_inner_circle}

ACTIVE PROJECTS:
{current_active_projects}

━━━ LAST WEEK (for comparison only) ━━━
EVENTS:
{previous_events}

INNER CIRCLE:
{previous_inner_circle}

ACTIVE PROJECTS:
{previous_active_projects}
"""


# ── Client ──────────────────────────────────────────────────────────


def _build_client() -> genai.Client:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=settings.GEMINI_API_KEY)


# ── Window data assembly (§11.2) ────────────────────────────────────


_TOP_PEOPLE = 5
_TOP_PROJECTS = 5


async def _gather_window_text(
    db: AsyncSession,
    start: datetime.date,
    end: datetime.date,
) -> tuple[str, str, int]:
    """Return (events_text, reflections_text, event_count) for [start, end]."""
    events = (await db.execute(
        select(LifeEvent)
        .where(and_(LifeEvent.entry_date >= start, LifeEvent.entry_date <= end))
        .order_by(LifeEvent.entry_date)
    )).scalars().all()

    reflections = (await db.execute(
        select(JournalReflection)
        .where(
            and_(
                JournalReflection.entry_date >= start,
                JournalReflection.entry_date <= end,
            )
        )
        .order_by(JournalReflection.entry_date)
    )).scalars().all()

    event_lines: list[str] = []
    for e in events:
        _meta = json.loads(e.metadata_json) if e.metadata_json else {}  # noqa: F841
        event_lines.append(
            f"[{e.entry_date}] {e.category.value}: {e.description} "
            f"(sentiment: {e.sentiment.value if e.sentiment else 'UNKNOWN'})"
        )

    ref_lines: list[str] = []
    for r in reflections:
        flag = " [ACTIONABLE]" if r.is_actionable else ""
        ref_lines.append(f"[{r.entry_date}] {r.topic}: {r.content}{flag}")

    return (
        "\n".join(event_lines) or "No events.",
        "\n".join(ref_lines) or "No reflections.",
        len(events),
    )


async def _gather_inner_circle_top(
    db: AsyncSession,
    start: datetime.date,
    end: datetime.date,
) -> str:
    q = (
        select(Person.canonical_name, func.count(PersonMention.id).label("mention_count"))
        .join(PersonMention, PersonMention.person_id == Person.id)
        .where(
            and_(
                PersonMention.entry_date >= start,
                PersonMention.entry_date <= end,
            )
        )
        .group_by(Person.id, Person.canonical_name)
        .order_by(func.count(PersonMention.id).desc(), Person.canonical_name)
        .limit(_TOP_PEOPLE)
    )
    rows = (await db.execute(q)).all()
    if not rows:
        return "No data"
    return "\n".join(f"- {name} ({count}x)" for name, count in rows)


async def _gather_active_projects_top(
    db: AsyncSession,
    start: datetime.date,
    end: datetime.date,
) -> str:
    # Most-recent event per project within the window for the event_type hint.
    latest_evt_subq = (
        select(
            ProjectEvent.project_id,
            func.max(ProjectEvent.entry_date).label("latest_date"),
        )
        .where(
            and_(
                ProjectEvent.entry_date >= start,
                ProjectEvent.entry_date <= end,
            )
        )
        .group_by(ProjectEvent.project_id)
        .subquery()
    )

    q = (
        select(
            Project.name,
            func.count(ProjectEvent.id).label("update_count"),
            latest_evt_subq.c.latest_date,
        )
        .join(ProjectEvent, ProjectEvent.project_id == Project.id)
        .join(latest_evt_subq, latest_evt_subq.c.project_id == Project.id)
        .where(
            and_(
                ProjectEvent.entry_date >= start,
                ProjectEvent.entry_date <= end,
                Project.status.in_([ProjectStatus.ACTIVE, ProjectStatus.PAUSED]),
            )
        )
        .group_by(Project.id, Project.name, latest_evt_subq.c.latest_date)
        .order_by(func.count(ProjectEvent.id).desc(), Project.name)
        .limit(_TOP_PROJECTS)
    )
    rows = (await db.execute(q)).all()
    if not rows:
        return "No data"

    # Resolve last event_type per project for context (one extra round-trip).
    out_lines: list[str] = []
    for name, update_count, _latest in rows:
        last_type_q = (
            select(ProjectEvent.event_type)
            .join(Project, ProjectEvent.project_id == Project.id)
            .where(
                and_(
                    Project.name == name,
                    ProjectEvent.entry_date >= start,
                    ProjectEvent.entry_date <= end,
                )
            )
            .order_by(ProjectEvent.entry_date.desc(), ProjectEvent.id.desc())
            .limit(1)
        )
        last_type = (await db.execute(last_type_q)).scalar_one_or_none()
        type_hint = f" — {last_type.value}" if last_type else ""
        out_lines.append(f"- {name} ({update_count} updates{type_hint})")
    return "\n".join(out_lines)


# ── Cache invalidation hook ─────────────────────────────────────────


async def mark_narrative_stale_for_date(
    db: AsyncSession,
    entry_date: datetime.date,
) -> int:
    """Mark every cached narrative whose window contains `entry_date` stale.

    Idempotent: calling on a date with no covering rows is a no-op. The caller
    owns the transaction commit.
    """
    upper = entry_date  # window_end >= entry_date
    lower = entry_date + datetime.timedelta(days=6)  # window_end <= entry_date + 6
    now = datetime.datetime.now(datetime.timezone.utc)

    stmt = (
        update(NarrativeCache)
        .where(
            and_(
                NarrativeCache.window_end.is_not(None),
                NarrativeCache.window_end >= upper,
                NarrativeCache.window_end <= lower,
            )
        )
        .values(stale_at=now)
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(stmt)
    return result.rowcount or 0


# ── Public entry point ──────────────────────────────────────────────


async def get_or_generate_narrative(
    db: AsyncSession,
    reference_date: datetime.date | None = None,
) -> dict:
    """Return cached narrative for the rolling 7-day window ending on
    `reference_date`, regenerating if missing or stale."""
    if reference_date is None:
        reference_date = datetime.date.today()

    window = _resolve_window(reference_date)
    window_start, window_end = window.start, window.end
    prev_start, prev_end = window.previous_start, window.previous_end

    cached = (await db.execute(
        select(NarrativeCache).where(NarrativeCache.window_end == window_end)
    )).scalar_one_or_none()

    if cached is not None and cached.stale_at is None:
        return _serialize(cached, window_start, window_end, cached_flag=True)

    current_events_text, current_refs_text, current_event_count = await _gather_window_text(
        db, window_start, window_end
    )
    if current_event_count == 0:
        # Empty / quiet week — return fallback, do not call the LLM, do not cache.
        return {
            "content": "No journal data available for this week yet.",
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "generated_at": None,
            "cached": False,
        }

    prev_events_text, _prev_refs_text, _prev_event_count = await _gather_window_text(
        db, prev_start, prev_end
    )
    current_inner = await _gather_inner_circle_top(db, window_start, window_end)
    current_projects = await _gather_active_projects_top(db, window_start, window_end)
    prev_inner = await _gather_inner_circle_top(db, prev_start, prev_end)
    prev_projects = await _gather_active_projects_top(db, prev_start, prev_end)

    started = datetime.datetime.now(datetime.timezone.utc)

    prompt = NARRATIVE_PROMPT_V2.format(
        current_start=window_start,
        current_end=window_end,
        previous_start=prev_start,
        previous_end=prev_end,
        current_events=current_events_text,
        current_reflections=current_refs_text,
        current_inner_circle=current_inner,
        current_active_projects=current_projects,
        previous_events=prev_events_text,
        previous_inner_circle=prev_inner,
        previous_active_projects=prev_projects,
    )

    client = _build_client()
    response = await client.aio.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.5),
    )

    narrative_text = (response.text or "").strip()

    if cached is None:
        entry = NarrativeCache(
            week_start=window_start,
            week_end=window_end,
            window_end=window_end,
            content=narrative_text,
            model_used=settings.GEMINI_MODEL,
            stale_at=None,
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        result_obj = entry
    else:
        cached.content = narrative_text
        cached.model_used = settings.GEMINI_MODEL
        cached.stale_at = None
        cached.week_start = window_start
        cached.week_end = window_end
        await db.commit()
        await db.refresh(cached)
        result_obj = cached

    elapsed_ms = int(
        (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds() * 1000
    )
    logger.info(
        "narrative generated window=%s..%s events=%d cached=False ms=%d",
        window_start, window_end, current_event_count, elapsed_ms,
    )

    return _serialize(result_obj, window_start, window_end, cached_flag=False)


def _serialize(
    row: NarrativeCache,
    window_start: datetime.date,
    window_end: datetime.date,
    *,
    cached_flag: bool,
) -> dict:
    return {
        "content": row.content,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "generated_at": row.created_at.isoformat() if row.created_at else None,
        "cached": cached_flag,
    }
