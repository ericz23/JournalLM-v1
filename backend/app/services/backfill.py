"""Backfill service — Step 6.

Drives Steps 2 + 3 across a selectable batch of journal entries with
Q4 full re-extract semantics. Each entry runs in its own transaction
(`process_single_entry` from the shredder), so a failure on one date
does not abort the rest of the batch.

The HTTP route in `app.routes.operations` and the CLI in
`backend.scripts.backfill` are thin adapters around `run_backfill`.
"""

from __future__ import annotations

import asyncio
import dataclasses
import datetime
import io
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.journal_entry import JournalEntry
from app.services.embeddings import purge_entry_embeddings
from app.services.shredder import (
    EntryResult,
    SHREDDER_VERSION,
    _build_client,
    process_single_entry,
)

logger = logging.getLogger(__name__)


# ── Selector + options + report ─────────────────────────────────────


@dataclass
class BackfillSelector:
    """Filter rules for picking which `JournalEntry` rows to process."""

    date_from: datetime.date | None = None
    date_to: datetime.date | None = None
    entry_dates: list[datetime.date] | None = None
    only_unprocessed: bool = False
    max_shredder_version: str | None = None
    force: bool = False
    limit: int | None = None


@dataclass
class BackfillOptions:
    """How to run a batch."""

    dry_run: bool = False
    rate_limit_seconds: float = 1.0
    snapshot_db: bool = True
    purge_embeddings: bool = False
    audit_log_path: Path | None = None
    note: str | None = None


@dataclass
class DryRunEntryResult:
    entry_date: str
    would_run: bool
    current_shredder_version: str | None
    note: str


@dataclass
class BackfillReport:
    started_at: datetime.datetime
    finished_at: datetime.datetime | None = None
    selector: BackfillSelector = field(default_factory=BackfillSelector)
    options: BackfillOptions = field(default_factory=BackfillOptions)
    snapshot_path: Path | None = None
    audit_log_path: Path | None = None
    total_selected: int = 0
    processed: int = 0
    failed: int = 0
    skipped_by_version: int = 0
    person_mentions_created: int = 0
    project_events_created: int = 0
    person_proposals_created: int = 0
    project_proposals_created: int = 0
    project_status_transitions: int = 0
    embeddings_purged_dates: list[datetime.date] = field(default_factory=list)
    entries: list[EntryResult] = field(default_factory=list)
    dry_run_entries: list[DryRunEntryResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ── Version comparison ──────────────────────────────────────────────


def _parse_version(v: str | None) -> tuple[int, ...]:
    """Parse 'v2.10' → (2, 10). Treats None / empty / 'v0' identically."""
    if v is None:
        return (0,)
    cleaned = v.strip().lstrip("vV")
    if not cleaned:
        return (0,)
    parts: list[int] = []
    for seg in cleaned.split("."):
        try:
            parts.append(int(seg))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def _compare_version(a: str | None, b: str | None) -> int:
    """Return -1/0/1 comparing two shredder version strings numerically."""
    pa, pb = _parse_version(a), _parse_version(b)
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0


# ── Selector resolution ─────────────────────────────────────────────


def _validate_selector(selector: BackfillSelector) -> None:
    if selector.entry_dates is not None and len(selector.entry_dates) == 0:
        raise ValueError("entry_dates must be non-empty when provided")
    if (
        selector.date_from is not None
        and selector.date_to is not None
        and selector.date_from > selector.date_to
    ):
        raise ValueError("date_from must be <= date_to")
    if selector.limit is not None and selector.limit <= 0:
        raise ValueError("limit must be positive when provided")


async def _select_entries(
    db: AsyncSession,
    selector: BackfillSelector,
) -> tuple[list[JournalEntry], int]:
    """Resolve the candidate entry list per §5.1.

    Returns (selected_entries, skipped_by_version_count).
    """
    q = select(JournalEntry)

    if selector.entry_dates is not None:
        q = q.where(JournalEntry.entry_date.in_(selector.entry_dates))
    else:
        if selector.date_from is not None:
            q = q.where(JournalEntry.entry_date >= selector.date_from)
        if selector.date_to is not None:
            q = q.where(JournalEntry.entry_date <= selector.date_to)

    if selector.only_unprocessed:
        q = q.where(JournalEntry.processed_at.is_(None))

    q = q.order_by(JournalEntry.entry_date.asc())

    rows = (await db.execute(q)).scalars().all()
    rows_list = list(rows)

    skipped_by_version = 0
    if selector.max_shredder_version is not None and not selector.force:
        kept: list[JournalEntry] = []
        for row in rows_list:
            cmp = _compare_version(row.shredder_version, selector.max_shredder_version)
            logger.debug(
                "version cmp date=%s row=%s max=%s -> %d",
                row.entry_date,
                row.shredder_version,
                selector.max_shredder_version,
                cmp,
            )
            if cmp >= 0:
                skipped_by_version += 1
                continue
            kept.append(row)
        rows_list = kept
    elif selector.max_shredder_version is not None and selector.force:
        logger.info(
            "max_shredder_version=%s ignored because force=True",
            selector.max_shredder_version,
        )

    if selector.limit is not None:
        rows_list = rows_list[: selector.limit]

    return rows_list, skipped_by_version


# ── Snapshot + audit log helpers ────────────────────────────────────


def _db_path() -> Path | None:
    """Return the on-disk SQLite path, or None if DATABASE_URL is non-file."""
    url = settings.DATABASE_URL
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            return Path(url[len(prefix):])
    return None


def _snapshot_database(timestamp: datetime.datetime) -> Path | None:
    """Copy the live SQLite file to a `*.backup-<ts>` sibling. Returns the new path."""
    src = _db_path()
    if src is None or not src.exists():
        logger.warning("Snapshot skipped — database is not a file path (%s)", settings.DATABASE_URL)
        return None

    snapshot_dir = (
        Path(settings.BACKFILL_SNAPSHOT_DIR)
        if settings.BACKFILL_SNAPSHOT_DIR
        else src.parent
    )
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    suffix = timestamp.strftime("%Y%m%d-%H%M%S")
    dest = snapshot_dir / f"{src.name}.backup-{suffix}"
    shutil.copy2(src, dest)
    logger.info("Snapshot created at %s (%d bytes)", dest, dest.stat().st_size)
    return dest


def _default_audit_log_path(timestamp: datetime.datetime) -> Path:
    log_dir = Path(settings.BACKFILL_LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    suffix = timestamp.strftime("%Y%m%d-%H%M%S")
    return log_dir / f"{suffix}.jsonl"


def _json_default(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _write_jsonl(handle: io.TextIOBase, payload: dict) -> None:
    handle.write(json.dumps(payload, default=_json_default))
    handle.write("\n")
    handle.flush()


# ── Main entry point ────────────────────────────────────────────────


async def run_backfill(
    db: AsyncSession,
    selector: BackfillSelector,
    options: BackfillOptions | None = None,
) -> BackfillReport:
    options = options or BackfillOptions()
    _validate_selector(selector)

    started_at = datetime.datetime.now(datetime.timezone.utc)
    report = BackfillReport(
        started_at=started_at,
        selector=selector,
        options=options,
    )

    candidates, skipped_by_version = await _select_entries(db, selector)
    report.skipped_by_version = skipped_by_version
    report.total_selected = len(candidates)

    if not candidates:
        report.finished_at = datetime.datetime.now(datetime.timezone.utc)
        logger.info(
            "backfill done selected=0 skipped_version=%d (no work to do)",
            skipped_by_version,
        )
        return report

    audit_handle: io.TextIOBase | None = None
    if not options.dry_run:
        audit_path = options.audit_log_path or _default_audit_log_path(started_at)
        try:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_handle = audit_path.open("w", encoding="utf-8")
            report.audit_log_path = audit_path
            _write_jsonl(
                audit_handle,
                {
                    "type": "header",
                    "started_at": started_at,
                    "selector": dataclasses.asdict(selector),
                    "options": {
                        **dataclasses.asdict(options),
                        # asdict serialises Path; keep audit_log_path as string
                        "audit_log_path": (
                            str(options.audit_log_path)
                            if options.audit_log_path is not None
                            else None
                        ),
                    },
                    "note": options.note,
                    "shredder_version_target": SHREDDER_VERSION,
                },
            )
        except OSError as exc:
            logger.warning("Failed to open audit log %s: %s", audit_path, exc)
            audit_handle = None
            report.audit_log_path = None
            report.errors.append(f"audit_log_open: {exc}")

    if not options.dry_run and options.snapshot_db:
        try:
            report.snapshot_path = _snapshot_database(started_at)
        except OSError as exc:
            logger.error("Snapshot failed: %s", exc)
            report.errors.append(f"snapshot: {exc}")
            report.finished_at = datetime.datetime.now(datetime.timezone.utc)
            if audit_handle is not None:
                _write_jsonl(audit_handle, {"type": "abort", "reason": f"snapshot failed: {exc}"})
                audit_handle.close()
            raise

    client = None
    if not options.dry_run:
        try:
            client = _build_client()
        except RuntimeError as exc:
            logger.error("Cannot build Gemini client: %s", exc)
            report.errors.append(f"client: {exc}")
            report.finished_at = datetime.datetime.now(datetime.timezone.utc)
            if audit_handle is not None:
                _write_jsonl(audit_handle, {"type": "abort", "reason": str(exc)})
                audit_handle.close()
            return report

    for i, entry in enumerate(candidates):
        if options.dry_run:
            dry = DryRunEntryResult(
                entry_date=entry.entry_date.isoformat(),
                would_run=True,
                current_shredder_version=entry.shredder_version,
                note=("force" if selector.force else "version_filter_match"),
            )
            report.dry_run_entries.append(dry)
            logger.info(
                "backfill dry-run date=%s current_version=%s",
                entry.entry_date,
                entry.shredder_version,
            )
            continue

        if options.purge_embeddings:
            try:
                purged = await purge_entry_embeddings(db, entry.entry_date)
                await db.commit()
                if purged:
                    report.embeddings_purged_dates.append(entry.entry_date)
            except Exception as exc:
                await db.rollback()
                logger.warning("purge_embeddings failed for %s: %s", entry.entry_date, exc)
                report.errors.append(f"{entry.entry_date}: purge_embeddings: {exc}")

        per_entry_started = datetime.datetime.now(datetime.timezone.utc)
        result = await process_single_entry(db, entry, client)
        per_entry_ms = int(
            (datetime.datetime.now(datetime.timezone.utc) - per_entry_started).total_seconds()
            * 1000
        )

        report.entries.append(result)
        if result.error:
            report.failed += 1
            report.errors.append(f"{result.entry_date}: {result.error}")
            logger.warning(
                "backfill date=%s FAILED error=%s ms=%d",
                result.entry_date,
                result.error,
                per_entry_ms,
            )
        else:
            report.processed += 1
            report.person_mentions_created += result.person_mentions_created
            report.project_events_created += result.project_events_created
            report.person_proposals_created += result.person_proposals_created
            report.project_proposals_created += result.project_proposals_created
            report.project_status_transitions += result.project_status_transitions
            logger.info(
                "backfill date=%s events=%d reflections=%d mentions_created=%d "
                "events_created=%d proposals=%d status_transitions=%d ms=%d",
                result.entry_date,
                result.events_extracted,
                result.reflections_extracted,
                result.person_mentions_created,
                result.project_events_created,
                result.person_proposals_created + result.project_proposals_created,
                result.project_status_transitions,
                per_entry_ms,
            )

        if audit_handle is not None:
            try:
                _write_jsonl(
                    audit_handle,
                    {
                        "type": "entry",
                        "entry_date": result.entry_date,
                        "status": "error" if result.error else "ok",
                        "events_extracted": result.events_extracted,
                        "reflections_extracted": result.reflections_extracted,
                        "people_mentions_extracted": result.people_mentions_extracted,
                        "project_events_extracted": result.project_events_extracted,
                        "person_mentions_created": result.person_mentions_created,
                        "project_events_created": result.project_events_created,
                        "person_proposals_created": result.person_proposals_created,
                        "project_proposals_created": result.project_proposals_created,
                        "project_status_transitions": result.project_status_transitions,
                        "shredder_version_after": entry.shredder_version,
                        "elapsed_ms": per_entry_ms,
                        "error": result.error,
                    },
                )
            except OSError as exc:
                logger.warning("audit log write failed: %s", exc)
                report.errors.append(f"audit_log_write: {exc}")

        if i < len(candidates) - 1 and options.rate_limit_seconds > 0:
            await asyncio.sleep(options.rate_limit_seconds)

    report.finished_at = datetime.datetime.now(datetime.timezone.utc)

    if audit_handle is not None:
        try:
            _write_jsonl(
                audit_handle,
                {
                    "type": "summary",
                    "started_at": started_at,
                    "finished_at": report.finished_at,
                    "total_selected": report.total_selected,
                    "processed": report.processed,
                    "failed": report.failed,
                    "skipped_by_version": report.skipped_by_version,
                    "totals": {
                        "person_mentions_created": report.person_mentions_created,
                        "project_events_created": report.project_events_created,
                        "person_proposals_created": report.person_proposals_created,
                        "project_proposals_created": report.project_proposals_created,
                        "project_status_transitions": report.project_status_transitions,
                    },
                    "embeddings_purged_dates": [
                        d.isoformat() for d in report.embeddings_purged_dates
                    ],
                    "snapshot_path": str(report.snapshot_path) if report.snapshot_path else None,
                    "errors": report.errors,
                },
            )
        finally:
            audit_handle.close()

    logger.info(
        "backfill done selected=%d processed=%d failed=%d skipped_version=%d "
        "mentions=%d events=%d proposals=%d transitions=%d audit=%s",
        report.total_selected,
        report.processed,
        report.failed,
        report.skipped_by_version,
        report.person_mentions_created,
        report.project_events_created,
        report.person_proposals_created + report.project_proposals_created,
        report.project_status_transitions,
        report.audit_log_path,
    )

    return report


# ── Audit log replay (for GET /api/operations/backfill/last) ────────


def _list_audit_logs() -> list[Path]:
    log_dir = Path(settings.BACKFILL_LOG_DIR)
    if not log_dir.exists():
        return []
    return sorted(log_dir.glob("*.jsonl"))


def load_last_audit_summary() -> dict | None:
    """Return the parsed summary line from the most recent audit log, plus header.

    Adds a derived `match_rate` field per §9 when the relevant counters are non-zero.
    Returns None when no logs exist or the latest log lacks a summary line.
    """
    logs = _list_audit_logs()
    if not logs:
        return None

    latest = logs[-1]
    header: dict | None = None
    summary: dict | None = None
    entry_count = 0

    try:
        with latest.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = obj.get("type")
                if kind == "header":
                    header = obj
                elif kind == "summary":
                    summary = obj
                elif kind == "entry":
                    entry_count += 1
    except OSError as exc:
        logger.warning("Failed to read audit log %s: %s", latest, exc)
        return None

    if summary is None:
        return None

    totals = summary.get("totals") or {}
    person_created = totals.get("person_mentions_created", 0) or 0
    person_proposals = totals.get("person_proposals_created", 0) or 0
    project_created = totals.get("project_events_created", 0) or 0
    project_proposals = totals.get("project_proposals_created", 0) or 0

    person_total = person_created + person_proposals
    project_total = project_created + project_proposals

    match_rate = {
        "person": (person_created / person_total) if person_total else None,
        "project": (project_created / project_total) if project_total else None,
    }

    return {
        "audit_log_path": str(latest),
        "entry_count": entry_count,
        "header": header,
        "summary": summary,
        "match_rate": match_rate,
    }
