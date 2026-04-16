"""Parse Obsidian-style daily journal markdown files.

Expected format (from the synthetic_journals dataset):
    ```markdown
    ---
    tags:
      - daily_note
    journal: Personal Daily
    journal-date: 2026-10-01
    ---
    ```calendar-nav
    ```
    ...body sections...
    ```

The outer triple-backtick fence and YAML frontmatter are stripped.
The body text is returned as `raw_content`.
"""

from __future__ import annotations

import datetime
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedJournal:
    entry_date: datetime.date
    raw_content: str
    file_hash: str
    filename: str


_FRONTMATTER_DATE = re.compile(r"journal-date:\s*(\d{4}-\d{2}-\d{2})")
_FILENAME_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _extract_date(text: str, filename: str) -> datetime.date:
    """Try YAML frontmatter first, fall back to filename."""
    m = _FRONTMATTER_DATE.search(text)
    if m:
        return datetime.date.fromisoformat(m.group(1))

    m = _FILENAME_DATE.search(filename)
    if m:
        return datetime.date.fromisoformat(m.group(1))

    raise ValueError(f"Cannot determine date for {filename}")


def _strip_outer_fence(text: str) -> str:
    """Remove the outermost ```markdown ... ``` wrapper if present."""
    lines = text.split("\n")

    start = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("```markdown"):
            start = i + 1
            break

    end = len(lines)
    for i in range(len(lines) - 1, start - 1, -1):
        if lines[i].strip() == "```":
            end = i
            break

    return "\n".join(lines[start:end])


def _strip_boilerplate(text: str) -> str:
    """Remove YAML frontmatter and calendar-nav blocks, keep prose."""
    lines = text.split("\n")
    result: list[str] = []
    in_frontmatter = False
    in_calendar_nav = False

    for line in lines:
        stripped = line.strip()

        if stripped == "---" and not in_frontmatter and not result:
            in_frontmatter = True
            continue
        if stripped == "---" and in_frontmatter:
            in_frontmatter = False
            continue
        if in_frontmatter:
            continue

        if stripped.startswith("```calendar"):
            in_calendar_nav = True
            continue
        if in_calendar_nav and stripped == "```":
            in_calendar_nav = False
            continue
        if in_calendar_nav:
            continue

        result.append(line)

    return "\n".join(result).strip()


def parse_journal_file(path: Path) -> ParsedJournal:
    raw_bytes = path.read_bytes()
    file_hash = hashlib.sha256(raw_bytes).hexdigest()
    text = raw_bytes.decode("utf-8")

    entry_date = _extract_date(text, path.name)
    body = _strip_outer_fence(text)
    content = _strip_boilerplate(body)

    return ParsedJournal(
        entry_date=entry_date,
        raw_content=content,
        file_hash=file_hash,
        filename=path.name,
    )


def scan_journal_directory(directory: Path) -> list[ParsedJournal]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Journal directory not found: {directory}")

    journals: list[ParsedJournal] = []
    for path in sorted(directory.glob("*.md")):
        try:
            journals.append(parse_journal_file(path))
        except ValueError:
            continue

    return journals
