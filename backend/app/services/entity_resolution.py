"""Entity resolution — maps extracted surface strings to canonical entities.

Runs per journal entry inside the same transaction as the shredder, after
`life_events` and `journal_reflections` have been persisted. Produces:

- `person_mentions` and `project_events` for matched canonical entities.
- `entity_proposals (pending)` for unmatched surface strings.
- Project status inference (Q3) for matched projects.
- Aggregate recompute for touched `people` / `projects`.

No canonical `people` / `projects` rows are auto-created here (Q1).
Fuzzy matching only ranks candidates for the inbox — it never auto-merges (Q2).
Re-run on the same date is idempotent: prior pending proposals, mentions,
and events for that date are cleared and rebuilt (Q4).
"""

from __future__ import annotations

import datetime
import json
import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity_blocklist import EntityBlocklist
from app.models.entity_proposal import (
    EntityProposal,
    ProposalEntityType,
    ProposalStatus,
)
from app.models.life_event import LifeEvent
from app.models.people import Person
from app.models.person_mention import PersonMention
from app.models.project_event import ProjectEvent, ProjectEventType
from app.models.projects import Project, ProjectStatus

logger = logging.getLogger(__name__)


# ── Result type ──────────────────────────────────────────────────────


@dataclass
class ResolutionResult:
    person_mentions_created: int = 0
    project_events_created: int = 0
    person_proposals_created: int = 0
    project_proposals_created: int = 0
    project_status_transitions: int = 0
    skipped_blocked: int = 0
    errors: list[str] = field(default_factory=list)


# ── Normalization ────────────────────────────────────────────────────


_MAX_SURFACE_LEN = 200
_TRAILING_PUNCT = ".,;:\"'"


def _normalize_surface(name: str | None) -> str | None:
    """Normalize a surface string for storage and matching.

    Returns None if the string is empty after normalization.
    """
    if name is None:
        return None
    s = name.strip()
    # Strip surrounding quotes.
    while len(s) >= 2 and s[0] in "\"'" and s[-1] in "\"'":
        s = s[1:-1].strip()
    # Collapse internal whitespace.
    s = re.sub(r"\s+", " ", s)
    # Trim trailing punctuation.
    while s and s[-1] in _TRAILING_PUNCT:
        s = s[:-1].rstrip()
    if not s:
        return None
    if len(s) > _MAX_SURFACE_LEN:
        logger.warning("Surface string truncated to %d chars: %r", _MAX_SURFACE_LEN, s)
        s = s[:_MAX_SURFACE_LEN]
    return s


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"\s+", s.lower()) if t]


# ── Alias utilities ──────────────────────────────────────────────────


def _parse_aliases(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Could not parse aliases_json: %r", raw)
        return []
    if isinstance(data, list):
        return [str(x) for x in data if isinstance(x, (str, int))]
    return []


def _lower_or_none(s: str | None) -> str | None:
    return s.lower() if s else None


# ── Matching ─────────────────────────────────────────────────────────


async def _match_person(db: AsyncSession, surface: str) -> tuple[Person | None, bool]:
    """Try to match surface string to an existing Person.

    Returns (person_or_None, ambiguous). `ambiguous=True` means multiple
    alias candidates matched and the caller should fall back to a proposal.
    """
    lower = surface.lower()
    people = (await db.execute(select(Person))).scalars().all()

    canonical_matches = [p for p in people if p.canonical_name.lower() == lower]
    if len(canonical_matches) == 1:
        return canonical_matches[0], False
    if len(canonical_matches) > 1:
        return None, True

    alias_matches = [
        p
        for p in people
        if any(a.lower() == lower for a in _parse_aliases(p.aliases_json))
    ]
    if len(alias_matches) == 1:
        return alias_matches[0], False
    if len(alias_matches) > 1:
        return None, True

    return None, False


async def _match_project(db: AsyncSession, surface: str) -> tuple[Project | None, bool]:
    lower = surface.lower()
    projects = (await db.execute(select(Project))).scalars().all()

    name_matches = [p for p in projects if p.name.lower() == lower]
    if len(name_matches) == 1:
        return name_matches[0], False
    if len(name_matches) > 1:
        return None, True

    alias_matches = [
        p
        for p in projects
        if any(a.lower() == lower for a in _parse_aliases(p.aliases_json))
    ]
    if len(alias_matches) == 1:
        return alias_matches[0], False
    if len(alias_matches) > 1:
        return None, True

    return None, False


# ── Fuzzy candidate ranking (for proposals only) ─────────────────────


_CANDIDATE_TOP_N = 5
_CANDIDATE_MIN_SCORE = 0.35


def _edit_ratio(a: str, b: str) -> float:
    """Normalized similarity in [0, 1]. 1.0 = identical."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _token_overlap(a: str, b: str) -> float:
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _prefix_match(surface: str, name: str) -> bool:
    s, n = surface.lower(), name.lower()
    if not s or not n:
        return False
    if s.startswith(n) or n.startswith(s):
        return True
    for tok in _tokens(s):
        if n.startswith(tok):
            return True
    return False


def _score_candidate(surface: str, candidate_strings: list[str]) -> tuple[float, dict]:
    """Score a surface against a set of (canonical + alias) strings.

    Returns (composite_score, signals_dict).
    """
    best_prefix = any(_prefix_match(surface, c) for c in candidate_strings)
    best_overlap = max((_token_overlap(surface, c) for c in candidate_strings), default=0.0)
    best_edit = max((_edit_ratio(surface, c) for c in candidate_strings), default=0.0)

    score = (
        0.3 * (1.0 if best_prefix else 0.0)
        + 0.35 * best_overlap
        + 0.35 * best_edit
    )
    signals = {
        "exact_prefix": best_prefix,
        "token_overlap": round(best_overlap, 3),
        "edit_distance_ratio": round(1 - best_edit, 3),
    }
    return score, signals


def _rank_people_candidates(surface: str, people: list[Person]) -> list[dict]:
    ranked = []
    for p in people:
        strs = [p.canonical_name] + _parse_aliases(p.aliases_json)
        score, signals = _score_candidate(surface, strs)
        if score >= _CANDIDATE_MIN_SCORE:
            ranked.append(
                {
                    "entity_id": p.id,
                    "canonical_name": p.canonical_name,
                    "score": round(score, 3),
                    "signals": signals,
                }
            )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:_CANDIDATE_TOP_N]


def _rank_project_candidates(surface: str, projects: list[Project]) -> list[dict]:
    ranked = []
    for p in projects:
        strs = [p.name] + _parse_aliases(p.aliases_json)
        score, signals = _score_candidate(surface, strs)
        if score >= _CANDIDATE_MIN_SCORE:
            ranked.append(
                {
                    "entity_id": p.id,
                    "canonical_name": p.name,
                    "score": round(score, 3),
                    "signals": signals,
                }
            )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:_CANDIDATE_TOP_N]


# ── Blocklist ────────────────────────────────────────────────────────


async def _is_blocked(
    db: AsyncSession,
    entity_type: ProposalEntityType,
    surface: str,
) -> bool:
    lower = surface.lower()
    q = select(EntityBlocklist).where(EntityBlocklist.entity_type == entity_type)
    rows = (await db.execute(q)).scalars().all()
    return any(r.surface_name.lower() == lower for r in rows)


# ── life_event_id linking ────────────────────────────────────────────


_LINK_MIN_OVERLAP = 0.5


def _pick_linked_event(
    hint: str | None,
    events_by_date: list[LifeEvent],
) -> int | None:
    if not hint:
        return None
    h = hint.strip().lower()
    if not h:
        return None

    for ev in events_by_date:
        if (ev.description or "").strip().lower() == h:
            return ev.id
        if (ev.source_snippet or "").strip().lower() == h:
            return ev.id

    best_id: int | None = None
    best_score = 0.0
    for ev in events_by_date:
        haystack = " ".join(
            [ev.description or "", ev.source_snippet or ""]
        ).strip()
        if not haystack:
            continue
        score = _token_overlap(h, haystack)
        if score > best_score:
            best_score = score
            best_id = ev.id

    if best_score >= _LINK_MIN_OVERLAP:
        return best_id
    return None


# ── Sentiment coercion (reused from shredder but kept local to avoid cycle) ──


def _coerce_sentiment(raw: str | None):
    from app.models.life_event import SentimentLabel

    if not raw:
        return None
    upper = raw.strip().upper()
    if upper in SentimentLabel.__members__:
        return SentimentLabel[upper]
    return None


# ── Project status inference (Q3) ────────────────────────────────────


def _coerce_project_status(raw: str | None) -> ProjectStatus | None:
    if not raw:
        return None
    upper = raw.strip().upper()
    if upper in ProjectStatus.__members__:
        return ProjectStatus[upper]
    return None


def _infer_next_status(
    current: ProjectStatus,
    event_type: ProjectEventType,
    suggested: ProjectStatus | None,
) -> ProjectStatus:
    """Apply the Step 3 §12 decision table. Returns the new status (possibly equal)."""
    et = event_type
    s = suggested

    if et == ProjectEventType.START:
        return ProjectStatus.ACTIVE

    if et == ProjectEventType.PAUSE:
        if current == ProjectStatus.ACTIVE:
            return ProjectStatus.PAUSED
        return current

    if et == ProjectEventType.MILESTONE:
        if s == ProjectStatus.COMPLETED and current != ProjectStatus.COMPLETED:
            return ProjectStatus.COMPLETED
        return current

    if et == ProjectEventType.PROGRESS:
        if current == ProjectStatus.PAUSED:
            return ProjectStatus.ACTIVE
        return current

    if et == ProjectEventType.SETBACK:
        if s == ProjectStatus.ABANDONED:
            return ProjectStatus.ABANDONED
        return current

    return current


# ── Project event_type coercion ──────────────────────────────────────


def _coerce_event_type(raw: str | None) -> ProjectEventType | None:
    if not raw:
        return None
    # DB enum values are lowercase strings.
    lower = raw.strip().lower()
    for member in ProjectEventType:
        if member.value == lower:
            return member
    # Also accept uppercase name style.
    upper = raw.strip().upper()
    if upper in ProjectEventType.__members__:
        return ProjectEventType[upper]
    return None


# ── Aggregate recompute ──────────────────────────────────────────────


async def _recompute_person_aggregates(db: AsyncSession, person_id: int) -> None:
    count = (
        await db.execute(
            select(func.count(PersonMention.id)).where(PersonMention.person_id == person_id)
        )
    ).scalar() or 0
    first_seen = (
        await db.execute(
            select(func.min(PersonMention.entry_date)).where(
                PersonMention.person_id == person_id
            )
        )
    ).scalar()
    last_seen = (
        await db.execute(
            select(func.max(PersonMention.entry_date)).where(
                PersonMention.person_id == person_id
            )
        )
    ).scalar()
    person = (
        await db.execute(select(Person).where(Person.id == person_id))
    ).scalar_one_or_none()
    if person is None:
        return
    person.mention_count = count
    person.first_seen_date = first_seen
    person.last_seen_date = last_seen


async def _recompute_project_aggregates(db: AsyncSession, project_id: int) -> None:
    count = (
        await db.execute(
            select(func.count(ProjectEvent.id)).where(ProjectEvent.project_id == project_id)
        )
    ).scalar() or 0
    first_seen = (
        await db.execute(
            select(func.min(ProjectEvent.entry_date)).where(
                ProjectEvent.project_id == project_id
            )
        )
    ).scalar()
    last_seen = (
        await db.execute(
            select(func.max(ProjectEvent.entry_date)).where(
                ProjectEvent.project_id == project_id
            )
        )
    ).scalar()
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project is None:
        return
    project.mention_count = count
    project.first_seen_date = first_seen
    project.last_seen_date = last_seen


# ── Per-date clean slate ─────────────────────────────────────────────


async def _clear_date_state(
    db: AsyncSession,
    entry_date: datetime.date,
) -> tuple[set[int], set[int]]:
    """Delete per-date mentions/events and replaceable pending proposals.

    Returns (touched_person_ids, touched_project_ids) collected BEFORE deletion
    so aggregates can be recomputed post-rebuild.
    """
    person_ids = set(
        (
            await db.execute(
                select(PersonMention.person_id).where(
                    PersonMention.entry_date == entry_date
                )
            )
        ).scalars().all()
    )
    project_ids = set(
        (
            await db.execute(
                select(ProjectEvent.project_id).where(
                    ProjectEvent.entry_date == entry_date
                )
            )
        ).scalars().all()
    )

    await db.execute(
        delete(PersonMention).where(PersonMention.entry_date == entry_date)
    )
    await db.execute(
        delete(ProjectEvent).where(ProjectEvent.entry_date == entry_date)
    )

    replaceable = (
        ProposalStatus.PENDING,
        ProposalStatus.REJECTED,
        ProposalStatus.DISMISSED,
        ProposalStatus.BLOCKED,
    )
    await db.execute(
        delete(EntityProposal).where(
            EntityProposal.entry_date == entry_date,
            EntityProposal.status.in_(replaceable),
        )
    )

    return person_ids, project_ids


# ── Payload merging for dedup within a run ───────────────────────────


def _merge_person_payload(existing: dict | None, new: dict) -> dict:
    if not existing:
        return {
            "mentions": [new],
        }
    existing.setdefault("mentions", []).append(new)
    return existing


def _merge_project_payload(existing: dict | None, new: dict) -> dict:
    if not existing:
        return {
            "events": [new],
        }
    existing.setdefault("events", []).append(new)
    return existing


# ── Public entry point ───────────────────────────────────────────────


async def resolve_entry(
    db: AsyncSession,
    entry_date: datetime.date,
    life_events: list[LifeEvent],
    extraction,  # ExtractionResponse from shredder (avoid import cycle)
) -> ResolutionResult:
    """Resolve Step 2 extraction output into mentions/events/proposals.

    Must be called after life_events/reflections are flushed so IDs exist,
    and before the outer transaction commits.
    """
    result = ResolutionResult()

    try:
        touched_person_ids, touched_project_ids = await _clear_date_state(db, entry_date)

        all_people = (await db.execute(select(Person))).scalars().all()
        all_projects = (await db.execute(select(Project))).scalars().all()

        # ── People ──────────────────────────────────────────────────
        person_proposal_by_key: dict[str, EntityProposal] = {}
        person_proposal_payloads: dict[str, dict] = {}

        for item in getattr(extraction, "people_mentioned", []) or []:
            surface = _normalize_surface(getattr(item, "name", None))
            if not surface:
                continue

            if await _is_blocked(db, ProposalEntityType.PERSON, surface):
                result.skipped_blocked += 1
                logger.info("Blocked person surface: %r", surface)
                continue

            link_id = _pick_linked_event(
                getattr(item, "linked_event_hint", None), life_events
            )

            person, ambiguous = await _match_person(db, surface)

            if person is not None and not ambiguous:
                db.add(
                    PersonMention(
                        person_id=person.id,
                        entry_date=entry_date,
                        life_event_id=link_id,
                        context_snippet=(getattr(item, "interaction_context", None) or "")[:500] or None,
                        sentiment=_coerce_sentiment(getattr(item, "sentiment", None)),
                    )
                )
                result.person_mentions_created += 1
                touched_person_ids.add(person.id)
                continue

            # No match (or ambiguous) → proposal.
            key = surface.lower()
            payload_item = {
                "name": surface,
                "relationship_hint": getattr(item, "relationship_hint", None),
                "interaction_context": getattr(item, "interaction_context", None),
                "linked_event_hint": getattr(item, "linked_event_hint", None),
                "sentiment": getattr(item, "sentiment", None),
            }

            if key in person_proposal_by_key:
                merged = _merge_person_payload(person_proposal_payloads[key], payload_item)
                person_proposal_payloads[key] = merged
                person_proposal_by_key[key].payload_json = json.dumps(merged)
                continue

            candidates = _rank_people_candidates(surface, all_people)
            proposal = EntityProposal(
                entity_type=ProposalEntityType.PERSON,
                status=ProposalStatus.PENDING,
                surface_name=surface,
                entry_date=entry_date,
                life_event_id=link_id,
                payload_json=json.dumps(_merge_person_payload(None, payload_item)),
                candidate_matches_json=json.dumps(candidates),
            )
            db.add(proposal)
            person_proposal_by_key[key] = proposal
            person_proposal_payloads[key] = json.loads(proposal.payload_json)
            result.person_proposals_created += 1

        # ── Projects ────────────────────────────────────────────────
        project_proposal_by_key: dict[str, EntityProposal] = {}
        project_proposal_payloads: dict[str, dict] = {}

        # Track status transitions — last-write-wins per project within run.
        pending_status: dict[int, ProjectStatus] = {}

        for item in getattr(extraction, "project_events", []) or []:
            surface = _normalize_surface(getattr(item, "project_name", None))
            if not surface:
                continue

            event_type = _coerce_event_type(getattr(item, "event_type", None))
            if event_type is None:
                logger.warning(
                    "Unknown project event_type %r for %r; skipping",
                    getattr(item, "event_type", None),
                    surface,
                )
                continue

            if await _is_blocked(db, ProposalEntityType.PROJECT, surface):
                result.skipped_blocked += 1
                logger.info("Blocked project surface: %r", surface)
                continue

            link_id = _pick_linked_event(
                getattr(item, "linked_event_hint", None), life_events
            )
            description = (getattr(item, "description", "") or "").strip()
            suggested = _coerce_project_status(
                getattr(item, "suggested_project_status", None)
            )

            project, ambiguous = await _match_project(db, surface)

            if project is not None and not ambiguous:
                db.add(
                    ProjectEvent(
                        project_id=project.id,
                        entry_date=entry_date,
                        life_event_id=link_id,
                        event_type=event_type,
                        content=description,
                    )
                )
                result.project_events_created += 1
                touched_project_ids.add(project.id)

                current = pending_status.get(project.id, project.status)
                next_status = _infer_next_status(current, event_type, suggested)
                if next_status != current:
                    pending_status[project.id] = next_status
                elif project.id not in pending_status:
                    pending_status[project.id] = current
                continue

            # No match → proposal.
            key = surface.lower()
            payload_item = {
                "project_name": surface,
                "event_type": event_type.value,
                "description": description,
                "linked_event_hint": getattr(item, "linked_event_hint", None),
                "suggested_project_status": (
                    suggested.value if suggested is not None else None
                ),
            }

            if key in project_proposal_by_key:
                merged = _merge_project_payload(project_proposal_payloads[key], payload_item)
                project_proposal_payloads[key] = merged
                project_proposal_by_key[key].payload_json = json.dumps(merged)
                continue

            candidates = _rank_project_candidates(surface, all_projects)
            proposal = EntityProposal(
                entity_type=ProposalEntityType.PROJECT,
                status=ProposalStatus.PENDING,
                surface_name=surface,
                entry_date=entry_date,
                life_event_id=link_id,
                payload_json=json.dumps(_merge_project_payload(None, payload_item)),
                candidate_matches_json=json.dumps(candidates),
            )
            db.add(proposal)
            project_proposal_by_key[key] = proposal
            project_proposal_payloads[key] = json.loads(proposal.payload_json)
            result.project_proposals_created += 1

        # ── Apply project status transitions ────────────────────────
        for project_id, new_status in pending_status.items():
            project = (
                await db.execute(select(Project).where(Project.id == project_id))
            ).scalar_one_or_none()
            if project is None:
                continue
            if project.status != new_status:
                logger.info(
                    "Project %s: status %s → %s",
                    project.name,
                    project.status.value,
                    new_status.value,
                )
                project.status = new_status
                result.project_status_transitions += 1

        # Flush so newly inserted mentions/events are visible to aggregate
        # recompute queries.
        await db.flush()

        # ── Aggregate recompute for all touched entities ────────────
        for pid in touched_person_ids:
            await _recompute_person_aggregates(db, pid)
        for pid in touched_project_ids:
            await _recompute_project_aggregates(db, pid)

    except Exception as exc:
        logger.exception("Resolution failed for %s", entry_date)
        result.errors.append(str(exc))
        raise

    return result
