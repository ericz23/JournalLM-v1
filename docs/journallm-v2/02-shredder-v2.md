# Step 2 — Shredder V2

**Index:** [README.md](./README.md)  
**Plan reference:** [JOURNALLM_V2_IMPLEMENTATION_PLAN.md](../../JOURNALLM_V2_IMPLEMENTATION_PLAN.md)  
**Status:** Complete (spec baseline ready for implementation)  
**Ideation refs:** §1.4, §1.5, Locked Q1, Q3, Q4.

---

## 1) Scope

### In scope

- Define the V2 extraction contract returned by Gemini for one journal entry.
- Define prompt updates needed for:
  - sentiment labels (not float in persisted output),
  - `people_mentioned`,
  - `project_events`,
  - optional project status suggestion.
- Define per-entry shred flow and transaction semantics aligned with Q4 full re-extract.
- Define staging payload shape that Step 3 consumes for resolution/proposal generation.
- Define API output compatibility expectations for existing shredder endpoints.

### Out of scope

- Matching/merge logic for people and projects (Step 3).
- Inbox action API and state transitions (Step 4).
- UI changes (Step 5+).

---

## 2) Current state snapshot (as of Step 1 implementation)

Current `backend/app/services/shredder.py` behavior:
- Extracts `life_events` + `reflections` only.
- Still asks LLM for float `sentiment_score` but maps to enum for DB writes.
- Writes:
  - `life_events` (with enum sentiment),
  - `journal_reflections`,
  - `journal_entries.processed_at`,
  - `journal_entries.shredder_version = "v2.0"`.
- Full re-extract semantics already exist for `life_events` and `journal_reflections`.

Gap to close in Step 2:
- Add extraction output for people/project structures.
- Introduce staged persistence contract so Step 3 can resolve/confirm.
- Update prompt language to output categorical sentiment directly.

---

## 3) Locked decisions applied

- **Q1:** Shredder can propose people/projects but cannot auto-create canonical rows.
- **Q3:** Shredder may suggest project status updates; resolution layer applies final status.
- **Q4:** Re-shred replaces per-date derived rows and remains idempotent/safe.

---

## 4) V2 extraction contract (Gemini JSON schema)

`ExtractionResponseV2` (single-entry payload) must include:

- `life_events: list[ExtractedEventV2]`
- `reflections: list[ExtractedReflection]`
- `people_mentioned: list[ExtractedPersonMention]`
- `project_events: list[ExtractedProjectEvent]`

### 4.1 `ExtractedEventV2`

Fields:
- `category: str` (same category set as V1)
- `description: str`
- `metadata: EventMetadata`
- `sentiment: "POSITIVE" | "NEGATIVE" | "NEUTRAL"` (preferred)
- `source_snippet: str`

Compatibility fallback:
- During migration period, if model returns legacy `sentiment_score`, app maps to enum using Step 0 thresholds.

### 4.2 `ExtractedReflection`

Unchanged:
- `topic`, `content`, `is_actionable`.

### 4.3 `ExtractedPersonMention`

Fields:
- `name: str` (surface string from journal, e.g. "Sam")
- `relationship_hint: str | null` (friend/colleague/family/client/etc, if inferable)
- `interaction_context: str | null` (short supporting snippet)
- `linked_event_hint: str | null` (optional textual hook to help Step 3 map to `life_event_id`)
- `sentiment: "POSITIVE" | "NEGATIVE" | "NEUTRAL" | null`

Notes:
- This is a mention candidate, not canonical person identity.

### 4.4 `ExtractedProjectEvent`

Fields:
- `project_name: str` (surface string, e.g. "Portuguese")
- `event_type: "progress" | "milestone" | "setback" | "reflection" | "start" | "pause"`
- `description: str`
- `linked_event_hint: str | null`
- `suggested_project_status: "ACTIVE" | "PAUSED" | "COMPLETED" | "ABANDONED" | null`

Notes:
- `suggested_project_status` is advisory for Step 3; user override remains authoritative (Q3).

---

## 5) Prompt contract changes

## 5.1 System instruction goals

The system prompt must explicitly instruct:
- Atomic event extraction remains first-class.
- Sentiment output should be **categorical label**, not float.
- Extract **people mentions** separately from life events.
- Extract **project events** separately from life events.
- Provide optional status suggestion only when text clearly indicates lifecycle transition.

## 5.2 Required hard rules in prompt

- Never infer canonical identity; only output observed name strings.
- Never infer project existence globally; only output per-entry project event mentions.
- Use exact enums for sentiment/event types/status values.
- Keep `source_snippet`/context snippets near-verbatim and concise.
- Return strict JSON object matching schema.

## 5.3 Temperature and output mode

- Keep `temperature=0.2`.
- Keep `response_mime_type="application/json"`.
- Keep typed schema binding via Pydantic response model.

---

## 6) Shredder processing flow (per entry)

1. Start per-date shred transaction context.
2. Clear existing per-date derived rows:
   - `life_events`
   - `journal_reflections`
   - (via FK cascade, old proposal links tied to removed events may fall away; Step 3 rebuilds new links)
3. Call Gemini with V2 schema.
4. Persist:
   - `life_events` (enum sentiment),
   - `journal_reflections`.
5. Persist **staging payload** for Step 3:
   - either inline in memory return object from shred call, or
   - persisted row-level JSON for Step 3 consumption in same run.
   - Preferred for current architecture: keep in-process object and call Step 3 service immediately after extraction.
6. Set:
   - `processed_at = now()`
   - `shredder_version = "v2.1"` (or agreed V2 schema version string)
7. Commit.

Error path:
- rollback entire per-date transaction.
- return per-entry error in `ShredderResult.entries`.

---

## 7) Data write boundaries for Step 2 vs Step 3

To preserve Q1:
- Step 2 **does not** write canonical `people`/`projects`.
- Step 2 may write only:
  - `life_events`,
  - `journal_reflections`,
  - optional raw staging artifacts if needed (implementation detail).

Step 3 owns:
- Matching against existing canonical entities,
- Creating `person_mentions` / `project_events` rows,
- Creating `entity_proposals` for unresolved items,
- Applying inferred project status updates.

---

## 8) API compatibility notes

Existing endpoints (`/api/shredder/run`, `/results/{entry_date}`) should remain available.

Recommended compatibility behavior:
- Keep existing `life_events` and `reflections` response fields.
- Add optional fields (non-breaking):
  - `people_mentioned` (from latest extraction context if available),
  - `project_events` (from latest extraction context if available).

If not adding immediately in Step 2 code, document as deferred to Step 3/4 integration.

---

## 9) Validation and coercion rules

Required app-side coercions:
- Unknown `category` -> `PERSONAL`.
- Unknown `event_type` -> drop item with warning (do not crash whole entry).
- Unknown sentiment string -> null + warning.
- All snippet fields truncated to storage limits (`source_snippet` <= 500).
- Topic truncation remains at 200 chars.

Do not silently coerce invalid project status to ACTIVE in Step 2; keep null and let Step 3 infer/fallback.

---

## 10) Testing plan (Step 2)

### Unit tests
- Pydantic parsing for full V2 response shape.
- Sentiment label coercion and fallback from legacy float payload.
- Invalid enum handling (logs + skip behavior).

### Integration tests
- Single entry shred writes life events/reflections and updates `shredder_version`.
- Re-shred same date replaces prior rows (Q4 behavior preserved).
- Failure in Gemini call leaves DB unchanged for that date.

### Golden fixture tests

Use 3 synthetic entries:
- **Social-heavy day**: multiple people mentions + dietary/social split.
- **Project-heavy day**: multiple project events + status suggestion.
- **Low-signal day**: minimal events, no people/project extraction.

Assertions:
- JSON contract shape stable.
- Deterministic category/event_type enums.
- Snippets and metadata fields populated when present.

---

## 11) Rollout / migration notes

- Step 2 can be shipped behind internal flag `SHREDDER_SCHEMA_VERSION=v2` if desired.
- For local-first development, direct cutover is acceptable once Step 3 implementation is ready.
- Backfill:
  - Re-shred date ranges using Q4 full replacement.
  - Ensure Step 3 runs after each entry to populate proposals/mentions/events.

---

## 12) Dependencies

- **Reads from Step 0:** versioning semantics, sentiment policy, Q4 transaction expectations.
- **Reads from Step 1:** table/enums available for downstream resolution path.
- **Feeds Step 3:** staged people/project extraction payloads and optional status signals.

---

## 13) Definition of done

Step 2 is complete when:
- Shredder prompt and schema produce V2 payload with `people_mentioned` and `project_events`.
- Shredder persists life events/reflections with enum sentiment only.
- `shredder_version` is updated per successful entry.
- Re-shred behavior remains full-replace and transaction-safe.
- Step 2 tests (unit/integration/golden fixtures) pass.

---

## Changelog

- 2026-04-22 — Initial complete Step 2 spec drafted based on V2 implementation plan, Step 0 conventions, and Step 1 completed schema/migration work.
