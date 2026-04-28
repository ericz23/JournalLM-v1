"""Re-embedding CLI — Step 6.

Run from the `backend/` directory:

    python -m scripts.re_embed --from 2026-03-01 --to 2026-03-31

Or from the repo root:

    python backend/scripts/re_embed.py --no-purge

Wraps the same logic as `POST /api/operations/re-embed`. Stop the
FastAPI dev server before running this so the embedding rate limit
is not split across two processes.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import sys
from pathlib import Path

# Allow `python backend/scripts/re_embed.py …` from the repo root.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.database import async_session_factory  # noqa: E402
from app.models.journal_entry import JournalEntry  # noqa: E402
from app.services.embeddings import embed_journals, purge_entry_embeddings  # noqa: E402


def _parse_date(value: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date {value!r}: {exc}") from exc


def _parse_date_list(value: str) -> list[datetime.date]:
    out = [
        _parse_date(c.strip()) for c in value.split(",") if c.strip()
    ]
    if not out:
        raise argparse.ArgumentTypeError("--dates must contain at least one date")
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Purge + regenerate journal embeddings.")
    p.add_argument("--from", dest="date_from", type=_parse_date)
    p.add_argument("--to", dest="date_to", type=_parse_date)
    p.add_argument("--dates", dest="entry_dates", type=_parse_date_list,
                   help="comma-separated date list (overrides --from/--to)")
    p.add_argument("--no-purge", action="store_true",
                   help="skip purge_entry_embeddings; only fill in missing chunks")
    p.add_argument("--log-level", default="INFO")
    return p


async def _amain(args: argparse.Namespace) -> int:
    if (
        args.date_from is not None
        and args.date_to is not None
        and args.date_from > args.date_to
    ):
        print("invalid range: --from must be <= --to", file=sys.stderr)
        return 2

    async with async_session_factory() as db:
        q = select(JournalEntry.entry_date)
        if args.entry_dates is not None:
            q = q.where(JournalEntry.entry_date.in_(args.entry_dates))
        else:
            if args.date_from is not None:
                q = q.where(JournalEntry.entry_date >= args.date_from)
            if args.date_to is not None:
                q = q.where(JournalEntry.entry_date <= args.date_to)
        target_dates = list(
            (await db.execute(q.order_by(JournalEntry.entry_date.asc()))).scalars().all()
        )

        purged: list[datetime.date] = []
        if not args.no_purge:
            for d in target_dates:
                count = await purge_entry_embeddings(db, d)
                if count:
                    purged.append(d)
            if purged:
                await db.commit()

        result = await embed_journals(db)

    print()
    print("─" * 60)
    print(f"target dates    : {len(target_dates)}")
    print(f"purged dates    : {len(purged)}")
    print(f"entries embedded: {result.entries_processed}")
    print(f"chunks created  : {result.chunks_created}")
    print(f"skipped         : {result.skipped}")
    print("─" * 60)
    return 0


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
