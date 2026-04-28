"""Admin / operations HTTP surface — Step 6.

Thin adapter over `app.services.backfill` and `app.services.embeddings`.
Single-user assumption holds; concurrent runs are serialized via a
process-local `asyncio.Lock`.
"""

from __future__ import annotations

import asyncio
import dataclasses
import datetime
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.journal_entry import JournalEntry
from app.services.backfill import (
    BackfillOptions,
    BackfillReport,
    BackfillSelector,
    DryRunEntryResult,
    _db_path,
    _snapshot_database,
    load_last_audit_summary,
    run_backfill,
)
from app.services.embeddings import embed_journals, purge_entry_embeddings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/operations", tags=["operations"])

_BACKFILL_LOCK = asyncio.Lock()


# ── Request schemas ─────────────────────────────────────────────────


class BackfillRequest(BaseModel):
    date_from: datetime.date | None = None
    date_to: datetime.date | None = None
    entry_dates: list[datetime.date] | None = None
    only_unprocessed: bool = False
    max_shredder_version: str | None = None
    force: bool = False
    limit: int | None = None
    dry_run: bool = False
    rate_limit_seconds: float = Field(default=1.0, ge=0)
    snapshot_db: bool = True
    purge_embeddings: bool = False
    note: str | None = None


class ReembedRequest(BaseModel):
    date_from: datetime.date | None = None
    date_to: datetime.date | None = None
    entry_dates: list[datetime.date] | None = None
    purge_first: bool = True


# ── Response schemas ────────────────────────────────────────────────


class EntryResultPayload(BaseModel):
    entry_date: str
    events_extracted: int
    reflections_extracted: int
    people_mentions_extracted: int
    project_events_extracted: int
    person_mentions_created: int
    project_events_created: int
    person_proposals_created: int
    project_proposals_created: int
    project_status_transitions: int
    error: str | None = None


class DryRunEntryPayload(BaseModel):
    entry_date: str
    would_run: bool
    current_shredder_version: str | None = None
    note: str


class BackfillReportPayload(BaseModel):
    started_at: datetime.datetime
    finished_at: datetime.datetime | None = None
    selector: dict[str, Any]
    options: dict[str, Any]
    snapshot_path: str | None = None
    audit_log_path: str | None = None
    total_selected: int
    processed: int
    failed: int
    skipped_by_version: int
    person_mentions_created: int
    project_events_created: int
    person_proposals_created: int
    project_proposals_created: int
    project_status_transitions: int
    embeddings_purged_dates: list[datetime.date]
    entries: list[EntryResultPayload]
    dry_run_entries: list[DryRunEntryPayload]
    errors: list[str]


class ReembedResponse(BaseModel):
    entries_processed: int
    chunks_created: int
    skipped: int
    purged_dates: list[datetime.date]


class SnapshotResponse(BaseModel):
    snapshot_path: str
    bytes_copied: int
    created_at: datetime.datetime


class LastBackfillResponse(BaseModel):
    audit_log_path: str
    entry_count: int
    header: dict[str, Any] | None
    summary: dict[str, Any]
    match_rate: dict[str, float | None]


# ── Serialization helpers ───────────────────────────────────────────


def _selector_to_dict(s: BackfillSelector) -> dict[str, Any]:
    d = dataclasses.asdict(s)
    if d.get("entry_dates"):
        d["entry_dates"] = [
            dt.isoformat() if isinstance(dt, datetime.date) else dt
            for dt in d["entry_dates"]
        ]
    for k in ("date_from", "date_to"):
        if isinstance(d.get(k), datetime.date):
            d[k] = d[k].isoformat()
    return d


def _options_to_dict(o: BackfillOptions) -> dict[str, Any]:
    d = dataclasses.asdict(o)
    if isinstance(d.get("audit_log_path"), Path):
        d["audit_log_path"] = str(d["audit_log_path"])
    return d


def _serialize_report(report: BackfillReport) -> BackfillReportPayload:
    return BackfillReportPayload(
        started_at=report.started_at,
        finished_at=report.finished_at,
        selector=_selector_to_dict(report.selector),
        options=_options_to_dict(report.options),
        snapshot_path=str(report.snapshot_path) if report.snapshot_path else None,
        audit_log_path=str(report.audit_log_path) if report.audit_log_path else None,
        total_selected=report.total_selected,
        processed=report.processed,
        failed=report.failed,
        skipped_by_version=report.skipped_by_version,
        person_mentions_created=report.person_mentions_created,
        project_events_created=report.project_events_created,
        person_proposals_created=report.person_proposals_created,
        project_proposals_created=report.project_proposals_created,
        project_status_transitions=report.project_status_transitions,
        embeddings_purged_dates=report.embeddings_purged_dates,
        entries=[
            EntryResultPayload(
                entry_date=e.entry_date,
                events_extracted=e.events_extracted,
                reflections_extracted=e.reflections_extracted,
                people_mentions_extracted=e.people_mentions_extracted,
                project_events_extracted=e.project_events_extracted,
                person_mentions_created=e.person_mentions_created,
                project_events_created=e.project_events_created,
                person_proposals_created=e.person_proposals_created,
                project_proposals_created=e.project_proposals_created,
                project_status_transitions=e.project_status_transitions,
                error=e.error,
            )
            for e in report.entries
        ],
        dry_run_entries=[
            DryRunEntryPayload(
                entry_date=d.entry_date,
                would_run=d.would_run,
                current_shredder_version=d.current_shredder_version,
                note=d.note,
            )
            for d in report.dry_run_entries
        ],
        errors=report.errors,
    )


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/backfill", response_model=BackfillReportPayload)
async def operations_backfill(
    body: BackfillRequest,
    db: AsyncSession = Depends(get_db),
):
    if _BACKFILL_LOCK.locked():
        raise HTTPException(status_code=409, detail="backfill already running")

    selector = BackfillSelector(
        date_from=body.date_from,
        date_to=body.date_to,
        entry_dates=body.entry_dates,
        only_unprocessed=body.only_unprocessed,
        max_shredder_version=body.max_shredder_version,
        force=body.force,
        limit=body.limit,
    )
    options = BackfillOptions(
        dry_run=body.dry_run,
        rate_limit_seconds=body.rate_limit_seconds,
        snapshot_db=body.snapshot_db,
        purge_embeddings=body.purge_embeddings,
        note=body.note,
    )

    async with _BACKFILL_LOCK:
        try:
            report = await run_backfill(db, selector, options)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Backfill aborted unexpectedly")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return _serialize_report(report)


@router.get("/backfill/last", response_model=LastBackfillResponse)
async def operations_backfill_last():
    summary = load_last_audit_summary()
    if summary is None:
        raise HTTPException(status_code=404, detail="no backfill audit logs available")
    return LastBackfillResponse(**summary)


@router.post("/re-embed", response_model=ReembedResponse)
async def operations_reembed(
    body: ReembedRequest,
    db: AsyncSession = Depends(get_db),
):
    if (
        body.date_from is not None
        and body.date_to is not None
        and body.date_from > body.date_to
    ):
        raise HTTPException(status_code=400, detail="date_from must be <= date_to")

    q = select(JournalEntry.entry_date)
    if body.entry_dates is not None:
        if not body.entry_dates:
            raise HTTPException(status_code=400, detail="entry_dates must be non-empty")
        q = q.where(JournalEntry.entry_date.in_(body.entry_dates))
    else:
        if body.date_from is not None:
            q = q.where(JournalEntry.entry_date >= body.date_from)
        if body.date_to is not None:
            q = q.where(JournalEntry.entry_date <= body.date_to)

    target_dates: list[datetime.date] = list(
        (await db.execute(q.order_by(JournalEntry.entry_date.asc()))).scalars().all()
    )

    purged: list[datetime.date] = []
    if body.purge_first:
        for entry_date in target_dates:
            purged_count = await purge_entry_embeddings(db, entry_date)
            if purged_count:
                purged.append(entry_date)
        if purged:
            await db.commit()

    embed_result = await embed_journals(db)

    return ReembedResponse(
        entries_processed=embed_result.entries_processed,
        chunks_created=embed_result.chunks_created,
        skipped=embed_result.skipped,
        purged_dates=purged,
    )


@router.post("/snapshot", response_model=SnapshotResponse)
async def operations_snapshot():
    src = _db_path()
    if src is None or not src.exists():
        raise HTTPException(
            status_code=400,
            detail="DATABASE_URL is not a file-backed SQLite path; cannot snapshot",
        )

    timestamp = datetime.datetime.now(datetime.timezone.utc)
    try:
        dest = _snapshot_database(timestamp)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"snapshot failed: {exc}") from exc

    if dest is None:
        raise HTTPException(status_code=500, detail="snapshot returned no path")

    return SnapshotResponse(
        snapshot_path=str(dest),
        bytes_copied=dest.stat().st_size,
        created_at=timestamp,
    )
