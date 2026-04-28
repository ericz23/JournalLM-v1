"""Dashboard data-layer service — Step 7.

Single read-side aggregator for `GET /api/dashboard/data`. The route is a
thin adapter: parse `ref_date`, call `build_payload`, return.

All widget data is computed for a rolling 7-day window ending on
`ref_date`. The previous 7-day window is computed in parallel so widgets
can show "vs last week" deltas without a second round-trip.

Helpers run in `asyncio.gather` where independent (the four entity
helpers); dietary repeat-visit counting depends on a corpus-wide DIETARY
scan and runs sequentially.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.journal_entry import JournalEntry
from app.models.journal_reflection import JournalReflection
from app.models.life_event import EventCategory, LifeEvent, SentimentLabel
from app.models.people import Person
from app.models.person_mention import PersonMention
from app.models.project_event import ProjectEvent
from app.models.projects import Project, ProjectStatus

logger = logging.getLogger(__name__)


# ── Pydantic response models (§13) ──────────────────────────────────


class WindowMeta(BaseModel):
    start: datetime.date
    end: datetime.date
    previous_start: datetime.date
    previous_end: datetime.date


class FollowUpLink(BaseModel):
    matched_kind: Literal["life_event", "project_event"]
    matched_count: int
    sample_description: str
    sample_date: datetime.date
    project_id: int | None = None


class ReflectionRow(BaseModel):
    date: datetime.date
    topic: str
    content: str
    is_actionable: bool
    is_recurring: bool = False
    follow_up: FollowUpLink | None = None


class DiningRow(BaseModel):
    date: datetime.date
    restaurant: str
    dishes: list[str] = Field(default_factory=list)
    meal_type: str = ""
    sentiment: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"] | None = None
    description: str
    visit_count_total: int
    visit_count_window: int
    is_repeat: bool


class LearningRow(BaseModel):
    date: datetime.date
    subject: str
    milestone: str
    description: str
    sentiment: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"] | None = None


class LearningSubjectTimeline(BaseModel):
    subject: str
    sessions_window: int
    last_milestone: str | None
    last_session_date: datetime.date
    sentiment_distribution: dict[str, int]


class InnerCirclePerson(BaseModel):
    person_id: int
    canonical_name: str
    relationship_type: str | None = None
    mention_count_window: int
    mention_count_previous: int
    last_mention_date: datetime.date
    last_mention_snippet: str | None = None
    sentiment_distribution: dict[str, int]
    dominant_sentiment: Literal["POSITIVE", "NEUTRAL", "NEGATIVE", "MIXED"] | None = None
    days_since_last_mention: int


class ActiveProject(BaseModel):
    project_id: int
    name: str
    category: str | None = None
    status: Literal["ACTIVE", "PAUSED"]
    update_count_window: int
    update_count_previous: int
    last_event_date: datetime.date
    last_event_snippet: str | None = None
    last_event_type: str | None = None
    streak_dot_sequence: list[bool]
    is_dormant: bool
    days_since_last_event: int
    target_date: datetime.date | None = None


class DashboardPayload(BaseModel):
    has_data: bool
    window: WindowMeta | None = None
    inner_circle: list[InnerCirclePerson] = Field(default_factory=list)
    inner_circle_total: int = 0
    inner_circle_insight: str | None = None
    active_projects: list[ActiveProject] = Field(default_factory=list)
    active_projects_total: int = 0
    active_projects_insight: str | None = None
    dining: list[DiningRow] = Field(default_factory=list)
    reflections: list[ReflectionRow] = Field(default_factory=list)
    learning: list[LearningRow] = Field(default_factory=list)
    learning_by_subject: list[LearningSubjectTimeline] = Field(default_factory=list)


# ── Window resolution ───────────────────────────────────────────────


@dataclass
class _Window:
    start: datetime.date
    end: datetime.date
    previous_start: datetime.date
    previous_end: datetime.date


def _resolve_window(ref_date: datetime.date) -> _Window:
    end = ref_date
    start = end - datetime.timedelta(days=6)
    prev_end = start - datetime.timedelta(days=1)
    prev_start = prev_end - datetime.timedelta(days=6)
    return _Window(start=start, end=end, previous_start=prev_start, previous_end=prev_end)


async def _get_latest_journal_date(db: AsyncSession) -> datetime.date | None:
    return (
        await db.execute(select(func.max(JournalEntry.entry_date)))
    ).scalar()


# ── Loaders ─────────────────────────────────────────────────────────


async def _load_events_in_window(
    db: AsyncSession,
    start: datetime.date,
    end: datetime.date,
) -> list[LifeEvent]:
    rows = (await db.execute(
        select(LifeEvent)
        .where(and_(LifeEvent.entry_date >= start, LifeEvent.entry_date <= end))
        .order_by(LifeEvent.entry_date.desc(), LifeEvent.id)
    )).scalars().all()
    return list(rows)


async def _load_reflections_in_window(
    db: AsyncSession,
    start: datetime.date,
    end: datetime.date,
) -> list[JournalReflection]:
    rows = (await db.execute(
        select(JournalReflection)
        .where(
            and_(
                JournalReflection.entry_date >= start,
                JournalReflection.entry_date <= end,
            )
        )
        .order_by(JournalReflection.entry_date.desc(), JournalReflection.id)
    )).scalars().all()
    return list(rows)


# ── Dining (§9) ─────────────────────────────────────────────────────


def _normalize_restaurant_key(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().casefold()


def _truncate(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


async def _build_dining(
    db: AsyncSession,
    window: _Window,
    events_in_window: list[LifeEvent],
) -> list[DiningRow]:
    """Build DiningRows with whole-corpus repeat-visit counts (§9.1)."""
    corpus_q = select(LifeEvent).where(LifeEvent.category == EventCategory.DIETARY)
    corpus_rows = (await db.execute(corpus_q)).scalars().all()

    total_counts: Counter[str] = Counter()
    for ev in corpus_rows:
        meta = json.loads(ev.metadata_json) if ev.metadata_json else {}
        restaurant = (meta or {}).get("restaurant")
        if restaurant:
            total_counts[_normalize_restaurant_key(restaurant)] += 1

    window_counts: Counter[str] = Counter()
    for ev in events_in_window:
        if ev.category != EventCategory.DIETARY:
            continue
        meta = json.loads(ev.metadata_json) if ev.metadata_json else {}
        restaurant = (meta or {}).get("restaurant")
        if restaurant:
            window_counts[_normalize_restaurant_key(restaurant)] += 1

    rows: list[DiningRow] = []
    for ev in events_in_window:
        if ev.category != EventCategory.DIETARY:
            continue
        meta = json.loads(ev.metadata_json) if ev.metadata_json else {}
        restaurant = (meta or {}).get("restaurant")
        if not restaurant:
            continue
        key = _normalize_restaurant_key(restaurant)
        total = total_counts.get(key, 0)
        rows.append(
            DiningRow(
                date=ev.entry_date,
                restaurant=restaurant,
                dishes=list(meta.get("dishes") or []),
                meal_type=meta.get("meal_type") or "",
                sentiment=ev.sentiment.value if ev.sentiment else None,
                description=ev.description,
                visit_count_total=total,
                visit_count_window=window_counts.get(key, 0),
                is_repeat=total > 1,
            )
        )
    return rows


# ── Learning (§10) ──────────────────────────────────────────────────


def _build_learning(events_in_window: list[LifeEvent]) -> tuple[list[LearningRow], list[LearningSubjectTimeline]]:
    flat: list[LearningRow] = []
    by_subject_rows: dict[str, list[LifeEvent]] = {}

    for ev in events_in_window:
        if ev.category != EventCategory.LEARNING:
            continue
        meta = json.loads(ev.metadata_json) if ev.metadata_json else {}
        subject = (meta or {}).get("subject") or ""
        milestone = (meta or {}).get("milestone") or ""

        flat.append(
            LearningRow(
                date=ev.entry_date,
                subject=subject,
                milestone=milestone,
                description=ev.description,
                sentiment=ev.sentiment.value if ev.sentiment else None,
            )
        )
        if subject:
            by_subject_rows.setdefault(subject, []).append(ev)

    timelines: list[LearningSubjectTimeline] = []
    for subject, rows in by_subject_rows.items():
        rows_sorted = sorted(rows, key=lambda r: r.entry_date, reverse=True)
        latest = rows_sorted[0]
        latest_meta = json.loads(latest.metadata_json) if latest.metadata_json else {}
        last_milestone = (latest_meta or {}).get("milestone") or None

        sentiment_dist: dict[str, int] = {
            label.value: 0 for label in SentimentLabel
        }
        for r in rows:
            if r.sentiment is not None:
                sentiment_dist[r.sentiment.value] += 1

        timelines.append(
            LearningSubjectTimeline(
                subject=subject,
                sessions_window=len(rows),
                last_milestone=last_milestone,
                last_session_date=latest.entry_date,
                sentiment_distribution=sentiment_dist,
            )
        )

    timelines.sort(key=lambda t: (-t.sessions_window, t.subject.lower()))
    return flat, timelines


# ── Reflections (§8) ────────────────────────────────────────────────


_REFLECTION_STOPWORDS = frozenset(
    {
        "about", "above", "after", "again", "against", "also", "always", "another",
        "around", "because", "been", "before", "being", "below", "between", "both",
        "could", "does", "doing", "down", "during", "each", "even", "every", "from",
        "further", "have", "having", "here", "into", "just", "keep", "kind", "less",
        "like", "lots", "made", "make", "many", "more", "most", "much", "must",
        "need", "next", "only", "other", "over", "really", "same", "should", "since",
        "some", "still", "such", "take", "than", "that", "their", "them", "then",
        "there", "these", "they", "thing", "things", "this", "those", "through",
        "today", "very", "want", "were", "what", "when", "where", "which", "while",
        "will", "with", "would", "your", "yourself",
    }
)
_KEYWORD_TOKENIZER = re.compile(r"[A-Za-z][A-Za-z']{3,}")
_FOLLOW_UP_KEYWORD_CAP = 50
_FOLLOW_UP_LOOKBACK_DAYS = 28


def _extract_keywords(*texts: str | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for text_ in texts:
        if not text_:
            continue
        for tok in _KEYWORD_TOKENIZER.findall(text_):
            lowered = tok.lower()
            if lowered in _REFLECTION_STOPWORDS or len(lowered) < 4:
                continue
            if lowered in seen:
                continue
            seen.add(lowered)
            out.append(lowered)
            if len(out) >= _FOLLOW_UP_KEYWORD_CAP:
                return out
    return out


async def _build_reflections(
    db: AsyncSession,
    window: _Window,
    reflections_in_window: list[JournalReflection],
    events_in_window: list[LifeEvent],
    project_events_in_window: list[ProjectEvent],
) -> list[ReflectionRow]:
    if not reflections_in_window:
        return []

    # Recurring-topic detection — single grouped query over the previous 4 weeks.
    recurring_topics: set[str] = set()
    rec_lookback_start = window.start - datetime.timedelta(days=28)
    rec_lookback_end = window.start - datetime.timedelta(days=1)
    if rec_lookback_end >= rec_lookback_start:
        rec_q = (
            select(func.lower(JournalReflection.topic))
            .where(
                and_(
                    JournalReflection.entry_date >= rec_lookback_start,
                    JournalReflection.entry_date <= rec_lookback_end,
                )
            )
            .group_by(func.lower(JournalReflection.topic))
        )
        prior_topics = (await db.execute(rec_q)).scalars().all()
        if len(prior_topics) > 200:
            logger.warning(
                "Recurring-topic check returned %d prior topics — stop list may need tuning.",
                len(prior_topics),
            )
        recurring_topics = {t for t in prior_topics if t}

    # Follow-up scan — load actionable reflections from the last 4 weeks.
    follow_lookback_start = window.start - datetime.timedelta(days=_FOLLOW_UP_LOOKBACK_DAYS)
    follow_q = (
        select(JournalReflection)
        .where(
            and_(
                JournalReflection.is_actionable.is_(True),
                JournalReflection.entry_date >= follow_lookback_start,
                JournalReflection.entry_date <= window.end,
            )
        )
        .order_by(JournalReflection.entry_date)
    )
    candidate_actionables = list((await db.execute(follow_q)).scalars().all())

    follow_ups_by_reflection_id: dict[int, FollowUpLink] = {}
    for cand in candidate_actionables:
        keywords = _extract_keywords(cand.topic, cand.content)
        if not keywords:
            continue

        project_matches: list[tuple[ProjectEvent, int]] = []
        for pe in project_events_in_window:
            content = (pe.content or "").lower()
            hits = sum(1 for kw in keywords if kw in content)
            if hits:
                project_matches.append((pe, hits))

        life_matches: list[tuple[LifeEvent, int]] = []
        for ev in events_in_window:
            description = (ev.description or "").lower()
            hits = sum(1 for kw in keywords if kw in description)
            if hits:
                life_matches.append((ev, hits))

        logger.debug(
            "follow-up scan reflection_id=%s keywords=%d life_matches=%d project_matches=%d",
            cand.id, len(keywords), len(life_matches), len(project_matches),
        )

        if project_matches:
            project_matches.sort(key=lambda t: (t[0].entry_date, t[1]), reverse=True)
            top, _ = project_matches[0]
            follow_ups_by_reflection_id[cand.id] = FollowUpLink(
                matched_kind="project_event",
                matched_count=len(project_matches),
                sample_description=(top.content or "")[:180].strip(),
                sample_date=top.entry_date,
                project_id=top.project_id,
            )
        elif life_matches:
            life_matches.sort(key=lambda t: (t[0].entry_date, t[1]), reverse=True)
            top, _ = life_matches[0]
            follow_ups_by_reflection_id[cand.id] = FollowUpLink(
                matched_kind="life_event",
                matched_count=len(life_matches),
                sample_description=(top.description or "")[:180].strip(),
                sample_date=top.entry_date,
                project_id=None,
            )

    rows: list[ReflectionRow] = []
    for r in reflections_in_window:
        rows.append(
            ReflectionRow(
                date=r.entry_date,
                topic=r.topic,
                content=r.content,
                is_actionable=r.is_actionable,
                is_recurring=(r.topic or "").lower() in recurring_topics,
                follow_up=follow_ups_by_reflection_id.get(r.id),
            )
        )

    rows.sort(
        key=lambda x: (
            0 if x.is_actionable else 1,
            0 if x.is_recurring else 1,
            -x.date.toordinal(),
        )
    )
    return rows


# ── Inner Circle (§7) ───────────────────────────────────────────────


def _dominant_sentiment(
    distribution: dict[str, int],
) -> Literal["POSITIVE", "NEUTRAL", "NEGATIVE", "MIXED"] | None:
    total = sum(distribution.values())
    if total == 0:
        logger.warning("dominant_sentiment requested for empty distribution — returning None")
        return None
    for label, count in distribution.items():
        if count / total > 0.6:
            return label  # type: ignore[return-value]
    return "MIXED"


def _inner_circle_insight(rows: list[InnerCirclePerson]) -> str:
    n = len(rows)
    if n == 0:
        return "Quiet week — no logged social interactions."
    if n == 1:
        return f"One interaction this week — {rows[0].canonical_name}."
    if n <= 3:
        return f"You connected with {n} people this week."
    top = max(rows, key=lambda r: r.mention_count_window)
    return f"You connected with {n} people this week — {top.canonical_name} most often."


async def _build_inner_circle(
    db: AsyncSession,
    window: _Window,
) -> tuple[list[InnerCirclePerson], int, str]:
    current_q = (
        select(PersonMention, Person)
        .join(Person, PersonMention.person_id == Person.id)
        .where(
            and_(
                PersonMention.entry_date >= window.start,
                PersonMention.entry_date <= window.end,
            )
        )
        .order_by(PersonMention.entry_date.desc(), PersonMention.id.desc())
    )
    current_rows = (await db.execute(current_q)).all()

    if not current_rows:
        return [], 0, _inner_circle_insight([])

    by_person: dict[int, dict[str, Any]] = {}
    for mention, person in current_rows:
        bucket = by_person.setdefault(
            person.id,
            {
                "person": person,
                "mentions": [],
                "sentiment_dist": {label.value: 0 for label in SentimentLabel},
            },
        )
        bucket["mentions"].append(mention)
        if mention.sentiment is not None:
            bucket["sentiment_dist"][mention.sentiment.value] += 1

    person_ids = list(by_person.keys())

    previous_counts_q = (
        select(PersonMention.person_id, func.count(PersonMention.id))
        .where(
            and_(
                PersonMention.person_id.in_(person_ids),
                PersonMention.entry_date >= window.previous_start,
                PersonMention.entry_date <= window.previous_end,
            )
        )
        .group_by(PersonMention.person_id)
    )
    previous_counts: dict[int, int] = dict(
        (await db.execute(previous_counts_q)).all()
    )

    rows: list[InnerCirclePerson] = []
    for pid, bucket in by_person.items():
        person: Person = bucket["person"]
        mentions: list[PersonMention] = bucket["mentions"]
        # mentions arrive newest-first because of the query ORDER BY.
        latest = mentions[0]

        rows.append(
            InnerCirclePerson(
                person_id=person.id,
                canonical_name=person.canonical_name,
                relationship_type=person.relationship_type,
                mention_count_window=len(mentions),
                mention_count_previous=previous_counts.get(pid, 0),
                last_mention_date=latest.entry_date,
                last_mention_snippet=_truncate(latest.context_snippet, 220),
                sentiment_distribution=bucket["sentiment_dist"],
                dominant_sentiment=_dominant_sentiment(bucket["sentiment_dist"]),
                days_since_last_mention=(window.end - latest.entry_date).days,
            )
        )

    rows.sort(
        key=lambda r: (
            -r.mention_count_window,
            -r.last_mention_date.toordinal(),
            r.canonical_name.lower(),
        )
    )

    total = len(rows)
    capped = rows[: settings.DASHBOARD_INNER_CIRCLE_CAP]
    return capped, total, _inner_circle_insight(rows)


# ── Active Projects (§6) ────────────────────────────────────────────


def _active_projects_insight(rows: list[ActiveProject], total: int) -> str:
    if total == 0:
        return "No active projects yet."
    n_with_events = sum(1 for r in rows if r.update_count_window > 0)
    if n_with_events == 0:
        return f"All {total} active projects went quiet this week."
    return f"{n_with_events} of {total} active projects saw progress this week."


async def _build_active_projects(
    db: AsyncSession,
    window: _Window,
) -> tuple[list[ActiveProject], int, str, list[ProjectEvent]]:
    """Return (rows, total, insight, project_events_in_window).

    The fourth element is reused by the reflections follow-up scanner.
    """
    cutoff = window.start - datetime.timedelta(days=settings.DASHBOARD_PROJECT_RECENT_DAYS)

    eligible_q = (
        select(Project)
        .where(
            and_(
                Project.status.in_([ProjectStatus.ACTIVE, ProjectStatus.PAUSED]),
            )
        )
    )
    candidates: list[Project] = list((await db.execute(eligible_q)).scalars().all())

    if not candidates:
        return [], 0, _active_projects_insight([], 0), []

    candidate_ids = [p.id for p in candidates]

    window_events_q = (
        select(ProjectEvent)
        .where(
            and_(
                ProjectEvent.project_id.in_(candidate_ids),
                ProjectEvent.entry_date >= window.start,
                ProjectEvent.entry_date <= window.end,
            )
        )
        .order_by(ProjectEvent.entry_date.desc(), ProjectEvent.id.desc())
    )
    window_events: list[ProjectEvent] = list((await db.execute(window_events_q)).scalars().all())

    previous_events_q = (
        select(ProjectEvent.project_id, func.count(ProjectEvent.id))
        .where(
            and_(
                ProjectEvent.project_id.in_(candidate_ids),
                ProjectEvent.entry_date >= window.previous_start,
                ProjectEvent.entry_date <= window.previous_end,
            )
        )
        .group_by(ProjectEvent.project_id)
    )
    previous_counts: dict[int, int] = dict((await db.execute(previous_events_q)).all())

    latest_event_q = (
        select(ProjectEvent)
        .where(ProjectEvent.project_id.in_(candidate_ids))
        .order_by(ProjectEvent.project_id, ProjectEvent.entry_date.desc(), ProjectEvent.id.desc())
    )
    latest_per_project: dict[int, ProjectEvent] = {}
    for pe in (await db.execute(latest_event_q)).scalars():
        latest_per_project.setdefault(pe.project_id, pe)

    window_events_by_project: dict[int, list[ProjectEvent]] = {}
    for pe in window_events:
        window_events_by_project.setdefault(pe.project_id, []).append(pe)

    rows: list[ActiveProject] = []
    for project in candidates:
        events_window = window_events_by_project.get(project.id, [])
        latest_event = latest_per_project.get(project.id)
        last_event_date = (
            latest_event.entry_date
            if latest_event
            else project.last_seen_date
        )

        # Eligibility per §6.1
        has_window_event = bool(events_window)
        recently_active = (
            project.status == ProjectStatus.ACTIVE
            and last_event_date is not None
            and last_event_date >= cutoff
        )
        if not (has_window_event or recently_active):
            continue
        if last_event_date is None:
            continue

        # Streak dot sequence — oldest → newest, length 7.
        dot_dates = {pe.entry_date for pe in events_window}
        sequence: list[bool] = []
        for offset in range(7):
            d = window.start + datetime.timedelta(days=offset)
            sequence.append(d in dot_dates)

        days_since = (window.end - last_event_date).days
        is_dormant = (window.start - last_event_date).days > settings.DASHBOARD_DORMANCY_DAYS
        logger.debug(
            "project=%s last_event=%s days_since=%d dormant=%s",
            project.name, last_event_date, days_since, is_dormant,
        )

        rows.append(
            ActiveProject(
                project_id=project.id,
                name=project.name,
                category=project.category,
                status=project.status.value,  # type: ignore[arg-type]
                update_count_window=len(events_window),
                update_count_previous=previous_counts.get(project.id, 0),
                last_event_date=last_event_date,
                last_event_snippet=_truncate(
                    latest_event.content if latest_event else None, 220
                ),
                last_event_type=(
                    latest_event.event_type.value if latest_event else None
                ),
                streak_dot_sequence=sequence,
                is_dormant=is_dormant,
                days_since_last_event=days_since,
                target_date=project.target_date,
            )
        )

    total_active = len(rows)
    rows.sort(
        key=lambda r: (
            -r.update_count_window,
            -r.last_event_date.toordinal(),
            r.name.lower(),
        )
    )
    capped = rows[: settings.DASHBOARD_ACTIVE_PROJECTS_CAP]
    insight = _active_projects_insight(rows, total_active)
    return capped, total_active, insight, window_events


# ── Orchestrator ────────────────────────────────────────────────────


async def build_payload(
    db: AsyncSession,
    ref_date: datetime.date | None = None,
) -> DashboardPayload:
    started = datetime.datetime.now(datetime.timezone.utc)

    latest = await _get_latest_journal_date(db)
    if latest is None:
        return DashboardPayload(has_data=False)

    ref = ref_date or latest
    window = _resolve_window(ref)

    events_in_window = await _load_events_in_window(db, window.start, window.end)
    reflections_in_window = await _load_reflections_in_window(db, window.start, window.end)

    inner_task = asyncio.create_task(_build_inner_circle(db, window))
    projects_task = asyncio.create_task(_build_active_projects(db, window))
    dining_task = asyncio.create_task(_build_dining(db, window, events_in_window))

    learning_flat, learning_by_subject = _build_learning(events_in_window)

    inner_rows, inner_total, inner_insight = await inner_task
    project_rows, project_total, project_insight, window_project_events = await projects_task
    dining_rows = await dining_task

    reflection_rows = await _build_reflections(
        db,
        window,
        reflections_in_window,
        events_in_window,
        window_project_events,
    )

    payload = DashboardPayload(
        has_data=True,
        window=WindowMeta(
            start=window.start,
            end=window.end,
            previous_start=window.previous_start,
            previous_end=window.previous_end,
        ),
        inner_circle=inner_rows,
        inner_circle_total=inner_total,
        inner_circle_insight=inner_insight,
        active_projects=project_rows,
        active_projects_total=project_total,
        active_projects_insight=project_insight,
        dining=dining_rows,
        reflections=reflection_rows,
        learning=learning_flat,
        learning_by_subject=learning_by_subject,
    )

    elapsed_ms = int(
        (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds() * 1000
    )
    logger.info(
        "dashboard payload built window=%s..%s inner_circle=%d active_projects=%d "
        "dining=%d reflections=%d learning=%d ms=%d",
        window.start, window.end,
        len(payload.inner_circle), len(payload.active_projects),
        len(payload.dining), len(payload.reflections), len(payload.learning),
        elapsed_ms,
    )

    return payload
