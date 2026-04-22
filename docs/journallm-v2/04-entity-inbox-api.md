# Step 4 — Entity inbox API (backend)

**Index:** [README.md](./README.md)  
**Plan reference:** [JOURNALLM_V2_IMPLEMENTATION_PLAN.md](../../JOURNALLM_V2_IMPLEMENTATION_PLAN.md)  
**Status:** Complete (spec baseline ready for implementation)  
**Ideation refs:** §1.5, Locked Q1, Q2, Q3.

---

## 1) Scope

### In scope

- Read endpoints to list/fetch `entity_proposals` with filters and precomputed candidate merge scores.
- Write endpoints that apply the Q1 user actions:
  - Person: confirm new, merge into existing, dismiss, blocklist.
  - Project: confirm new, merge into existing, reject (with optional dismiss/blocklist modes).
- Transactional replay of dedup'd proposal payloads into `person_mentions` / `project_events` when a proposal is accepted.
- Auto-cascade of pending proposals across all dates that share the same surface string.
- Aggregate recompute on the affected canonical entity after each action.
- Minimal blocklist CRUD needed to unblock surfaces from the inbox.
- Idempotency semantics and conflict handling for already-resolved proposals.

### Out of scope

- Inbox UI routes/components (Step 5).
- Full People/Projects CRUD (canonical name edits, relationship_type forms, notes, etc. — Step 10).
- Dashboard surfacing of confirmed entities (Step 7/8).
- Bulk reshred from the UI; only per-proposal actions here (backfill triggers live in Step 6).

---

## 2) Dependencies

- **Reads normative detail from:**
  - Step 0 — conventions, enum definitions, API naming.
  - Step 1 — schema for `entity_proposals`, `entity_blocklist`, `people`, `projects`, `person_mentions`, `project_events`.
  - Step 3 — resolution service (used as helper for payload replay, candidate recompute on cascade, and aggregate recompute).
- **Feeds:**
  - Step 5 — inbox UI calls these endpoints.
  - Step 6 — backfill script can observe proposal resolution outcomes.
  - Step 10 — confirmed canonical entities become editable in People/Projects pages.

---

## 3) Router layout

New module: `backend/app/routes/entity_inbox.py`.

Registered under `app.main` as:

```python
app.include_router(entity_inbox.router, prefix="/api")
```

Route groups (same file):

- `/api/entity-proposals/*`
- `/api/entity-blocklist/*`

Tag: `"entity-inbox"`.

All endpoints return JSON, use async SQLAlchemy sessions via `Depends(get_db)`, and follow the existing `backend/app/routes/shredder.py` style:
- Top-level Pydantic `BaseModel` schemas inside the file.
- No auth — single-user personal tool.
- `HTTPException` with `404` for missing rows, `409` for conflict on already-resolved proposals, `400` for validation errors.

---

## 4) Shared response schemas

```python
class CandidateMatch(BaseModel):
    entity_id: int
    canonical_name: str
    score: float
    signals: dict  # exact_prefix, token_overlap, edit_distance_ratio

class ProposalSummary(BaseModel):
    id: int
    entity_type: Literal["person", "project"]
    status: Literal["pending", "accepted_new", "merged_existing", "dismissed", "rejected", "blocked"]
    surface_name: str
    entry_date: date
    life_event_id: int | None
    created_at: datetime
    resolved_at: datetime | None

class ProposalDetail(ProposalSummary):
    payload: dict  # parsed payload_json
    candidate_matches: list[CandidateMatch]
    resolution_entity_id: int | None
    resolution_note: str | None

class BlocklistEntry(BaseModel):
    id: int
    entity_type: Literal["person", "project"]
    surface_name: str
    reason: Literal["manual_block", "system_noise"] | None
    created_at: datetime
```

Parsing of `payload_json` and `candidate_matches_json` is centralized in a helper so clients never see raw JSON strings.

---

## 5) Read endpoints

### 5.1 `GET /api/entity-proposals`

**Query parameters (all optional):**

| Name | Type | Default | Notes |
|------|------|---------|-------|
| `status` | enum or list | `pending` | Any of `pending`, `accepted_new`, `merged_existing`, `dismissed`, `rejected`, `blocked`. |
| `entity_type` | enum | all | `person` or `project`. |
| `entry_date_from` | date | — | Inclusive. |
| `entry_date_to` | date | — | Inclusive. |
| `search` | string | — | Case-insensitive contains match on `surface_name`. |
| `limit` | int | 50 | Max 200. |
| `offset` | int | 0 | |

**Response:** `{"total": int, "items": list[ProposalSummary]}`.

Ordering: `entry_date DESC`, `created_at DESC`, `id DESC`.

### 5.2 `GET /api/entity-proposals/{id}`

**Response:** `ProposalDetail`.

Errors: `404` if not found.

### 5.3 `GET /api/entity-proposals/summary`

Supports the inbox badge on the dashboard nav.

**Response:**

```json
{
  "pending_person": 4,
  "pending_project": 2,
  "total_pending": 6,
  "oldest_pending_entry_date": "2026-10-25"
}
```

### 5.4 `GET /api/entity-blocklist`

**Response:** `list[BlocklistEntry]`, ordered `entity_type ASC, surface_name ASC`.

Query filters: `entity_type` optional.

---

## 6) Action endpoints (person proposals)

All actions share the same preconditions and post-conditions unless noted:

- **Precondition:** target proposal exists and has `status == pending`.
  - On `status != pending`: `409 Conflict` with body `{"detail": "proposal already resolved", "current_status": "..."}`.
- **Transaction:** one DB transaction per action. On any exception, the entire action rolls back.
- **Post-condition:** proposal row gets `status`, `resolution_entity_id`, `resolution_note`, `resolved_at = now()`.
- **Aggregates:** `_recompute_person_aggregates(db, person_id)` from Step 3 is invoked at the end on any affected canonical person.

### 6.1 `POST /api/entity-proposals/{id}/actions/confirm-new`

Create a new `people` row and attach all mentions in the proposal payload.

**Request body:**

```python
class ConfirmNewPersonBody(BaseModel):
    canonical_name: str               # defaults to surface_name if omitted — treat empty/null as "use surface"
    aliases: list[str] = []           # extra aliases beyond surface_name
    relationship_type: str | None = None
    notes: str | None = None
```

**Behavior:**

1. Validate `entity_type == person`.
2. If a `people` row with `LOWER(canonical_name) == LOWER(body.canonical_name)` already exists → `409` with `{"detail": "person with canonical_name already exists", "existing_id": N}`. The UI should switch to merge flow.
3. Create `people` row. `aliases_json` = JSON of the union `{surface_name} ∪ aliases` (case-preserving, de-duped by `lower()`), minus `canonical_name` itself.
4. Seed `first_seen_date = last_seen_date = proposal.entry_date`, `mention_count = 0` (aggregates recompute at end).
5. **Replay payload (§9).**
6. Mark proposal `accepted_new`; `resolution_entity_id = new person.id`; `resolution_note = "confirmed new"`.
7. **Cascade (§10)** across other pending person proposals matching the new person.
8. Recompute aggregates on the new person.

**Response:** the new `ProposalDetail` plus:

```python
class ActionResult(BaseModel):
    proposal: ProposalDetail
    entity_id: int
    mentions_created: int       # for person actions
    events_created: int = 0     # for project actions
    cascaded_proposal_ids: list[int] = []
```

### 6.2 `POST /api/entity-proposals/{id}/actions/merge-existing`

Attach the proposal's mentions to an existing `people` row and optionally add the surface as an alias.

**Request body:**

```python
class MergePersonBody(BaseModel):
    target_entity_id: int
    add_alias: bool = True           # default True — add surface_name as alias
    extra_aliases: list[str] = []    # additional aliases user typed
```

**Behavior:**

1. Validate `entity_type == person`.
2. Load target `people` row or `404`.
3. If `add_alias`: union `target.aliases_json` with `{surface_name} ∪ extra_aliases`, de-duped by `lower()`, excluding `canonical_name`.
4. **Replay payload (§9).**
5. Mark proposal `merged_existing`; `resolution_entity_id = target_entity_id`; `resolution_note = "merged into {target.canonical_name}"`.
6. **Cascade (§10).**
7. Recompute aggregates on the target person.

**Response:** `ActionResult`.

### 6.3 `POST /api/entity-proposals/{id}/actions/dismiss`

One-time dismissal without blocklist.

**Request body:**

```python
class DismissBody(BaseModel):
    note: str | None = None
```

**Behavior:**

- Mark proposal `dismissed`; `resolution_entity_id = None`; `resolution_note = body.note`.
- **No** cascade.
- **No** rows written to `person_mentions` or `entity_blocklist`.

Future runs may re-propose this surface (consistent with §1.5 "one-time dismiss").

### 6.4 `POST /api/entity-proposals/{id}/actions/blocklist`

Dismiss **and** register surface string on the blocklist.

**Request body:**

```python
class BlocklistBody(BaseModel):
    reason: Literal["manual_block", "system_noise"] = "manual_block"
    note: str | None = None
    cascade_pending: bool = True
```

**Behavior:**

1. Upsert `entity_blocklist(entity_type, surface_name)` — unique constraint already exists; on conflict just update `reason` if provided.
2. Mark this proposal `blocked`; `resolution_note = body.note or reason`.
3. If `cascade_pending`: **all other pending** proposals of the same `entity_type` where `LOWER(surface_name) == LOWER(current.surface_name)` are also marked `blocked` with `resolution_note = "auto-cascaded from proposal #{id}"`.
4. **No** `person_mentions` created.

---

## 7) Action endpoints (project proposals)

Same preconditions and transactional semantics as person actions. Status inference (Q3) runs during payload replay (§9.2).

### 7.1 `POST /api/entity-proposals/{id}/actions/confirm-new`

**Request body:**

```python
class ConfirmNewProjectBody(BaseModel):
    name: str                          # defaults to surface_name if omitted
    aliases: list[str] = []
    category: str | None = None
    status: Literal["ACTIVE", "PAUSED", "COMPLETED", "ABANDONED"] | None = None
    description: str | None = None
    target_date: date | None = None
```

**Behavior:**

1. Validate `entity_type == project`.
2. Conflict on duplicate name (case-insensitive) → `409`, `{"existing_id": N}`.
3. Create `projects` row. Initial `status = body.status or ACTIVE`.
4. **Replay payload (§9.2)** — creates `project_events` rows and applies Q3 status inference on top of the user-set initial status.
5. Mark proposal `accepted_new`; cascade; recompute aggregates.

### 7.2 `POST /api/entity-proposals/{id}/actions/merge-existing`

**Request body:**

```python
class MergeProjectBody(BaseModel):
    target_entity_id: int
    add_alias: bool = True
    extra_aliases: list[str] = []
```

Same merge pattern as person 6.2, but:
- Replay creates `project_events` rows.
- Status inference applies and **may** transition the target's status — matching Q3. User's manual UI override (Step 10) is authoritative but simply replaces via PATCH later.

### 7.3 `POST /api/entity-proposals/{id}/actions/reject`

Project-specific action for "not a project."

**Request body:**

```python
class RejectProjectBody(BaseModel):
    mode: Literal["dismiss", "blocklist"] = "dismiss"
    note: str | None = None
```

**Behavior:**

- Always: mark proposal `rejected`; **no** `projects` row created; **no** `project_events` written.
- `mode == dismiss`: no blocklist addition. Cascade **not** applied (one-time).
- `mode == blocklist`: upsert `entity_blocklist(project, surface_name)`. Cascade all other pending project proposals with the same lowercased `surface_name` to `rejected` (note: cascaded proposals also get status `rejected`, not `blocked` — the blocklist row itself is the durable signal).

### 7.4 `POST /api/entity-proposals/{id}/actions/dismiss`

Same shape as 6.3 but for project proposals. Mirror behavior.

### 7.5 `POST /api/entity-proposals/{id}/actions/blocklist`

Same shape as 6.4 but for project proposals. Same behavior; sets status `blocked` (not `rejected`) for consistency with person blocklist flow and to keep "intentional noise" distinct from "not a project this time."

---

## 8) Blocklist management

### 8.1 `DELETE /api/entity-blocklist/{id}`

Remove a blocklist entry so the surface can be proposed again. `204 No Content` on success; `404` if missing.

### 8.2 `POST /api/entity-blocklist`

Admin-style create not required in Step 4. Surfaces land on the blocklist only via action endpoints (§6.4, §7.3 blocklist mode, §7.5). Documented here as explicitly **not** part of V2 ship.

---

## 9) Payload replay

When a proposal is **accepted** (confirm-new or merge-existing), the stored `payload_json` must be expanded back into row-level writes.

### 9.1 Person replay

`payload = {"mentions": [item, item, ...]}` where each item has `name`, `relationship_hint`, `interaction_context`, `linked_event_hint`, `sentiment`.

For each item:
- `person_id = resolved_person.id`.
- `entry_date = proposal.entry_date`.
- `life_event_id`: prefer `proposal.life_event_id` if set; otherwise attempt re-linking via the Step 3 helper `_pick_linked_event(item.linked_event_hint, events_on_entry_date)`. If still null, leave null.
- `context_snippet = item.interaction_context[:500]` or `None`.
- `sentiment = _coerce_sentiment(item.sentiment)`.

If a matching `person_mentions` row already exists for `(person_id, entry_date, life_event_id, context_snippet)`, skip insert to keep replay idempotent in the event of retry.

### 9.2 Project replay

`payload = {"events": [item, ...]}` where each item has `project_name`, `event_type`, `description`, `linked_event_hint`, `suggested_project_status`.

For each item:
- Validate `event_type` via `_coerce_event_type`; skip if invalid (log warning).
- Create `project_events` row.
- Feed into a per-action status-inference accumulator: start from `project.status`, apply `_infer_next_status` per item in order, persist the final status.

### 9.3 Shared helpers

The replay logic is extracted to `entity_inbox_service.py` (same `services/` directory) and reuses:
- `entity_resolution._pick_linked_event`
- `entity_resolution._coerce_sentiment`
- `entity_resolution._coerce_event_type`
- `entity_resolution._coerce_project_status`
- `entity_resolution._infer_next_status`
- `entity_resolution._recompute_person_aggregates`
- `entity_resolution._recompute_project_aggregates`

These are already defined and should be left module-private but imported explicitly by the inbox service (no cross-module mutation).

---

## 10) Cascade semantics

**Motivation:** when the user confirms "Samuel" as a new person (or merges it into an existing one), any *other* pending proposals across any date whose `surface_name` is `Samuel` should auto-resolve to the same canonical entity. Otherwise the inbox keeps nagging the user for every date that mentioned the same person pre-confirmation.

### 10.1 Cascade scope

Applied on these actions:
- Person `confirm-new`, `merge-existing`.
- Project `confirm-new`, `merge-existing`.

**Not** applied on: `dismiss`, `reject (mode=dismiss)`. Applied on `blocklist` and `reject (mode=blocklist)` to silence future proposal noise consistently.

### 10.2 Cascade query

For an accept-style action resolving to canonical entity E via surface S:

```sql
SELECT * FROM entity_proposals
WHERE entity_type = :entity_type
  AND status = 'pending'
  AND id != :current_proposal_id
  AND (
    LOWER(surface_name) = LOWER(:S)
    OR LOWER(surface_name) IN (LOWER(a) for a in E.aliases union {E.canonical_name})
  );
```

In Python, load all pending proposals of matching type and filter in-memory using the same normalization as Step 3.

### 10.3 Cascade resolution

For each cascaded proposal P2:
1. Replay its payload (§9) into mentions/events on entity E.
2. Mark P2 status:
   - For person/project accept actions → `merged_existing` with `resolution_entity_id = E.id`, `resolution_note = "auto-cascaded from proposal #{current_id}"`.
   - For blocklist/reject-with-blocklist → `blocked` (person) or `rejected` (project).
3. Record P2.id in the `ActionResult.cascaded_proposal_ids` list returned to the client.

Aggregates are recomputed once at the end after all cascades complete.

### 10.4 Bounded cascade size

If cascaded set size exceeds 200, cap at 200 and include a `cascade_truncated: true` field in the response. In practice single-user journals will not hit this; the cap prevents runaway costs if the user bulk-resolves months of corpus.

---

## 11) Idempotency, conflicts, and errors

### 11.1 Already-resolved proposal

If `status != pending` on entry:
- Return `409` with `current_status` and `resolved_at` in the body.
- No writes performed.

### 11.2 Concurrent action attempts

Single-user dev app: we assume no true concurrency. As a light safeguard the action handlers re-select the proposal with `WITH ROWS FOR UPDATE` equivalent (SQLAlchemy `with_for_update()`) where supported, then re-check status before proceeding. SQLite does not support row-level locking; in practice the per-request async session provides enough isolation for a single user, and we rely on the up-front status check.

### 11.3 Validation errors

Return `400` with `{"detail": "..."}` for:
- Empty `canonical_name` / `name` after trim.
- Duplicate aliases colliding with another entity's canonical_name (for project merge-existing that would pull the project's primary name into aliases).
- Unknown `target_entity_id` → prefer `404` over `400`.

### 11.4 Replay failure isolation

If any single payload item fails to replay (e.g. malformed `event_type`), log a warning and skip that item; do **not** fail the entire action unless **all** items fail. Include `warnings: list[str]` in `ActionResult` response.

---

## 12) Observability

Per-action `INFO` log line:

```
proposal #{id} resolved entity_type={person|project} action={confirm_new|merge_existing|dismiss|blocklist|reject} target={entity_id|none} cascade={n} mentions_or_events={n}
```

Per-cascade `DEBUG` log line per auto-resolved proposal.

On any `409`/`400`/`404`: `WARNING` with the path, proposal id, and reason.

---

## 13) Testing plan

### 13.1 Unit tests (service layer)

- Alias normalization/dedup within body → no duplicate entries in `aliases_json`.
- Replay person payload: single item, multiple items, partial invalid items.
- Replay project payload: verifies each event writes, status transitions match decision table after whole batch.
- Cascade candidate selector: matches by surface_name and by alias set, excludes self and non-pending.

### 13.2 Integration tests (FastAPI TestClient over in-memory SQLite)

- **Confirm new person** with 3 pending proposals for "Samuel" on different dates → all three become `merged_existing` with cascade; 3 `person_mentions` rows created; aggregates correct.
- **Merge existing person**: existing `Sam Chen` with alias `Sam`. Proposal surface `Samuel`. User merges with `add_alias=True` → Person.aliases now includes `Samuel`; proposal resolved; a later re-shred of another date that contains `Samuel` now **matches deterministically** (tests Step 3 round-trip).
- **Dismiss**: one pending proposal for `"The Team"` → status `dismissed`, no mentions, no blocklist row, other pending proposals untouched.
- **Blocklist**: `"The Team"` → `entity_blocklist` row created, current proposal `blocked`, all other pending same-surface proposals `blocked`.
- **Project confirm-new with status override**: body sets `status=PAUSED`, replay contains one `start` event. Final status should be `ACTIVE` (inference overrides user init because replay sequence runs after — *or* we document reverse policy). **Decision:** user-provided `status` is the starting point for inference; inference then runs. So final = `_infer_next_status(PAUSED, start, None) == ACTIVE`. Capture this in the test as the contract.
- **Project reject with blocklist**: proposal `"random topic"` rejected in blocklist mode → proposal status `rejected`, blocklist row exists, cascade applied across other dates with same surface set to `rejected`.
- **Already resolved**: POST any action to a `merged_existing` proposal → `409`.
- **Unknown target**: merge-existing with `target_entity_id=99999` → `404`.

### 13.3 Re-shred interaction

After a user confirms a new person, re-shred an existing entry whose text contains that person's surface → Step 3 now matches deterministically → no new pending proposal created for that date. Test guards against regression if cascade does not correctly update aliases or status.

---

## 14) Rollout / feature flag

- No explicit runtime flag; the endpoints are live as soon as the router is included.
- If rollback is needed, comment out the `app.include_router(entity_inbox.router)` call in `app.main`. Data layer remains untouched.

---

## 15) Definition of done

Step 4 is complete when:

- `backend/app/routes/entity_inbox.py` exposes the endpoints in §5–§8.
- `backend/app/services/entity_inbox_service.py` holds the action/replay/cascade logic with Step 3 helpers reused.
- All integration tests in §13.2 pass against an in-memory SQLite fixture.
- Accepting proposals creates `people`/`projects` rows and `person_mentions`/`project_events` rows as specified.
- Cascade reliably closes duplicate pending proposals.
- `_recompute_*_aggregates` is invoked post-action so `mention_count`, `first_seen_date`, `last_seen_date` on the canonical entity are consistent.
- OpenAPI schema (auto-generated by FastAPI) renders without warnings.

---

## Changelog

- 2026-04-22 — Initial complete Step 4 spec. Defines router surface, per-action request/response shapes, payload replay contract, cascade rules, conflict/validation semantics, and testing matrix. Designed to reuse Step 3 helpers directly so resolution and inbox stay in lockstep on matching and status inference.
