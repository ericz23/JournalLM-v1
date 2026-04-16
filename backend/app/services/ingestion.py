"""Ingest parsed journal files into the database.

Handles upsert logic: if a journal for a given date already exists and
the file hash is unchanged, skip it.  If the hash differs (content was
edited), update the row and clear `processed_at` so the Shredder knows
to re-extract events.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal_entry import JournalEntry
from app.services.journal_parser import ParsedJournal, scan_journal_directory


@dataclass
class IngestionResult:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] | None = None

    @property
    def total_scanned(self) -> int:
        return self.inserted + self.updated + self.skipped


async def ingest_journals(
    db: AsyncSession,
    journal_dir: Path,
) -> IngestionResult:
    parsed = scan_journal_directory(journal_dir)
    result = IngestionResult(errors=[])

    dates = [p.entry_date for p in parsed]
    existing_q = await db.execute(
        select(JournalEntry).where(JournalEntry.entry_date.in_(dates))
    )
    existing_map: dict[datetime.date, JournalEntry] = {
        row.entry_date: row for row in existing_q.scalars().all()
    }

    for journal in parsed:
        try:
            existing = existing_map.get(journal.entry_date)

            if existing is None:
                db.add(
                    JournalEntry(
                        entry_date=journal.entry_date,
                        raw_content=journal.raw_content,
                        file_hash=journal.file_hash,
                    )
                )
                result.inserted += 1

            elif existing.file_hash == journal.file_hash:
                result.skipped += 1

            else:
                existing.raw_content = journal.raw_content
                existing.file_hash = journal.file_hash
                existing.processed_at = None
                result.updated += 1

        except Exception as exc:
            result.errors.append(f"{journal.filename}: {exc}")  # type: ignore[union-attr]

    await db.commit()
    return result
