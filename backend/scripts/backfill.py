"""Backfill CLI — Step 6.

Run from the `backend/` directory:

    python -m scripts.backfill --max-version v2.2 --force --note "V2 cutover"

Or from the repo root:

    python backend/scripts/backfill.py --dry-run

Stop the FastAPI dev server before running this — the in-process
`_BACKFILL_LOCK` does not protect against cross-process LLM stampedes.

Exit codes:
  0  — all selected entries processed (or no-ops if --dry-run)
  1  — at least one entry failed
  2  — invalid selector input

Caveat: re-shredding a date can transition `projects.status` per Step 3
§12. Until Step 10 ships `last_manual_status_change_at`, avoid forcing
a re-shred on dates whose project statuses you have manually corrected.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import sys
from pathlib import Path

# Allow `python backend/scripts/backfill.py …` from the repo root by ensuring
# the `backend/` directory is importable as the top of the package path.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.core.database import async_session_factory  # noqa: E402
from app.services.backfill import (  # noqa: E402
    BackfillOptions,
    BackfillReport,
    BackfillSelector,
    run_backfill,
)


def _parse_date(value: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date {value!r}: {exc}") from exc


def _parse_date_list(value: str) -> list[datetime.date]:
    out: list[datetime.date] = []
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        out.append(_parse_date(chunk))
    if not out:
        raise argparse.ArgumentTypeError("--dates must contain at least one date")
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Backfill journal entries through Shredder + resolution.")
    p.add_argument("--from", dest="date_from", type=_parse_date, help="inclusive start date")
    p.add_argument("--to", dest="date_to", type=_parse_date, help="inclusive end date")
    p.add_argument("--dates", dest="entry_dates", type=_parse_date_list,
                   help="comma-separated YYYY-MM-DD list (overrides --from/--to)")
    p.add_argument("--only-unprocessed", action="store_true",
                   help="restrict to entries with processed_at IS NULL")
    p.add_argument("--max-version", dest="max_shredder_version",
                   help="re-shred entries with shredder_version < this value")
    p.add_argument("--force", action="store_true",
                   help="ignore version filter and re-shred every matched date")
    p.add_argument("--limit", type=int, help="cap the candidate list after ordering by date")
    p.add_argument("--dry-run", action="store_true",
                   help="print what would run; no DB writes, no LLM calls")
    p.add_argument("--rate-limit", type=float, default=1.0,
                   help="seconds to sleep between Gemini calls (default 1.0)")
    p.add_argument("--no-snapshot", action="store_true",
                   help="skip the SQLite snapshot before the run")
    p.add_argument("--purge-embeddings", action="store_true",
                   help="purge journal_embeddings for each affected date before shredding")
    p.add_argument("--note", help="operator comment recorded in the audit log header")
    p.add_argument("--log-level", default="INFO",
                   help="Python logging level (default INFO)")
    return p


def _print_report(report: BackfillReport) -> None:
    print()
    print("─" * 60)
    print(f"selected         : {report.total_selected}")
    print(f"processed        : {report.processed}")
    print(f"failed           : {report.failed}")
    print(f"skipped (version): {report.skipped_by_version}")
    print(f"mentions_created : {report.person_mentions_created}")
    print(f"events_created   : {report.project_events_created}")
    print(f"proposals_created: {report.person_proposals_created + report.project_proposals_created}")
    print(f"status_transitions: {report.project_status_transitions}")
    if report.snapshot_path:
        print(f"snapshot         : {report.snapshot_path}")
    if report.audit_log_path:
        print(f"audit log        : {report.audit_log_path}")
    if report.errors:
        print("errors:")
        for err in report.errors:
            print(f"  - {err}")
    print("─" * 60)


async def _amain(args: argparse.Namespace) -> int:
    selector = BackfillSelector(
        date_from=args.date_from,
        date_to=args.date_to,
        entry_dates=args.entry_dates,
        only_unprocessed=args.only_unprocessed,
        max_shredder_version=args.max_shredder_version,
        force=args.force,
        limit=args.limit,
    )
    options = BackfillOptions(
        dry_run=args.dry_run,
        rate_limit_seconds=args.rate_limit,
        snapshot_db=not args.no_snapshot,
        purge_embeddings=args.purge_embeddings,
        note=args.note,
    )

    async with async_session_factory() as db:
        try:
            report = await run_backfill(db, selector, options)
        except ValueError as exc:
            print(f"invalid selector: {exc}", file=sys.stderr)
            return 2

    _print_report(report)
    return 1 if report.failed > 0 else 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    return asyncio.run(_amain(args))


if __name__ == "__main__":
    sys.exit(main())
