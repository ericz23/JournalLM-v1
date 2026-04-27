"""Entity inbox API — manage `entity_proposals` + `entity_blocklist`."""

from __future__ import annotations

import datetime
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entity_blocklist import BlocklistReason, EntityBlocklist
from app.models.entity_proposal import (
    EntityProposal,
    ProposalEntityType,
    ProposalStatus,
)
from app.models.projects import ProjectStatus
from app.services import entity_inbox_service as inbox

router = APIRouter(prefix="/entity-inbox", tags=["entity-inbox"])


# ── Shared schemas ──────────────────────────────────────────────────


class CandidateMatch(BaseModel):
    entity_id: int
    canonical_name: str
    score: float
    signals: dict


class ProposalSummary(BaseModel):
    id: int
    entity_type: Literal["person", "project"]
    status: Literal[
        "pending", "accepted_new", "merged_existing", "dismissed", "rejected", "blocked"
    ]
    surface_name: str
    entry_date: datetime.date
    life_event_id: int | None
    created_at: datetime.datetime
    resolved_at: datetime.datetime | None


class ProposalDetail(ProposalSummary):
    payload: dict
    candidate_matches: list[CandidateMatch]
    resolution_entity_id: int | None
    resolution_note: str | None


class ActionResult(BaseModel):
    proposal: ProposalDetail
    entity_id: int | None = None
    mentions_created: int = 0
    events_created: int = 0
    status_transitions: int = 0
    cascaded_proposal_ids: list[int] = []
    cascade_truncated: bool = False
    warnings: list[str] = []


class BlocklistEntrySchema(BaseModel):
    id: int
    entity_type: Literal["person", "project"]
    surface_name: str
    reason: Literal["manual_block", "system_noise"] | None
    created_at: datetime.datetime


class SummaryResponse(BaseModel):
    pending_person: int
    pending_project: int
    total_pending: int
    oldest_pending_entry_date: datetime.date | None


class ProposalListResponse(BaseModel):
    total: int
    items: list[ProposalSummary]


# ── Action body schemas ─────────────────────────────────────────────


class ConfirmNewPersonBody(BaseModel):
    canonical_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    relationship_type: str | None = None
    notes: str | None = None


class MergePersonBody(BaseModel):
    target_entity_id: int
    add_alias: bool = True
    extra_aliases: list[str] = Field(default_factory=list)


class DismissBody(BaseModel):
    note: str | None = None


class BlocklistBody(BaseModel):
    reason: Literal["manual_block", "system_noise"] = "manual_block"
    note: str | None = None
    cascade_pending: bool = True


class ConfirmNewProjectBody(BaseModel):
    name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    category: str | None = None
    status: Literal["ACTIVE", "PAUSED", "COMPLETED", "ABANDONED"] | None = None
    description: str | None = None
    target_date: datetime.date | None = None


class MergeProjectBody(BaseModel):
    target_entity_id: int
    add_alias: bool = True
    extra_aliases: list[str] = Field(default_factory=list)


class RejectProjectBody(BaseModel):
    mode: Literal["dismiss", "blocklist"] = "dismiss"
    note: str | None = None


# ── Serialization helpers ───────────────────────────────────────────


def _parse_json(raw: str | None, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _to_summary(p: EntityProposal) -> ProposalSummary:
    return ProposalSummary(
        id=p.id,
        entity_type=p.entity_type.value,
        status=p.status.value,
        surface_name=p.surface_name,
        entry_date=p.entry_date,
        life_event_id=p.life_event_id,
        created_at=p.created_at,
        resolved_at=p.resolved_at,
    )


def _to_detail(p: EntityProposal) -> ProposalDetail:
    payload = _parse_json(p.payload_json, {})
    candidates_raw = _parse_json(p.candidate_matches_json, [])
    candidates = [
        CandidateMatch(
            entity_id=int(c.get("entity_id")),
            canonical_name=str(c.get("canonical_name", "")),
            score=float(c.get("score", 0.0)),
            signals=c.get("signals") or {},
        )
        for c in candidates_raw
        if isinstance(c, dict) and "entity_id" in c
    ]
    return ProposalDetail(
        id=p.id,
        entity_type=p.entity_type.value,
        status=p.status.value,
        surface_name=p.surface_name,
        entry_date=p.entry_date,
        life_event_id=p.life_event_id,
        created_at=p.created_at,
        resolved_at=p.resolved_at,
        payload=payload if isinstance(payload, dict) else {},
        candidate_matches=candidates,
        resolution_entity_id=p.resolution_entity_id,
        resolution_note=p.resolution_note,
    )


def _outcome_to_response(outcome: inbox.ActionOutcome) -> ActionResult:
    return ActionResult(
        proposal=_to_detail(outcome.proposal),
        entity_id=outcome.entity_id,
        mentions_created=outcome.mentions_created,
        events_created=outcome.events_created,
        status_transitions=outcome.status_transitions,
        cascaded_proposal_ids=outcome.cascaded_proposal_ids,
        cascade_truncated=outcome.cascade_truncated,
        warnings=outcome.warnings,
    )


async def _run_action(
    db: AsyncSession,
    coro,
) -> ActionResult:
    """Execute an inbox service coroutine, commit on success, map errors to HTTP."""
    try:
        outcome = await coro
    except inbox.InboxActionError as exc:
        await db.rollback()
        detail = {"detail": exc.message, **exc.payload}
        raise HTTPException(status_code=exc.http_status, detail=detail) from exc
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    await db.refresh(outcome.proposal)
    return _outcome_to_response(outcome)


# ── Read endpoints ──────────────────────────────────────────────────


@router.get("/proposals", response_model=ProposalListResponse)
async def list_proposals(
    status: list[str] = Query(default=["pending"]),
    entity_type: Literal["person", "project"] | None = None,
    entry_date_from: datetime.date | None = None,
    entry_date_to: datetime.date | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    valid_statuses = {s.value for s in ProposalStatus}
    filter_statuses = [s for s in status if s in valid_statuses]
    if not filter_statuses:
        raise HTTPException(400, "no valid status values provided")

    base = select(EntityProposal).where(
        EntityProposal.status.in_([ProposalStatus(s) for s in filter_statuses])
    )
    if entity_type is not None:
        base = base.where(EntityProposal.entity_type == ProposalEntityType(entity_type))
    if entry_date_from is not None:
        base = base.where(EntityProposal.entry_date >= entry_date_from)
    if entry_date_to is not None:
        base = base.where(EntityProposal.entry_date <= entry_date_to)
    if search:
        base = base.where(EntityProposal.surface_name.ilike(f"%{search}%"))

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar() or 0

    rows = (
        await db.execute(
            base.order_by(
                EntityProposal.entry_date.desc(),
                EntityProposal.created_at.desc(),
                EntityProposal.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    return ProposalListResponse(total=total, items=[_to_summary(r) for r in rows])


@router.get("/proposals/summary", response_model=SummaryResponse)
async def proposals_summary(db: AsyncSession = Depends(get_db)):
    pending_person = (
        await db.execute(
            select(func.count(EntityProposal.id)).where(
                EntityProposal.status == ProposalStatus.PENDING,
                EntityProposal.entity_type == ProposalEntityType.PERSON,
            )
        )
    ).scalar() or 0
    pending_project = (
        await db.execute(
            select(func.count(EntityProposal.id)).where(
                EntityProposal.status == ProposalStatus.PENDING,
                EntityProposal.entity_type == ProposalEntityType.PROJECT,
            )
        )
    ).scalar() or 0
    oldest = (
        await db.execute(
            select(func.min(EntityProposal.entry_date)).where(
                EntityProposal.status == ProposalStatus.PENDING
            )
        )
    ).scalar()

    return SummaryResponse(
        pending_person=pending_person,
        pending_project=pending_project,
        total_pending=pending_person + pending_project,
        oldest_pending_entry_date=oldest,
    )


@router.get("/proposals/{proposal_id}", response_model=ProposalDetail)
async def get_proposal(proposal_id: int, db: AsyncSession = Depends(get_db)):
    proposal = (
        await db.execute(
            select(EntityProposal).where(EntityProposal.id == proposal_id)
        )
    ).scalar_one_or_none()
    if proposal is None:
        raise HTTPException(404, f"proposal {proposal_id} not found")
    return _to_detail(proposal)


@router.get("/blocklist", response_model=list[BlocklistEntrySchema])
async def list_blocklist(
    entity_type: Literal["person", "project"] | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(EntityBlocklist)
    if entity_type is not None:
        q = q.where(EntityBlocklist.entity_type == ProposalEntityType(entity_type))
    rows = (
        await db.execute(
            q.order_by(EntityBlocklist.entity_type, EntityBlocklist.surface_name)
        )
    ).scalars().all()
    return [
        BlocklistEntrySchema(
            id=r.id,
            entity_type=r.entity_type.value,
            surface_name=r.surface_name,
            reason=r.reason.value if r.reason is not None else None,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.delete("/blocklist/{blocklist_id}", status_code=204)
async def delete_blocklist(
    blocklist_id: int, db: AsyncSession = Depends(get_db)
):
    row = (
        await db.execute(
            select(EntityBlocklist).where(EntityBlocklist.id == blocklist_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"blocklist entry {blocklist_id} not found")
    await db.delete(row)
    await db.commit()
    return None


# ── Person actions ──────────────────────────────────────────────────


@router.post(
    "/proposals/{proposal_id}/actions/confirm-new-person",
    response_model=ActionResult,
)
async def action_confirm_new_person(
    proposal_id: int,
    body: ConfirmNewPersonBody,
    db: AsyncSession = Depends(get_db),
):
    return await _run_action(
        db,
        inbox.confirm_new_person(
            db,
            proposal_id,
            canonical_name=body.canonical_name,
            aliases=body.aliases,
            relationship_type=body.relationship_type,
            notes=body.notes,
        ),
    )


@router.post(
    "/proposals/{proposal_id}/actions/merge-person",
    response_model=ActionResult,
)
async def action_merge_person(
    proposal_id: int,
    body: MergePersonBody,
    db: AsyncSession = Depends(get_db),
):
    return await _run_action(
        db,
        inbox.merge_person(
            db,
            proposal_id,
            target_entity_id=body.target_entity_id,
            add_alias=body.add_alias,
            extra_aliases=body.extra_aliases,
        ),
    )


# ── Project actions ─────────────────────────────────────────────────


@router.post(
    "/proposals/{proposal_id}/actions/confirm-new-project",
    response_model=ActionResult,
)
async def action_confirm_new_project(
    proposal_id: int,
    body: ConfirmNewProjectBody,
    db: AsyncSession = Depends(get_db),
):
    status = ProjectStatus(body.status) if body.status is not None else None
    return await _run_action(
        db,
        inbox.confirm_new_project(
            db,
            proposal_id,
            name=body.name,
            aliases=body.aliases,
            category=body.category,
            status=status,
            description=body.description,
            target_date=body.target_date,
        ),
    )


@router.post(
    "/proposals/{proposal_id}/actions/merge-project",
    response_model=ActionResult,
)
async def action_merge_project(
    proposal_id: int,
    body: MergeProjectBody,
    db: AsyncSession = Depends(get_db),
):
    return await _run_action(
        db,
        inbox.merge_project(
            db,
            proposal_id,
            target_entity_id=body.target_entity_id,
            add_alias=body.add_alias,
            extra_aliases=body.extra_aliases,
        ),
    )


@router.post(
    "/proposals/{proposal_id}/actions/reject-project",
    response_model=ActionResult,
)
async def action_reject_project(
    proposal_id: int,
    body: RejectProjectBody,
    db: AsyncSession = Depends(get_db),
):
    return await _run_action(
        db,
        inbox.reject_project(
            db,
            proposal_id,
            mode=body.mode,
            note=body.note,
        ),
    )


# ── Shared actions (work for both types) ────────────────────────────


@router.post(
    "/proposals/{proposal_id}/actions/dismiss",
    response_model=ActionResult,
)
async def action_dismiss(
    proposal_id: int,
    body: DismissBody,
    db: AsyncSession = Depends(get_db),
):
    return await _run_action(
        db,
        inbox.dismiss_proposal(db, proposal_id, note=body.note),
    )


@router.post(
    "/proposals/{proposal_id}/actions/blocklist",
    response_model=ActionResult,
)
async def action_blocklist(
    proposal_id: int,
    body: BlocklistBody,
    db: AsyncSession = Depends(get_db),
):
    reason = BlocklistReason(body.reason)
    return await _run_action(
        db,
        inbox.blocklist_proposal(
            db,
            proposal_id,
            reason=reason,
            note=body.note,
            cascade_pending=body.cascade_pending,
        ),
    )
