# Step 3 — Entity resolution and proposal creation

**Index:** [README.md](./README.md)  
**Plan reference:** [JOURNALLM_V2_IMPLEMENTATION_PLAN.md](../../JOURNALLM_V2_IMPLEMENTATION_PLAN.md)  
**Status:** Complete (spec baseline ready for implementation)  
**Ideation refs:** §1.3, §1.5, Locked Q1, Q2, Q3, Q4.

---

## 1) Scope

### In scope

- A new resolution service that runs after Shredder V2 extraction per journal entry.
- Deterministic matching of extracted people/project surface strings against existing canonical entities.
- Proposal creation for unresolved surface strings (no auto-create of `people` / `projects`).
- Creation of `person_mentions` and `project_events` rows for confirmed matches.
- Linking mentions/events to `life_events.id` when possible via `linked_event_hint`.
- Applying inferred project status updates (Q3) for matched projects.
- Aggregate stat maintenance (`mention_count`, `first_seen_date`, `last_seen_date`).
- Blocklist filtering during resolution.
- Idempotent re-run semantics aligned with Q4 full re-extract.

### Out of scope

- API endpoints for listing/acting on proposals (Step 4).
- UI flows for confirming/merging proposals (Step 5).
- Batch backfill runbook (Step 6).
- Dashboard surfacing of confirmed entities (Step 7).

---

## 2) Current state snapshot (end of Step 2)

After Step 2, the shredder:
- Emits `people_mentioned` and `project_events` in its extraction output.
- Persists `life_events` and `journal_reflections` only.
- Leaves `people_mentioned` and `project_events` **unused** (not persisted anywhere).
- Writes `shredder_version = "v2.1"` per entry on success.

Step 1 has already provided:
- `people`, `person_mentions`, `projects`, `project_events`, `entity_proposals`, `entity_blocklist` tables with FK/cascade rules supporting Q4.
- `SentimentLabel`, `ProjectStatus`, `ProjectEventType`, `ProposalStatus`, `ProposalEntityType`, `BlocklistReason` enums.

Step 3 is the layer that **consumes** the Step 2 extraction output and populates the Step 1 tables.

---

## 3) Locked decisions applied

- **Q1:** No canonical `people` / `projects` rows get created automatically by this step. Unmatched strings become `entity_proposals`.
- **Q2:** Matching against canonical entities uses exact/alias match first; light fuzzy (token overlap + edit distance) is used **only** to rank candidate merge suggestions for the inbox — never to auto-merge.
- **Q3:** Resolution may infer and update `projects.status` from `event_type` and `suggested_project_status`. User edits in the UI always win over later automatic updates (enforced in Step 10 UI; Step 3 simply applies status when appropriate).
- **Q4:** Re-running resolution on a re-shredded date must leave a clean, consistent state. Cascades from `life_events` deletes must be complemented by idempotent resolution replay.

---

## 4) Module layout

New backend module:

- `backend/app/services/entity_resolution.py`

Public entry point (called by shredder after successful extraction persistence):

```
async def resolve_entry(
    db: AsyncSession,
    entry_date: date,
    life_events: list[LifeEvent],
    extraction: ExtractionResponse,
) -> ResolutionResult
```

Where `extraction` is the raw Step 2 Pydantic response (provides `people_mentioned` and `project_events` plus event-linking hints).

The shredder invokes this function within the same per-entry transaction, before `db.commit()`.

---

## 5) Data flow (per journal entry)

1. Shredder persists `life_events` and `journal_reflections` (Step 2 behavior).
2. Resolution service starts. It has in-memory access to:
   - Extraction response (Step 2).
   - List of newly persisted `LifeEvent` rows (with real `id`s) for that date.
3. Clean slate for the date:
   - Delete `person_mentions` where `entry_date == entry_date`.
   - Delete `project_events` where `entry_date == entry_date`.
   - Delete `entity_proposals` where `entry_date == entry_date` **and** status in `{pending, rejected, dismissed, blocked}` that originated from prior extraction runs.
     - **Do NOT delete** proposals with status `accepted_new` or `merged_existing` (those are historical audit records of past user decisions and should be preserved).
4. For each extracted `people_mentioned` item:
   - Apply blocklist filter.
   - Attempt match against `people` (exact → alias → case-insensitive).
   - If matched: create `person_mentions` row linked to person, entry date, optional `life_event_id`.
   - If unmatched: compute ranked merge candidates via light fuzzy matching, create `entity_proposals(person, pending)`.
5. For each extracted `project_events` item:
   - Apply blocklist filter.
   - Attempt match against `projects`.
   - If matched:
     - Create `project_events` row linked to project, entry date, optional `life_event_id`.
     - Apply project status inference (Q3).
   - If unmatched: compute ranked candidates, create `entity_proposals(project, pending)`.
6. Update aggregates (`mention_count`, `first_seen_date`, `last_seen_date`) only for entities that got a real mention/event linked in this run.
7. Return `ResolutionResult` summary to shredder; shredder commits.

---

## 6) Surface string normalization

Implemented in `_normalize_surface(name: str) -> str`.

Rules:
- Strip whitespace.
- Collapse internal runs of whitespace to single space.
- Case-preserved for display (`canonical_name`), but matching uses case-insensitive comparison.
- Do not strip punctuation aggressively; only trim trailing `.`, `,`, `;`, `:`, `"` and surrounding quotes.
- Reject empty strings after normalization (skip item, log warning).
- Enforce max length of 200 characters (truncate with warning if longer).

---

## 7) Matching algorithm (people)

Input: normalized surface string `s`.

Order of checks:
1. **Exact canonical match (case-insensitive):**
   - `SELECT * FROM people WHERE LOWER(canonical_name) = LOWER(s)`
   - If one row returns: **matched**.
2. **Exact alias match (case-insensitive):**
   - Scan `people.aliases_json` for `s` (case-insensitive equality).
   - If exactly one person has `s` as an alias: **matched**.
   - If multiple candidates match via aliases: treat as ambiguous → create **proposal** with all candidates ranked.
3. **No match:** go to proposal path (§9).

Matching short-circuits at the first deterministic hit; fuzzy is not used for matching decisions.

---

## 8) Matching algorithm (projects)

Input: normalized surface string `s`.

Order of checks:
1. **Exact name match (case-insensitive).**
2. **Exact alias match (case-insensitive).**
3. **No match:** proposal path (§9).

Same ambiguity rules as people — multiple alias candidates means proposal, not auto-merge.

---

## 9) Proposal creation

When no confident match is found, create an `entity_proposals` row with:

- `entity_type`: `person` or `project`.
- `status`: `pending`.
- `surface_name`: normalized surface string.
- `entry_date`: from extraction.
- `life_event_id`: resolved from `linked_event_hint` (§11), nullable.
- `payload_json`: serialized extracted structure:
  - For person: `name`, `relationship_hint`, `interaction_context`, `linked_event_hint`, `sentiment`.
  - For project: `project_name`, `event_type`, `description`, `linked_event_hint`, `suggested_project_status`.
- `candidate_matches_json`: ranked candidate list from light fuzzy (§10), or empty list.
- `resolution_entity_id`: null until user action (handled in Step 4).

Deduplication within a single run:
- Collapse multiple extraction items for the same `surface_name` + `entity_type` on one `entry_date` into a single proposal row. The combined `payload_json` should preserve all context snippets (append list).

Blocklist filtering:
- Before creating a proposal, check `entity_blocklist` for `(entity_type, LOWER(surface_name))`.
- If blocked: **do not create proposal**. Log at info level only. Never emit user-facing noise.

---

## 10) Candidate ranking for proposals (Q2 fuzzy)

Candidates are computed only to **rank** merge suggestions in the inbox UI. They do not trigger matching.

For a given unmatched surface string `s`:

1. Pull all canonical entities of matching type (small dataset in practice).
2. For each candidate entity `c`, compute score components:
   - `exact_prefix`: boolean; `s` or a token of `s` prefixes canonical or alias.
   - `token_overlap`: Jaccard overlap of whitespace-tokenized lower forms.
   - `edit_distance_ratio`: normalized Levenshtein against canonical and aliases; take best.
3. Weighted composite:
   - `score = 0.3 * exact_prefix + 0.35 * token_overlap + 0.35 * (1 - min_edit_distance_ratio)`
4. Keep top N (default N=5) with score above a minimum threshold (default 0.35).
5. Serialize as JSON list in `candidate_matches_json`:

```json
[
  {
    "entity_id": 7,
    "canonical_name": "Sam Chen",
    "score": 0.72,
    "signals": {
      "exact_prefix": true,
      "token_overlap": 0.5,
      "edit_distance_ratio": 0.25
    }
  }
]
```

If no candidates pass the threshold, store `[]`.

Never use these scores to auto-merge; they only inform the UI ordering and badge display.

---

## 11) Linking mentions/events to `life_events`

Extraction items include an optional `linked_event_hint`. Step 3 must attempt to map it to a concrete `life_events.id` for the same `entry_date`:

Algorithm:
1. Build a lookup of the same-date `LifeEvent` rows by:
   - `description` (exact).
   - `source_snippet` (exact).
2. Normalize `linked_event_hint` similarly.
3. Try exact match first; if none, use token overlap ratio ≥ 0.5 against description + source_snippet concatenation.
4. If a single best match is found, use its `id`.
5. If none found or ambiguous, leave `life_event_id = NULL`. This is acceptable; mention/event/proposal still persists by `entry_date`.

Nullable link never blocks resolution. Logs warn once per unmatched hint.

---

## 12) Project status inference (Q3)

Triggered only when the project was matched to an existing `projects` row.

Inputs:
- Extracted `event_type` (`progress`, `milestone`, `setback`, `reflection`, `start`, `pause`).
- Extracted `suggested_project_status` (`ACTIVE`, `PAUSED`, `COMPLETED`, `ABANDONED` or null).
- Current `projects.status`.

Decision table:

| event_type | suggested_status | Current status | New status |
|------------|------------------|----------------|------------|
| start      | ACTIVE / null    | any            | ACTIVE     |
| pause      | PAUSED / null    | ACTIVE         | PAUSED     |
| milestone  | COMPLETED        | not COMPLETED  | COMPLETED  |
| milestone  | null or other    | any            | unchanged  |
| progress   | any              | PAUSED         | ACTIVE     |
| progress   | any              | non-PAUSED     | unchanged  |
| setback    | ABANDONED        | any            | ABANDONED  |
| setback    | null or other    | any            | unchanged  |
| reflection | any              | any            | unchanged  |

Rules:
- A status transition is only persisted if it differs from the current value.
- All transitions should log at info level for observability.
- Never overwrite a user-manual status change within a recency window — **Step 10 owns** a "last_manual_status_change_at" metadata field if we need it. For Step 3 MVP, always apply inference; Step 10 UI is expected to be the corrective surface until more nuanced policies are needed.

Note: This simple model is intentional. It's a starting policy. Later we can refine without schema change.

---

## 13) Aggregate maintenance

For every person that gets at least one new `person_mentions` row in the current entry:
- Increment `people.mention_count`.
- Update `people.last_seen_date` to `max(last_seen_date, entry_date)`.
- If `people.first_seen_date` is null or greater than `entry_date`, set to `entry_date`.

For every project that gets at least one new `project_events` row:
- Increment `projects.mention_count`.
- Update `projects.last_seen_date` similarly.
- Update `projects.first_seen_date` similarly.

Re-run consideration: because we **delete** prior `person_mentions`/`project_events` for the date before rebuilding (Q4), the increment during a re-run would double-count without compensation. To keep counts accurate under re-shred:

- Before re-building for `entry_date`, count deleted rows per entity and decrement `mention_count` accordingly.
- After rebuilding, increment as above.
- Recompute `last_seen_date` and `first_seen_date` by a bounded query against the remaining mentions/events for that entity (not by naive diff).

Implementation detail:
- For simplicity and correctness at V2 MVP, treat aggregates as **derived values recomputed at resolution time**:
  - `mention_count` = `SELECT count(*) FROM person_mentions WHERE person_id = ?` (likewise for projects).
  - `first_seen_date` = min of mention/event dates for entity.
  - `last_seen_date` = max of mention/event dates for entity.
- Only touch entities affected by this run (no global recompute).

This removes drift risk across repeated re-shreds.

---

## 14) Shredder integration

Changes required in `backend/app/services/shredder.py`:

1. After persisting `life_events` and `journal_reflections` but before `await db.commit()`:
   - Flush to ensure `LifeEvent.id`s exist.
   - Collect the persisted rows for `entry_date`.
   - Call `resolve_entry(db, entry_date, life_events=flushed_rows, extraction=extraction)`.
2. Expose counts returned from resolution in `EntryResult`:
   - `person_mentions_created`
   - `project_events_created`
   - `person_proposals_created`
   - `project_proposals_created`
3. Bump `shredder_version` to `v2.2` after Step 3 integration ships (new contract end-to-end).

Transaction behavior:
- Resolution runs inside the same async session as shred.
- Any exception in resolution rolls back the entire per-entry transaction (life events, reflections, mentions, proposals).
- This preserves Q4 atomicity: either the date's entire V2 footprint is rewritten, or none of it is.

---

## 15) ResolutionResult type

```python
@dataclass
class ResolutionResult:
    person_mentions_created: int = 0
    project_events_created: int = 0
    person_proposals_created: int = 0
    project_proposals_created: int = 0
    project_status_transitions: int = 0
    skipped_blocked: int = 0
    errors: list[str] = field(default_factory=list)
```

Shredder and operations tooling (Step 6) can log or surface these.

---

## 16) Idempotency guarantees

Running resolution twice on the same entry without changes to extraction should produce the same DB state:
- Clean-slate deletion of per-date `person_mentions`, `project_events`, and pending proposals ensures deterministic rebuild.
- Aggregate recompute avoids drift.
- Blocklist filtering is stable across runs.

Accepted or merged proposals from prior runs are **preserved** — they represent user decisions and should not be recreated as pending.

When a user previously merged `"Sam"` into `Sam Chen`, the current run will simply match via alias and skip proposal creation.

---

## 17) Observability

Logs per entry at info level:
- Counts produced (mentions, events, proposals, status transitions).

Logs per item at debug level:
- Chosen match type (canonical, alias, ambiguous→proposal, blocked, no-match).
- Candidate ranking for unmatched items.
- Status inference decision (old → new).

Logs at warning level:
- Unresolvable `linked_event_hint` hits.
- Unknown `event_type` / `project_status` tokens from Gemini (dropped with warning).

---

## 18) Testing plan

### Unit tests (`entity_resolution` module)

- `_normalize_surface`: whitespace collapse, punctuation trim, length cap, empty rejection.
- Exact canonical matcher: case-insensitive.
- Alias matcher: single/multiple candidate behavior.
- Candidate ranking: scoring function correctness and thresholding.
- Status inference decision table coverage.

### Integration tests (synthetic journals)

Seed an in-memory DB with:
- One `people` row: `Sam Chen` with alias `Sam`.
- One `projects` row: `Portuguese` in status `ACTIVE`.
- One `entity_blocklist` entry for a noisy string like `the team`.

Execute `resolve_entry` against fabricated extraction payloads that include:
- `Sam` → expect 1 `person_mentions` row, no proposal.
- `Samuel` → expect 1 `pending` person proposal, candidate rank includes `Sam Chen`.
- `the team` → expect nothing (blocked).
- `Portuguese` start event with `suggested_project_status=ACTIVE` → expect 1 `project_events`, no status change.
- `Portuguese` milestone with `suggested_project_status=COMPLETED` → expect 1 `project_events`, status transitions `ACTIVE → COMPLETED`.

### Re-run idempotency

- Run resolution on the same fabricated date twice.
- Assert: same row counts, no orphan rows, aggregates stable, prior `accepted_new` proposals still present.

### Q4 re-shred interaction

- Simulate:
  1. Shred + resolve date `D` with extraction A.
  2. Re-shred + resolve date `D` with extraction B (different people).
- Assert: no `person_mentions`/`project_events` from extraction A remain; pending proposals from A are replaced; `accepted_new` historical proposals from A (if any) are preserved.

---

## 19) Rollout / migration notes

- Step 3 integration is opt-in initially via a feature flag `RESOLUTION_ENABLED` (default true in dev, false in any rollback scenario).
- If disabled, shredder behaves exactly as Step 2 end state.
- Backfill (Step 6) will re-shred + resolve the entire journal corpus once Step 3 is stable.

---

## 20) Dependencies

- **Reads normative detail from:**
  - Step 0 — conventions, Q4 transaction safety.
  - Step 1 — schema for `people`, `projects`, `person_mentions`, `project_events`, `entity_proposals`, `entity_blocklist`.
  - Step 2 — extraction JSON contract (`people_mentioned`, `project_events`, `linked_event_hint`, `suggested_project_status`).
- **Feeds:**
  - Step 4 — proposal rows are ready to drive inbox API.
  - Step 7 — confirmed mentions/events populate widgets.
  - Step 10 — canonical entities gain lifecycle rows.

---

## 21) Definition of done

Step 3 is complete when:

- `entity_resolution.py` exists and is integrated into the per-entry shred flow.
- Running shred on a fresh V2 journal corpus produces:
  - `person_mentions` / `project_events` for matched entities.
  - `entity_proposals` rows for unmatched entities.
  - Zero canonical `people` / `projects` rows auto-created.
- Blocklist suppresses repeat noise.
- Project status inference obeys Q3 decision table.
- Aggregates remain correct under repeated re-shreds on the same date.
- Unit + integration tests pass.

---

## Changelog

- 2026-04-22 — Initial complete Step 3 spec drafted against Step 1 schema and Step 2 extraction contract. Defines resolution service module, matching rules, proposal creation, ranking algorithm, status inference table, aggregate maintenance policy, and shredder integration.
