# Step 6 — Backfill and operational scripts

**Index:** [README.md](./README.md)  
**Plan reference:** [JOURNALLM_V2_IMPLEMENTATION_PLAN.md](../../JOURNALLM_V2_IMPLEMENTATION_PLAN.md)  
**Status:** Complete (spec baseline ready for implementation)  
**Ideation refs:** §1.4, §1.5, Locked Q4 (re-shred = full re-extract).

---

## 1) Scope

### In scope

- A single backfill service (`backend/app/services/backfill.py`) that drives Steps 2 + 3 across a selectable batch of journal entries with **Q4 full re-extract** semantics.
- A thin admin HTTP surface (`/api/operations/*`) that wraps the service for the FastAPI dev server.
- A CLI entry point (`backend/scripts/backfill.py`) that wraps the same service for one-shot terminal runs.
- Embedding staleness handling: when an entry's `file_hash` changes (or the user forces a re-embed), purge old chunks from `journal_embeddings` **and** the `vec_journal_chunks` virtual table before any re-embed runs.
- Operational reporting: per-run JSONL audit log under `backend/data/backfill_logs/<YYYYMMDD-HHMMSS>.jsonl`, plus structured INFO logs.
- Safety affordances: SQLite snapshot before any non-dry-run batch, dry-run mode, rate-limit knob, resume-on-failure.
- Documented runbook for the V1 → V2 migration and the everyday "after I confirmed entities, do I need to re-shred?" question.

### Out of scope

- New schema/columns (Steps 1, 0 own this; Step 6 only adds an audit log directory under `backend/data/`).
- Inbox UI changes (Step 5).
- Dashboard changes (Steps 7–8).
- Caching extracted Gemini JSON to skip subsequent LLM calls — listed as a backlog item below; **not** delivered in Step 6.
- Multi-user/queueing concerns. Single-user assumption holds.

---

## 2) Locked decisions applied

- **Q1 (proposal-driven entities):** backfill never auto-confirms anything. Bulk shred + resolve only fills `entity_proposals`; the user reviews via the inbox.
- **Q2 (no auto-merge):** unchanged — the cascade in Step 4 still requires a user action to fire. Backfill leaves resolution-only deltas in the inbox.
- **Q3 (project status inference):** runs as part of resolution during shred. Re-shredding a date that previously had a manual status set is acceptable; user-initiated edits land in Step 10. Until Step 10 ships, callers should be aware that re-shred can transition `projects.status` according to the §12 decision table in Step 3.
- **Q4 (re-shred = full re-extract):** every per-entry pass deletes derived rows for that `entry_date` and rebuilds in one transaction (already implemented by Step 2 + Step 3). Backfill is a loop over per-entry transactions, not one giant transaction.

---

## 3) Dependencies

- **Reads normative detail from:**
  - Step 0 — `shredder_version` semantics, re-shred contract, sentiment migration.
  - Step 1 — schema for `journal_entries`, `journal_embeddings`, `vec_journal_chunks`.
  - Step 2 — extraction contract, per-entry shred behavior, current `shredder_version` constant (`v2.2`).
  - Step 3 — resolution behavior, `ResolutionResult` shape, idempotency guarantees, deletion of pending proposals on rebuild.
  - Step 4 — cascade behavior; backfill output fuels the inbox queue.
- **Feeds:**
  - Step 9 — once embeddings know about entity-aware chunks, the staleness purge in §6 is the natural hook for re-embed triggers.
  - Step 13 — release runbook references this doc verbatim.

---

## 4) Module layout

New files:

```
backend/app/services/backfill.py
backend/app/routes/operations.py
backend/scripts/__init__.py
backend/scripts/backfill.py
backend/data/backfill_logs/.gitkeep
```

Touched files:

```
backend/app/main.py                      # include new operations router
backend/app/services/ingestion.py        # purge stale embeddings on hash change
backend/app/services/embeddings.py       # extract a `purge_entry_embeddings` helper
```

The service holds **all** business logic. The route and CLI are 30-line adapters that translate inputs and serialize outputs.

---

## 5) Service contract (`backend/app/services/backfill.py`)

### 5.1 `BackfillSelector`

How to pick which entries are in scope:

```python
@dataclass
class BackfillSelector:
    date_from: date | None = None        # inclusive
    date_to: date | None = None          # inclusive
    entry_dates: list[date] | None = None  # explicit date list, takes priority over range
    only_unprocessed: bool = False       # processed_at IS NULL
    max_shredder_version: str | None = None  # "v2.1" → re-shred any entry < v2.1, including null
    force: bool = False                  # if True, ignore version filter and re-shred matched dates anyway
    limit: int | None = None             # safety cap on rows returned
```

Resolution rules:

1. If `entry_dates` is set, use those exact dates and ignore `date_from`/`date_to`.
2. Otherwise apply `date_from`/`date_to` (defaults: full corpus).
3. If `only_unprocessed`, additionally require `processed_at IS NULL`.
4. If `max_shredder_version` is set:
   - Compare using `_compare_version` (semver-ish helper, treats `None` as `"v0"`).
   - When `force=False`, **skip** entries whose `shredder_version >= max_shredder_version`.
   - When `force=True`, the filter is purely informational (logged, not applied) and every selected entry is re-shredded.
5. If `limit` is set, slice the final list after ordering by `entry_date ASC`.
6. If selection is empty, return early — no LLM client built, no audit log written.

### 5.2 `BackfillOptions`

How to run the batch:

```python
@dataclass
class BackfillOptions:
    dry_run: bool = False
    rate_limit_seconds: float = 1.0          # sleep between LLM calls
    snapshot_db: bool = True                 # copy SQLite file before first write
    purge_embeddings: bool = False           # also clear journal_embeddings for affected dates
    audit_log_path: Path | None = None       # default: backend/data/backfill_logs/<ts>.jsonl
    note: str | None = None                  # operator comment, recorded in audit header
```

### 5.3 `BackfillReport`

```python
@dataclass
class BackfillReport:
    started_at: datetime
    finished_at: datetime
    selector: BackfillSelector
    options: BackfillOptions
    snapshot_path: Path | None
    audit_log_path: Path | None
    total_selected: int
    processed: int
    failed: int
    skipped_by_version: int                  # version filter excluded these
    person_mentions_created: int
    project_events_created: int
    person_proposals_created: int
    project_proposals_created: int
    project_status_transitions: int
    embeddings_purged_dates: list[date]
    entries: list[EntryResult]               # reuse Step 2 dataclass
    errors: list[str]                        # non-fatal collected errors
```

`EntryResult` is the Step 2 dataclass already in `backend/app/services/shredder.py`. Backfill **does not** invent a new per-entry shape; it aggregates existing ones plus high-level totals.

### 5.4 `run_backfill`

```python
async def run_backfill(
    db: AsyncSession,
    selector: BackfillSelector,
    options: BackfillOptions = BackfillOptions(),
) -> BackfillReport
```

Lifecycle:

1. Validate selector (`date_from <= date_to`, `entry_dates` non-empty when set, etc.). On invalid input raise `ValueError` — caller maps to HTTP 400 / CLI exit 2.
2. Resolve the candidate `JournalEntry` list per §5.1.
3. Open the audit log (unless `dry_run`).
4. **If not dry-run and `snapshot_db`:** copy the SQLite file to `journallm.db.backup-<timestamp>` next to it. Log path; record on report.
5. **If `purge_embeddings`:** delete `journal_embeddings` and `vec_journal_chunks` rows for each candidate date **before** shred. (Re-embedding is a separate explicit operation in §7.4 — Step 6 only purges; Step 9 owns the re-embed orchestration.)
6. Build the Gemini client (existing `_build_client()` import from shredder service).
7. For each entry in the candidate list:
   - If `dry_run`: append a `DryRunEntryResult` to the report with the would-be action and continue. No DB writes, no LLM calls.
   - Otherwise call `_process_single_entry(db, entry, client)` from `backend/app/services/shredder.py` (re-export it as part of its public API in Step 6 — currently underscore-private, Step 6 will rename or expose a stable wrapper). The function already covers Q4 transactional clear+rebuild + resolution.
   - Append the returned `EntryResult` to the report.
   - Write the entry result as a JSONL row to the audit log immediately (one line per entry; resilient against crashes mid-run).
   - Sleep `options.rate_limit_seconds`.
8. Aggregate totals from `EntryResult` instances.
9. Close the audit log with a final summary line of type `summary`.
10. Return `BackfillReport`.

### 5.5 Re-export from shredder

Step 6 promotes `_process_single_entry` to `process_single_entry` (rename, no semantic change) so backfill consumes the documented entry point rather than reaching into `_`-private internals. Existing call site in `run_shredder` updates accordingly. This is a name change only — behavior, transactions, and `shredder_version` writes are untouched (Step 2 owns those).

---

## 6) Embedding staleness

### 6.1 Ingestion already detects content change

`backend/app/services/ingestion.py` clears `processed_at` when `file_hash` differs from the parsed file. Today it does **not** purge embeddings, which means the next time `/api/chat/embed` runs, the entry is skipped because `existing_dates` already contains its date — old chunks linger.

### 6.2 New helper in embeddings service

Add to `backend/app/services/embeddings.py`:

```python
async def purge_entry_embeddings(db: AsyncSession, entry_date: date) -> int:
    """Delete journal_embeddings rows + matching vec_journal_chunks rowids for entry_date.
    Returns count of deleted chunks. Caller commits."""
```

Implementation: select `JournalEmbedding.id` for the date, `DELETE FROM vec_journal_chunks WHERE rowid IN (...)`, then `DELETE FROM journal_embeddings WHERE entry_date = ...`.

### 6.3 Hook into ingestion

In `ingest_journals`, after marking an entry as updated (file_hash changed branch), call `purge_entry_embeddings(db, existing.entry_date)` before the final commit. This guarantees a subsequent `/api/chat/embed` will regenerate chunks for the changed entry.

### 6.4 Hook into backfill

When `BackfillOptions.purge_embeddings=True`, call `purge_entry_embeddings` for each selected date inside the same per-entry transaction as the shred. Default is `False` because chunk text is `raw_content`, which does not change during a re-shred — purging is wasteful unless the operator knows Step 9 changed the chunk source.

### 6.5 Step 9 handoff

Step 9 will likely change chunk inputs to include `life_event` summaries / `journal_reflections.content`. When Step 9 lands, `BackfillOptions.purge_embeddings` should become the default (or a new option `re_embed_after=True` should imply purge + immediate `embed_journals` call). Step 6 wires the trigger; Step 9 will own the policy.

---

## 7) HTTP API (`backend/app/routes/operations.py`)

Tag: `"operations"`. Mounted at `/api`.

### 7.1 `POST /api/operations/backfill`

**Request body:**

```python
class BackfillRequest(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    entry_dates: list[date] | None = None
    only_unprocessed: bool = False
    max_shredder_version: str | None = None
    force: bool = False
    limit: int | None = None
    dry_run: bool = False
    rate_limit_seconds: float = 1.0
    snapshot_db: bool = True
    purge_embeddings: bool = False
    note: str | None = None
```

**Response:** the full `BackfillReport` serialized as JSON. For long-running runs the route streams an SSE/event-stream variant deferred to Step 13; Step 6 ships the synchronous version because typical personal corpora are <500 entries and finish in a few minutes at 1 req/s.

**Errors:**
- `400` for invalid selector input, including `entry_dates=[]` and `date_from > date_to`.
- `409` if a backfill is already in progress (see §7.2 lock).
- `500` for unexpected Gemini errors that escape the per-entry try/except.

### 7.2 In-flight lock

Wrap the route handler in a process-local `asyncio.Lock` named `_BACKFILL_LOCK`. While held, additional calls return `409 {"detail": "backfill already running"}`. This prevents a curious user from double-clicking a button in a future admin UI and running two LLM stampedes at once.

### 7.3 `GET /api/operations/backfill/last`

Returns the last `BackfillReport` from `backend/data/backfill_logs/`, parsed back from its summary line. Read-only; useful for a future operations panel and unit tests. Returns `404` if no logs exist.

### 7.4 `POST /api/operations/re-embed`

Trigger the embedding regeneration deliberately. Request body:

```python
class ReembedRequest(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    entry_dates: list[date] | None = None
    purge_first: bool = True
```

Behavior:
1. Resolve target dates (same selector style as backfill, minus version filter).
2. If `purge_first`, call `purge_entry_embeddings` for each date.
3. Call existing `embed_journals(db)`.
4. Return `EmbedResult` plus the list of dates affected.

This endpoint is the single place to operationally re-embed; it replaces ad-hoc cleanup. Step 9 will refine the request shape if it adds entity-level chunks.

### 7.5 `POST /api/operations/snapshot`

Force-create a SQLite snapshot without running anything else:

```python
class SnapshotResponse(BaseModel):
    snapshot_path: str
    bytes_copied: int
    created_at: datetime
```

Path scheme: `journallm.db.backup-<YYYYMMDD-HHMMSS>` next to the live DB. Reused by `BackfillOptions.snapshot_db=True`.

---

## 8) CLI (`backend/scripts/backfill.py`)

Goal: power-user tool that calls the same service, no FastAPI process required.

```
python -m backend.scripts.backfill \
    [--from YYYY-MM-DD] [--to YYYY-MM-DD] \
    [--dates D1,D2,...] \
    [--only-unprocessed] \
    [--max-version v2.1] \
    [--force] \
    [--limit N] \
    [--dry-run] \
    [--rate-limit SECONDS] \
    [--no-snapshot] \
    [--purge-embeddings] \
    [--note STRING]
```

Behavior notes:

- Loads `app.core.config.settings`, opens a one-shot `AsyncSession` against the live DB, and calls `run_backfill`.
- Prints a colored single-line per entry plus the final report summary to stdout.
- Exit codes:
  - `0` — all selected entries processed (or no-ops if dry-run).
  - `1` — at least one entry failed.
  - `2` — invalid selector input (validated before any LLM call).
- The CLI does **not** require the FastAPI server to be running; in fact the `409 already_running` lock is in-process only, so spinning up the CLI while the server is doing a backfill could conflict at the LLM rate-limit / DB level. Document this as: "stop the server before running the CLI." A more robust file-based lock is backlog.

A second one-shot script:

```
python -m backend.scripts.re_embed [--from ...] [--to ...] [--no-purge]
```

Wraps the same logic as §7.4.

---

## 9) Audit log format

Path: `backend/data/backfill_logs/<YYYYMMDD-HHMMSS>.jsonl`. One JSON object per line. Schema:

```jsonc
// Header (first line)
{"type":"header","started_at":"2026-04-22T12:00:00Z","selector":{...},"options":{...},"note":"..."}

// One per entry processed
{"type":"entry","entry_date":"2026-03-12","status":"ok",
 "events_extracted":7,"reflections_extracted":2,
 "people_mentions_extracted":3,"project_events_extracted":1,
 "person_mentions_created":2,"project_events_created":1,
 "person_proposals_created":1,"project_proposals_created":0,
 "project_status_transitions":0,"error":null,
 "shredder_version_after":"v2.2"}

// Optional dry-run line
{"type":"entry","entry_date":"2026-03-13","status":"dry_run",
 "would_run":true,"current_shredder_version":"v2.0","note":"version_filter_match"}

// Final line
{"type":"summary","finished_at":"2026-04-22T12:04:11Z",
 "processed":42,"failed":1,"skipped_by_version":3,
 "totals":{"person_mentions_created":80,"project_events_created":12,
   "person_proposals_created":18,"project_proposals_created":4,
   "project_status_transitions":2},
 "embeddings_purged_dates":[],
 "errors":["2026-03-21: gemini timeout after 3 retries"]}
```

Match-rate metric (Step 6 derivative): `match_rate = mentions_created / (mentions_created + person_proposals_created)`. Computed on read in `GET /api/operations/backfill/last`, not stored.

---

## 10) Order of operations (the V2 runbook)

Single-user mental model, target audience = Eric.

### 10.1 First-time V2 migration

1. **Snapshot:** `POST /api/operations/snapshot` (or just `cp journallm.db journallm.db.bak`).
2. **Migrate schema:** apply Step 1 migrations (`alembic upgrade head` once Alembic is wired; until then, the SQLAlchemy `init_db()` ensures new tables exist).
3. **Ingest (idempotent):** `POST /api/journals/ingest`. This already reads from `JOURNAL_SOURCE_DIR` and upserts.
4. **Backfill all entries:**
   ```
   python -m backend.scripts.backfill --max-version v2.2 --force --note "V2 cutover"
   ```
   Force is needed because previously-shredded V1 entries have `processed_at IS NOT NULL` and the V1 `shredder_version` is `v1` or null; the version filter would already select them, but `--force` makes the intent explicit. Expect ~1s per entry × N entries.
5. **Triage inbox:** open `/inbox`, work through pending proposals. Cascade resolves duplicates automatically (Step 4 §10).
6. **Optional resolve-only second pass:** if a long batch of merges added many aliases (e.g. you confirmed `Sam Chen` with alias `Sam`, `Samuel`, `S.C.`), some dates may still show stale pending proposals **only** if the cascade did not run for them. In practice cascade in Step 4 already covers this. Step 6 documents the **fallback**: re-run backfill with `--force` for the affected date range — the resolution layer will now match the new aliases deterministically and the pending proposals will be deleted as part of Step 3's clean-slate behavior. Cost: one Gemini call per date. **Avoid this unless cascade clearly missed dates.**
7. **Re-embed:** `POST /api/operations/re-embed` if you intend to use chat. With Step 9 not yet shipped, this is identical to today's `/api/chat/embed`; Step 6 just exposes a re-runnable variant.

### 10.2 Day-to-day flow (after V2 cutover)

```
[journal file edit]
        │
        ▼
 ingest_journals (file_hash diff → processed_at=null + purge embeddings)
        │
        ▼
 run_shredder (per-entry: shred + resolve in one tx)
        │
        ▼
 inbox triage (only if new proposals appeared)
        │
        ▼
 chat / dashboard see updated rows immediately
```

This is the unchanged shred loop. The only Step 6 addition is the embedding purge during ingestion (§6.3).

### 10.3 "I changed the prompt or schema" flow

```
1. Bump shredder_version constant in services/shredder.py (e.g. v2.2 → v2.3).
2. Run: python -m backend.scripts.backfill --max-version v2.3
3. Triage inbox.
4. If chunk inputs changed in Step 9: re-embed.
```

The `--max-version` filter ensures only the entries that need updating are re-shredded; everything already at v2.3 is skipped without an LLM call.

---

## 11) Behavior, transactions, and failure modes

- **Per-entry transaction:** still owned by `process_single_entry` (Step 2). On exception, rollback for that entry; loop continues. Failed entries remain `processed_at IS NULL` (or retain prior version) so they can be retried with `--only-unprocessed` later.
- **Whole-batch failure:** if the Gemini client cannot be built (missing API key) the run aborts before processing any entry. Audit log records the error and exits with code 1.
- **Crash mid-batch:** the JSONL audit log is flushed line-by-line; on restart, run with `--only-unprocessed` to pick up where it stopped.
- **Concurrent backfills:** prevented within one process via `_BACKFILL_LOCK`. Across processes (server + CLI) operators must serialize themselves; the SQLite WAL will serialize writes but not LLM rate limits or audit log naming.
- **Cascade interaction:** backfill produces proposals; user confirms/merges via Step 4 endpoints; cascade auto-resolves duplicates. Backfill itself never resolves proposals.
- **Project status drift:** every re-shred re-applies inference per Step 3 §12. If the user has manually edited a status via Step 10 (when shipped), re-shred can overwrite it. Step 10 will introduce `last_manual_status_change_at` to defend against that; until then, **operators should avoid forced re-shred on dates whose project statuses were manually corrected**. Document this caveat in the CLI `--help` and inbox UI README. (Tracked as a Step 10 dependency.)

---

## 12) Observability

Per backfill run logs a single INFO line per entry, identical in shape to Step 3's resolution summary:

```
backfill date=2026-03-12 events=7 reflections=2 mentions_created=2 events_created=1 proposals=1 status_transitions=0 ms=1834
```

Plus aggregate INFO at the end:

```
backfill done selected=45 processed=42 failed=1 skipped_version=3 mentions=80 events=12 proposals=22 transitions=2 audit=backend/data/backfill_logs/20260422-1200.jsonl
```

Match-rate is logged at INFO if total people surface count is non-zero:

```
backfill match_rate person=78% project=67%
```

WARN on:
- Gemini retries exhausted for a date.
- Snapshot copy failure (run aborts).
- Audit log write failure (run continues, single warning, `BackfillReport.errors` populated).

DEBUG on:
- Per-entry version comparison decisions.
- Per-entry candidate proposal counts before resolution commit.

---

## 13) Testing plan

### 13.1 Unit tests

- `_compare_version` — `None < "v1" < "v1.0" < "v2.0" < "v2.10"` (treat numeric segments numerically, not lexicographically).
- `BackfillSelector` resolution against an in-memory DB: range, explicit dates, version filter, `force` overrides, `limit`.
- `purge_entry_embeddings` removes both ORM rows and matching `vec_journal_chunks` rows by id.
- Ingestion regression: when `file_hash` changes for an entry that has embeddings, the embeddings count drops to 0 after `ingest_journals`.

### 13.2 Integration tests (FastAPI TestClient + monkey-patched Gemini)

Patch `app.services.shredder._call_gemini` to return a fixed `ExtractionResponse` so we don't hit the network.

- `dry_run=True` returns selected entries without writing rows or files; `processed_at` of every selected entry is unchanged.
- Full backfill on a fresh DB with 3 entries and 1 stale entry (`shredder_version="v2.1"`):
  - `--max-version v2.2` re-shreds only the stale entry.
  - `--force` re-shreds all 4.
- Snapshot file is created at the documented path and is non-empty.
- Audit log JSONL has exactly `1 + N + 1` lines (header, entries, summary).
- `409 already_running` when two `/api/operations/backfill` calls overlap.

### 13.3 Re-shred + inbox interaction

- Seed 1 person `Sam Chen` with alias `Sam`. Pre-create a pending proposal for `Samuel` on date D1.
- Run backfill on D1 with `--force`. Confirm:
  - Pending proposal for `Samuel` on D1 is deleted (Step 3 clean-slate) and recreated (still pending — `Samuel` did not match alias).
  - `accepted_new` proposals from prior runs remain.
- Then resolve via Step 4 `merge-existing` with `add_alias=True`. Re-run backfill on D2 (which also contains `Samuel`). Confirm: D2 now produces a `person_mentions` row, no proposal.

### 13.4 Manual smoke

1. Stop the FastAPI server.
2. `python -m backend.scripts.backfill --dry-run`. Verify the printed plan matches expectation.
3. Start the server, run `POST /api/operations/backfill` with the same selector. Verify audit log appears under `backend/data/backfill_logs/`.
4. `GET /api/operations/backfill/last` returns the parsed summary.

---

## 14) Configuration

No new env vars are strictly required. Optional additions to `app.core.config.Settings`:

```python
BACKFILL_RATE_LIMIT_SECONDS: float = 1.0
BACKFILL_LOG_DIR: str = str(PROJECT_ROOT / "data" / "backfill_logs")
BACKFILL_SNAPSHOT_DIR: str | None = None  # default = directory of DATABASE_URL
```

These let an operator override defaults without touching code. Defaults match the inline constants used by the service.

`backend/data/` should be added to `.gitignore` (the directory is operator-scoped). Commit a single placeholder `.gitkeep` so the path exists in fresh clones.

---

## 15) Rollout / rollback

- **Rollout:** Step 6 only adds files plus two small touch-ups in `ingestion.py` and `embeddings.py`. Deploy without flags.
- **Rollback:** revert the operations router and CLI; the only persistent side-effect is files under `backend/data/backfill_logs/` and any `*.bak` SQLite snapshots — both are safe to leave or delete manually.
- **Schema impact:** none (Step 6 does not migrate).
- **Backfill compatibility:** the renaming of `_process_single_entry` to `process_single_entry` is internal; the existing `/api/shredder/run` continues to work because it imports `run_shredder` (unchanged).

---

## 16) Backlog (explicitly deferred from Step 6)

Track in ideation Phase 5 unless promoted earlier:

1. **Cached extraction JSON** — store the raw Gemini response next to the entry (e.g. `journal_entries.last_extraction_json`) so a resolution-only re-run does not need a new LLM call. Saves cost on alias-heavy backfills.
2. **Resume from audit log** — `--resume <log_path>` reads the JSONL and skips entries already marked `status="ok"`.
3. **Streaming response from `/api/operations/backfill`** — SSE per-entry progress for a future operations dashboard widget.
4. **File-based lock** for cross-process serialization between server + CLI.
5. **Weekly cron preset** — `python -m backend.scripts.weekly_ops` that ingests, shreds new entries, and emits a digest of inbox additions.
6. **Step 10 coupling** — once `last_manual_status_change_at` lands, backfill should refuse to overwrite manually-edited project statuses unless `--force-status` is set.

---

## 17) Definition of done

Step 6 is complete when:

- `backend/app/services/backfill.py` implements `BackfillSelector`, `BackfillOptions`, `BackfillReport`, and `run_backfill` per §5.
- `process_single_entry` is the public name in `backend/app/services/shredder.py`; `run_shredder` and the new backfill share it.
- `/api/operations/backfill`, `/api/operations/backfill/last`, `/api/operations/re-embed`, and `/api/operations/snapshot` are mounted and documented in OpenAPI.
- `backend/scripts/backfill.py` and `backend/scripts/re_embed.py` are runnable as `python -m backend.scripts.<name>` with the documented flags and exit codes.
- Ingestion purges stale embeddings on `file_hash` change.
- Audit logs land under `backend/data/backfill_logs/<ts>.jsonl` in the documented schema; `BackfillReport.audit_log_path` round-trips via `GET /api/operations/backfill/last`.
- Tests in §13.1–§13.3 pass.
- The runbook in §10 is the single source of truth referenced from the project README and Step 13.

---

## Changelog

- 2026-04-27 — Initial complete Step 6 spec. Defines a single backfill service with HTTP + CLI adapters, codifies Q4 transactional re-shred at the batch level, adds embedding-staleness handling on ingestion, specifies per-run JSONL audit logs, and documents the V2 cutover runbook plus everyday and prompt-bump operational flows. Deliberately defers extraction caching, streaming progress, and multi-process locking to backlog.
