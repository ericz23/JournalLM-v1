"""Entity inbox service — applies user actions on `entity_proposals`.

Turns pending proposals into canonical `people` / `projects` rows plus their
`person_mentions` / `project_events`, or dismisses/blocks them. Reuses the
resolution primitives from `entity_resolution` so inbox confirmations and
automatic resolution stay in lockstep on matching/status inference.

Transactional boundaries: each action runs inside a single SQLAlchemy
AsyncSession. Route handlers commit on success and roll back on error.
"""

from __future__ import annotations

import datetime
import json
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity_blocklist import BlocklistReason, EntityBlocklist
from app.models.entity_proposal import (
    EntityProposal,
    ProposalEntityType,
    ProposalStatus,
)
from app.models.life_event import LifeEvent
from app.models.people import Person
from app.models.person_mention import PersonMention
from app.models.project_event import ProjectEvent
from app.models.projects import Project, ProjectStatus
from app.services.entity_resolution import (
    _coerce_event_type,
    _coerce_project_status,
    _coerce_sentiment,
    _infer_next_status,
    _normalize_surface,
    _pick_linked_event,
    _recompute_person_aggregates,
    _recompute_project_aggregates,
)

logger = logging.getLogger(__name__)


# ── Exceptions ──────────────────────────────────────────────────────


class InboxActionError(Exception):
    """Base inbox action error."""

    http_status: int = 400

    def __init__(self, message: str, payload: dict | None = None):
        super().__init__(message)
        self.message = message
        self.payload = payload or {}


class ProposalNotFound(InboxActionError):
    http_status = 404


class ProposalAlreadyResolved(InboxActionError):
    http_status = 409


class EntityConflict(InboxActionError):
    http_status = 409


class TargetNotFound(InboxActionError):
    http_status = 404


class ValidationError(InboxActionError):
    http_status = 400


# ── Result types ────────────────────────────────────────────────────


_CASCADE_CAP = 200


@dataclass
class ActionOutcome:
    proposal: EntityProposal
    entity_id: int | None = None
    mentions_created: int = 0
    events_created: int = 0
    status_transitions: int = 0
    cascaded_proposal_ids: list[int] = field(default_factory=list)
    cascade_truncated: bool = False
    warnings: list[str] = field(default_factory=list)


# ── Proposal loading ────────────────────────────────────────────────


async def load_proposal(db: AsyncSession, proposal_id: int) -> EntityProposal:
    proposal = (
        await db.execute(select(EntityProposal).where(EntityProposal.id == proposal_id))
    ).scalar_one_or_none()
    if proposal is None:
        raise ProposalNotFound(f"Proposal {proposal_id} not found")
    return proposal


def _require_pending(proposal: EntityProposal) -> None:
    if proposal.status != ProposalStatus.PENDING:
        raise ProposalAlreadyResolved(
            "proposal already resolved",
            payload={
                "current_status": proposal.status.value,
                "resolved_at": (
                    proposal.resolved_at.isoformat() if proposal.resolved_at else None
                ),
            },
        )


def _require_entity_type(
    proposal: EntityProposal, expected: ProposalEntityType
) -> None:
    if proposal.entity_type != expected:
        raise ValidationError(
            f"proposal is {proposal.entity_type.value}, expected {expected.value}"
        )


def _parse_payload(proposal: EntityProposal) -> dict:
    try:
        data = json.loads(proposal.payload_json or "{}")
    except json.JSONDecodeError:
        logger.warning("Invalid payload_json on proposal #%s", proposal.id)
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data


# ── Alias helpers ───────────────────────────────────────────────────


def _parse_aliases(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data if isinstance(x, (str, int))]


def _merge_aliases(
    existing: list[str],
    additions: list[str],
    canonical: str,
) -> list[str]:
    """Case-insensitive dedup; exclude canonical; preserve original casing."""
    seen: set[str] = {canonical.lower()}
    result: list[str] = []
    for a in [*existing, *additions]:
        if a is None:
            continue
        norm = _normalize_surface(str(a))
        if not norm:
            continue
        key = norm.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(norm)
    return result


# ── Blocklist helpers ───────────────────────────────────────────────


async def _upsert_blocklist(
    db: AsyncSession,
    entity_type: ProposalEntityType,
    surface_name: str,
    reason: BlocklistReason | None,
) -> EntityBlocklist:
    existing = (
        await db.execute(
            select(EntityBlocklist).where(
                EntityBlocklist.entity_type == entity_type,
                EntityBlocklist.surface_name == surface_name,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if reason is not None:
            existing.reason = reason
        return existing
    row = EntityBlocklist(
        entity_type=entity_type,
        surface_name=surface_name,
        reason=reason,
    )
    db.add(row)
    await db.flush()
    return row


# ── Same-date life_event fetch ──────────────────────────────────────


async def _fetch_date_events(
    db: AsyncSession, entry_date: datetime.date
) -> list[LifeEvent]:
    return list(
        (
            await db.execute(
                select(LifeEvent).where(LifeEvent.entry_date == entry_date)
            )
        ).scalars().all()
    )


# ── Replay ──────────────────────────────────────────────────────────


async def _replay_person_payload(
    db: AsyncSession,
    proposal: EntityProposal,
    person: Person,
) -> tuple[int, list[str]]:
    """Create `person_mentions` rows for each item in the proposal payload.

    Returns (mentions_created, warnings).
    """
    payload = _parse_payload(proposal)
    items = payload.get("mentions") or []
    warnings: list[str] = []

    if not items:
        return 0, warnings

    events = await _fetch_date_events(db, proposal.entry_date)

    existing_rows = (
        await db.execute(
            select(PersonMention).where(
                PersonMention.person_id == person.id,
                PersonMention.entry_date == proposal.entry_date,
            )
        )
    ).scalars().all()
    existing_keys = {
        (m.life_event_id, m.context_snippet or "") for m in existing_rows
    }

    mentions_created = 0
    for item in items:
        if not isinstance(item, dict):
            warnings.append("skipped non-object mention item")
            continue

        context = (item.get("interaction_context") or "")[:500] or None
        hint = item.get("linked_event_hint")
        link_id = proposal.life_event_id or _pick_linked_event(hint, events)
        key = (link_id, context or "")
        if key in existing_keys:
            continue

        db.add(
            PersonMention(
                person_id=person.id,
                entry_date=proposal.entry_date,
                life_event_id=link_id,
                context_snippet=context,
                sentiment=_coerce_sentiment(item.get("sentiment")),
            )
        )
        existing_keys.add(key)
        mentions_created += 1

    return mentions_created, warnings


async def _replay_project_payload(
    db: AsyncSession,
    proposal: EntityProposal,
    project: Project,
) -> tuple[int, int, list[str]]:
    """Create `project_events` rows and apply Q3 status inference.

    Returns (events_created, transitions, warnings). Status change is
    applied to the project in-place.
    """
    payload = _parse_payload(proposal)
    items = payload.get("events") or []
    warnings: list[str] = []

    if not items:
        return 0, 0, warnings

    events = await _fetch_date_events(db, proposal.entry_date)
    events_created = 0
    transitions = 0
    current_status = project.status

    for item in items:
        if not isinstance(item, dict):
            warnings.append("skipped non-object event item")
            continue

        event_type = _coerce_event_type(item.get("event_type"))
        if event_type is None:
            warnings.append(f"skipped unknown event_type {item.get('event_type')!r}")
            continue

        description = (item.get("description") or "").strip()
        hint = item.get("linked_event_hint")
        link_id = proposal.life_event_id or _pick_linked_event(hint, events)
        suggested = _coerce_project_status(item.get("suggested_project_status"))

        db.add(
            ProjectEvent(
                project_id=project.id,
                entry_date=proposal.entry_date,
                life_event_id=link_id,
                event_type=event_type,
                content=description,
            )
        )
        events_created += 1

        next_status = _infer_next_status(current_status, event_type, suggested)
        if next_status != current_status:
            logger.info(
                "Project %s: status %s → %s (inbox replay)",
                project.name,
                current_status.value,
                next_status.value,
            )
            current_status = next_status
            transitions += 1

    if current_status != project.status:
        project.status = current_status

    return events_created, transitions, warnings


# ── Cascade ─────────────────────────────────────────────────────────


async def _find_cascade_candidates(
    db: AsyncSession,
    entity_type: ProposalEntityType,
    surface_set: set[str],
    exclude_id: int,
) -> list[EntityProposal]:
    """Return other pending proposals whose surface matches any in `surface_set`."""
    if not surface_set:
        return []
    q = select(EntityProposal).where(
        EntityProposal.entity_type == entity_type,
        EntityProposal.status == ProposalStatus.PENDING,
        EntityProposal.id != exclude_id,
    )
    rows = (await db.execute(q)).scalars().all()
    lowered = {s.lower() for s in surface_set}
    return [r for r in rows if r.surface_name.lower() in lowered]


async def _cascade_accept_person(
    db: AsyncSession,
    outcome: ActionOutcome,
    person: Person,
    source_proposal_id: int,
) -> None:
    surfaces = {person.canonical_name, *_parse_aliases(person.aliases_json)}
    candidates = await _find_cascade_candidates(
        db, ProposalEntityType.PERSON, surfaces, source_proposal_id
    )

    if len(candidates) > _CASCADE_CAP:
        candidates = candidates[:_CASCADE_CAP]
        outcome.cascade_truncated = True

    for p in candidates:
        created, warnings = await _replay_person_payload(db, p, person)
        outcome.mentions_created += created
        outcome.warnings.extend(warnings)
        p.status = ProposalStatus.MERGED_EXISTING
        p.resolution_entity_id = person.id
        p.resolution_note = f"auto-cascaded from proposal #{source_proposal_id}"
        p.resolved_at = datetime.datetime.now(datetime.timezone.utc)
        outcome.cascaded_proposal_ids.append(p.id)


async def _cascade_accept_project(
    db: AsyncSession,
    outcome: ActionOutcome,
    project: Project,
    source_proposal_id: int,
) -> None:
    surfaces = {project.name, *_parse_aliases(project.aliases_json)}
    candidates = await _find_cascade_candidates(
        db, ProposalEntityType.PROJECT, surfaces, source_proposal_id
    )

    if len(candidates) > _CASCADE_CAP:
        candidates = candidates[:_CASCADE_CAP]
        outcome.cascade_truncated = True

    for p in candidates:
        created, transitions, warnings = await _replay_project_payload(db, p, project)
        outcome.events_created += created
        outcome.status_transitions += transitions
        outcome.warnings.extend(warnings)
        p.status = ProposalStatus.MERGED_EXISTING
        p.resolution_entity_id = project.id
        p.resolution_note = f"auto-cascaded from proposal #{source_proposal_id}"
        p.resolved_at = datetime.datetime.now(datetime.timezone.utc)
        outcome.cascaded_proposal_ids.append(p.id)


async def _cascade_silence(
    db: AsyncSession,
    outcome: ActionOutcome,
    entity_type: ProposalEntityType,
    surface: str,
    source_proposal_id: int,
    new_status: ProposalStatus,
) -> None:
    """Mark other pending proposals for the same surface as silenced."""
    candidates = await _find_cascade_candidates(
        db, entity_type, {surface}, source_proposal_id
    )
    if len(candidates) > _CASCADE_CAP:
        candidates = candidates[:_CASCADE_CAP]
        outcome.cascade_truncated = True
    for p in candidates:
        p.status = new_status
        p.resolution_note = f"auto-cascaded from proposal #{source_proposal_id}"
        p.resolved_at = datetime.datetime.now(datetime.timezone.utc)
        outcome.cascaded_proposal_ids.append(p.id)


# ── Finalization helpers ────────────────────────────────────────────


def _stamp_proposal(
    proposal: EntityProposal,
    status: ProposalStatus,
    entity_id: int | None,
    note: str | None,
) -> None:
    proposal.status = status
    proposal.resolution_entity_id = entity_id
    proposal.resolution_note = note
    proposal.resolved_at = datetime.datetime.now(datetime.timezone.utc)


# ── Person actions ──────────────────────────────────────────────────


async def confirm_new_person(
    db: AsyncSession,
    proposal_id: int,
    *,
    canonical_name: str | None,
    aliases: list[str] | None,
    relationship_type: str | None,
    notes: str | None,
) -> ActionOutcome:
    proposal = await load_proposal(db, proposal_id)
    _require_pending(proposal)
    _require_entity_type(proposal, ProposalEntityType.PERSON)

    final_name = _normalize_surface(canonical_name) or proposal.surface_name
    if not final_name:
        raise ValidationError("canonical_name resolves to empty string")

    dupe = (
        await db.execute(
            select(Person).where(Person.canonical_name.ilike(final_name))
        )
    ).scalar_one_or_none()
    if dupe is not None:
        raise EntityConflict(
            "person with canonical_name already exists",
            payload={"existing_id": dupe.id},
        )

    person = Person(
        canonical_name=final_name,
        aliases_json=json.dumps(
            _merge_aliases([], [proposal.surface_name, *(aliases or [])], final_name)
        ),
        relationship_type=relationship_type,
        notes=notes,
        first_seen_date=proposal.entry_date,
        last_seen_date=proposal.entry_date,
        mention_count=0,
    )
    db.add(person)
    await db.flush()

    outcome = ActionOutcome(proposal=proposal, entity_id=person.id)

    created, warnings = await _replay_person_payload(db, proposal, person)
    outcome.mentions_created += created
    outcome.warnings.extend(warnings)

    _stamp_proposal(
        proposal, ProposalStatus.ACCEPTED_NEW, person.id, "confirmed new"
    )

    await _cascade_accept_person(db, outcome, person, proposal.id)

    await db.flush()
    await _recompute_person_aggregates(db, person.id)
    return outcome


async def merge_person(
    db: AsyncSession,
    proposal_id: int,
    *,
    target_entity_id: int,
    add_alias: bool,
    extra_aliases: list[str] | None,
) -> ActionOutcome:
    proposal = await load_proposal(db, proposal_id)
    _require_pending(proposal)
    _require_entity_type(proposal, ProposalEntityType.PERSON)

    target = (
        await db.execute(select(Person).where(Person.id == target_entity_id))
    ).scalar_one_or_none()
    if target is None:
        raise TargetNotFound(f"person {target_entity_id} not found")

    if add_alias:
        additions = [proposal.surface_name, *(extra_aliases or [])]
        target.aliases_json = json.dumps(
            _merge_aliases(
                _parse_aliases(target.aliases_json),
                additions,
                target.canonical_name,
            )
        )

    outcome = ActionOutcome(proposal=proposal, entity_id=target.id)

    created, warnings = await _replay_person_payload(db, proposal, target)
    outcome.mentions_created += created
    outcome.warnings.extend(warnings)

    _stamp_proposal(
        proposal,
        ProposalStatus.MERGED_EXISTING,
        target.id,
        f"merged into {target.canonical_name}",
    )

    await _cascade_accept_person(db, outcome, target, proposal.id)

    await db.flush()
    await _recompute_person_aggregates(db, target.id)
    return outcome


async def dismiss_proposal(
    db: AsyncSession,
    proposal_id: int,
    *,
    note: str | None,
) -> ActionOutcome:
    proposal = await load_proposal(db, proposal_id)
    _require_pending(proposal)
    _stamp_proposal(proposal, ProposalStatus.DISMISSED, None, note)
    return ActionOutcome(proposal=proposal)


async def blocklist_proposal(
    db: AsyncSession,
    proposal_id: int,
    *,
    reason: BlocklistReason,
    note: str | None,
    cascade_pending: bool,
) -> ActionOutcome:
    proposal = await load_proposal(db, proposal_id)
    _require_pending(proposal)

    await _upsert_blocklist(db, proposal.entity_type, proposal.surface_name, reason)

    _stamp_proposal(
        proposal,
        ProposalStatus.BLOCKED,
        None,
        note or f"blocklisted ({reason.value})",
    )

    outcome = ActionOutcome(proposal=proposal)

    if cascade_pending:
        await _cascade_silence(
            db,
            outcome,
            proposal.entity_type,
            proposal.surface_name,
            proposal.id,
            ProposalStatus.BLOCKED,
        )

    return outcome


# ── Project actions ─────────────────────────────────────────────────


async def confirm_new_project(
    db: AsyncSession,
    proposal_id: int,
    *,
    name: str | None,
    aliases: list[str] | None,
    category: str | None,
    status: ProjectStatus | None,
    description: str | None,
    target_date: datetime.date | None,
) -> ActionOutcome:
    proposal = await load_proposal(db, proposal_id)
    _require_pending(proposal)
    _require_entity_type(proposal, ProposalEntityType.PROJECT)

    final_name = _normalize_surface(name) or proposal.surface_name
    if not final_name:
        raise ValidationError("name resolves to empty string")

    dupe = (
        await db.execute(select(Project).where(Project.name.ilike(final_name)))
    ).scalar_one_or_none()
    if dupe is not None:
        raise EntityConflict(
            "project with name already exists",
            payload={"existing_id": dupe.id},
        )

    project = Project(
        name=final_name,
        aliases_json=json.dumps(
            _merge_aliases([], [proposal.surface_name, *(aliases or [])], final_name)
        ),
        category=category,
        status=status or ProjectStatus.ACTIVE,
        description=description,
        target_date=target_date,
        first_seen_date=proposal.entry_date,
        last_seen_date=proposal.entry_date,
        mention_count=0,
    )
    db.add(project)
    await db.flush()

    outcome = ActionOutcome(proposal=proposal, entity_id=project.id)

    created, transitions, warnings = await _replay_project_payload(db, proposal, project)
    outcome.events_created += created
    outcome.status_transitions += transitions
    outcome.warnings.extend(warnings)

    _stamp_proposal(
        proposal, ProposalStatus.ACCEPTED_NEW, project.id, "confirmed new"
    )

    await _cascade_accept_project(db, outcome, project, proposal.id)

    await db.flush()
    await _recompute_project_aggregates(db, project.id)
    return outcome


async def merge_project(
    db: AsyncSession,
    proposal_id: int,
    *,
    target_entity_id: int,
    add_alias: bool,
    extra_aliases: list[str] | None,
) -> ActionOutcome:
    proposal = await load_proposal(db, proposal_id)
    _require_pending(proposal)
    _require_entity_type(proposal, ProposalEntityType.PROJECT)

    target = (
        await db.execute(select(Project).where(Project.id == target_entity_id))
    ).scalar_one_or_none()
    if target is None:
        raise TargetNotFound(f"project {target_entity_id} not found")

    if add_alias:
        additions = [proposal.surface_name, *(extra_aliases or [])]
        target.aliases_json = json.dumps(
            _merge_aliases(
                _parse_aliases(target.aliases_json),
                additions,
                target.name,
            )
        )

    outcome = ActionOutcome(proposal=proposal, entity_id=target.id)

    created, transitions, warnings = await _replay_project_payload(db, proposal, target)
    outcome.events_created += created
    outcome.status_transitions += transitions
    outcome.warnings.extend(warnings)

    _stamp_proposal(
        proposal,
        ProposalStatus.MERGED_EXISTING,
        target.id,
        f"merged into {target.name}",
    )

    await _cascade_accept_project(db, outcome, target, proposal.id)

    await db.flush()
    await _recompute_project_aggregates(db, target.id)
    return outcome


async def reject_project(
    db: AsyncSession,
    proposal_id: int,
    *,
    mode: str,
    note: str | None,
) -> ActionOutcome:
    """`mode` is one of {'dismiss', 'blocklist'}."""
    if mode not in ("dismiss", "blocklist"):
        raise ValidationError(f"invalid reject mode {mode!r}")

    proposal = await load_proposal(db, proposal_id)
    _require_pending(proposal)
    _require_entity_type(proposal, ProposalEntityType.PROJECT)

    if mode == "blocklist":
        await _upsert_blocklist(
            db,
            ProposalEntityType.PROJECT,
            proposal.surface_name,
            BlocklistReason.MANUAL_BLOCK,
        )

    _stamp_proposal(
        proposal,
        ProposalStatus.REJECTED,
        None,
        note or f"rejected ({mode})",
    )

    outcome = ActionOutcome(proposal=proposal)

    if mode == "blocklist":
        await _cascade_silence(
            db,
            outcome,
            ProposalEntityType.PROJECT,
            proposal.surface_name,
            proposal.id,
            ProposalStatus.REJECTED,
        )

    return outcome
