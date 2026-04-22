# Step 1 — Database foundation

**Index:** [README.md](./README.md)  
**Plan reference:** [JOURNALLM_V2_IMPLEMENTATION_PLAN.md](../../JOURNALLM_V2_IMPLEMENTATION_PLAN.md)  
**Status:** Complete (spec baseline ready for implementation)  
**Ideation refs:** §1.1, §1.2, §1.4, §1.5, Locked Q1–Q4.

---

## 1) Scope

### In scope

- Define V2 schema additions for:
  - `people`
  - `person_mentions`
  - `projects`
  - `project_events`
  - `entity_proposals`
- Define required modifications to existing tables:
  - `journal_entries` (`shredder_version`)
  - `life_events` (float sentiment -> enum sentiment)
- Define FK/index strategy that preserves Q4 re-shred guarantees.
- Define migration order and rollback strategy.

### Out of scope

- Shredder prompt/content changes (Step 2).
- Resolution logic and matching algorithms (Step 3).
- API contracts for inbox actions (Step 4).
- UI behavior (Step 5+).

---

## 2) Locked decisions applied in this step

- **Q1:** New people/projects are proposal-driven. Schema must support pending proposals and explicit resolution states.
- **Q2:** Matching does not auto-merge. Schema supports candidate ranking metadata but not automatic canonical rewrites.
- **Q3:** Project status can be inferred later; schema must support lifecycle status.
- **Q4:** Re-shred is full replacement. FK structure must allow safe clear-and-rebuild per `entry_date`.

---

## 3) Target schema changes

## 3.1 Existing table modifications

### `journal_entries`

Add:
- `shredder_version` (`String(32)`, nullable initially, indexed optional)

Purpose:
- Track extraction contract that produced current derived rows (Step 0).

Notes:
- Keep nullable for backward compatibility during rollout.
- Backfill in operations step can set `v1.0` for legacy rows if needed.

### `life_events`

Replace:
- `sentiment_score` (`Float`) -> `sentiment` (`Enum`: `POSITIVE`, `NEGATIVE`, `NEUTRAL`)

Migration mapping (from Step 0):
- `score > 0.3` -> `POSITIVE`
- `score < -0.3` -> `NEGATIVE`
- otherwise -> `NEUTRAL`
- null -> null (nullable destination)

Compatibility rule:
- Do not keep both columns after migration completes; V2 contracts use enum only.

---

## 3.2 New core entity tables

### `people`

Columns:
- `id` INTEGER PK
- `canonical_name` String(200), unique, indexed
- `aliases_json` TEXT nullable (JSON array of strings)
- `relationship_type` String(50) nullable
- `notes` TEXT nullable
- `first_seen_date` DATE nullable (set when first confirmed mention linked)
- `last_seen_date` DATE nullable
- `mention_count` INTEGER not null default 0
- `created_at`, `updated_at` (TimestampMixin)

Indexes:
- unique(`canonical_name`)

Rationale:
- Keep alias storage local/simple in V2 MVP; normalize later if needed.

### `person_mentions`

Columns:
- `id` INTEGER PK
- `person_id` INTEGER FK -> `people.id` (ON DELETE CASCADE), indexed
- `entry_date` DATE FK -> `journal_entries.entry_date`, indexed
- `life_event_id` INTEGER FK -> `life_events.id` (ON DELETE CASCADE), nullable, indexed
- `context_snippet` String(500) nullable
- `sentiment` Enum(`POSITIVE`,`NEGATIVE`,`NEUTRAL`) nullable
- `created_at`, `updated_at` (or `created_at` only; for consistency prefer TimestampMixin)

Indexes:
- (`person_id`, `entry_date`)
- (`entry_date`)
- (`life_event_id`)

Constraints:
- `context_snippet` length capped by app validation.

Rationale:
- `life_event_id` nullable so mention can exist even if no single event mapping.

---

## 3.3 New project tables

### `projects`

Columns:
- `id` INTEGER PK
- `name` String(200), unique, indexed
- `aliases_json` TEXT nullable (JSON array, optional but recommended for Q2 support)
- `category` String(50) nullable
- `status` Enum(`ACTIVE`,`PAUSED`,`COMPLETED`,`ABANDONED`) not null default `ACTIVE`
- `description` TEXT nullable
- `target_date` DATE nullable
- `first_seen_date` DATE nullable
- `last_seen_date` DATE nullable
- `mention_count` INTEGER not null default 0
- `created_at`, `updated_at` (TimestampMixin)

Indexes:
- unique(`name`)
- (`status`, `last_seen_date`) for board/dormancy queries

### `project_events`

Columns:
- `id` INTEGER PK
- `project_id` INTEGER FK -> `projects.id` (ON DELETE CASCADE), indexed
- `entry_date` DATE FK -> `journal_entries.entry_date`, indexed
- `life_event_id` INTEGER FK -> `life_events.id` (ON DELETE CASCADE), nullable, indexed
- `event_type` Enum(`progress`,`milestone`,`setback`,`reflection`,`start`,`pause`) not null
- `content` TEXT not null
- `created_at`, `updated_at` (TimestampMixin)

Indexes:
- (`project_id`, `entry_date`)
- (`entry_date`)
- (`life_event_id`)

Rationale:
- Supports timeline views and project activity windows without extra joins.

---

## 3.4 Proposal/inbox table

### `entity_proposals`

Single-table design for V2 speed and simpler APIs.

Columns:
- `id` INTEGER PK
- `entity_type` Enum(`person`,`project`) not null
- `status` Enum(`pending`,`accepted_new`,`merged_existing`,`dismissed`,`rejected`,`blocked`) not null default `pending`
- `surface_name` String(200) not null (raw extracted candidate)
- `entry_date` DATE FK -> `journal_entries.entry_date`, indexed
- `life_event_id` INTEGER FK -> `life_events.id` (ON DELETE CASCADE), nullable, indexed
- `payload_json` TEXT not null (raw extraction context and hints)
- `candidate_matches_json` TEXT nullable (precomputed rank list; Step 3/4 uses it)
- `resolution_entity_id` INTEGER nullable (target `people.id` or `projects.id` depending on type)
- `resolution_note` TEXT nullable
- `created_at`, `updated_at` (TimestampMixin)
- `resolved_at` DateTime nullable

Indexes:
- (`status`, `entity_type`, `created_at`) for inbox list view
- (`entry_date`)
- (`surface_name`, `entity_type`)

Constraints:
- Check `entity_type` and `status` values.
- App-level validation enforces that `resolution_entity_id` points to correct table by `entity_type`.

Rationale:
- Avoid early polymorphic-table complexity while preserving full audit trail.

---

## 3.5 Optional blocklist storage (decision)

Chosen approach for Step 1: **dedicated table** (not encoded in proposal status only), to avoid re-proposing known noisy strings.

### `entity_blocklist`

Columns:
- `id` INTEGER PK
- `entity_type` Enum(`person`,`project`) not null
- `surface_name` String(200) not null
- `reason` String(50) nullable (`manual_block`, `system_noise`, etc.)
- `created_at`, `updated_at` (TimestampMixin)

Index/constraint:
- unique(`entity_type`, `surface_name`)

Rationale:
- O(1) lookup during resolution; clean semantics for one-time dismiss vs persistent block.

---

## 4) Enum definitions (database + app)

Required new enums in app/model layer:
- `SentimentLabel`: `POSITIVE`, `NEGATIVE`, `NEUTRAL`
- `ProjectStatus`: `ACTIVE`, `PAUSED`, `COMPLETED`, `ABANDONED`
- `ProjectEventType`: `progress`, `milestone`, `setback`, `reflection`, `start`, `pause`
- `ProposalEntityType`: `person`, `project`
- `ProposalStatus`: `pending`, `accepted_new`, `merged_existing`, `dismissed`, `rejected`, `blocked`

SQLite note:
- SQLAlchemy enums should be created with explicit constraints (or string columns + check constraints) to prevent silent drift.

---

## 5) Referential integrity and Q4 safety

Re-shred per date must not leave dangling references.

Required FK strategy:
- `person_mentions.life_event_id` -> `life_events.id` with `ON DELETE CASCADE`
- `project_events.life_event_id` -> `life_events.id` with `ON DELETE CASCADE`
- `entity_proposals.life_event_id` -> `life_events.id` with `ON DELETE CASCADE`

Implication:
- If old `life_events` rows are deleted during re-shred, dependent mention/event/proposal links are automatically removed or invalidated safely.
- Resolution pass after new inserts rebuilds expected rows.

Entry-date axis:
- Keep `entry_date` FKs to `journal_entries.entry_date` for cross-table time joins and dashboard windows.

---

## 6) Migration sequence (authoritative order)

1. Add `shredder_version` to `journal_entries` (nullable).
2. Add new enums/types in app and DB constraints.
3. Add new tables: `people`, `projects`, `entity_proposals`, `entity_blocklist`, then link tables `person_mentions`, `project_events`.
4. Add `life_events.sentiment` nullable.
5. Backfill `life_events.sentiment` from `sentiment_score` with threshold mapping.
6. Update app read/write paths to use `sentiment` only.
7. Drop `sentiment_score`.
8. Add/verify indexes.

Zero-downtime not required for local-first single-user, but migrations should still be reversible where feasible.

---

## 7) Rollback strategy

If Step 1 migration fails after partial apply:

- Prefer transaction-wrapped migration batches where engine supports it.
- If partially applied:
  - Keep old `sentiment_score` until step 6 above is complete.
  - Re-run migration script idempotently after fixing issue.
- Do not delete existing V1 data as part of Step 1 except planned sentiment conversion/drop.

Rollback boundary recommendation:
- Allow rollback through step 5 safely (before dropping `sentiment_score`).
- After drop, rollback requires restoring DB backup or reverse migration with data loss caveat.

---

## 8) Testing plan (Step 1)

### Unit/model tests
- Enum coercion/validation for all new enums.
- JSON alias field read/write round-trip.

### Migration tests
- Fresh DB migrate-up succeeds.
- Existing V1 DB migrate-up succeeds with:
  - `life_events.sentiment` mapped correctly from `sentiment_score`.
  - `shredder_version` column present.
  - New tables and indexes present.

### Integrity tests
- Deleting a `life_event` cascades to `person_mentions`, `project_events`, and proposal links.
- Deleting a `project` cascades project events only.
- Unique constraints enforce canonical uniqueness (`people.canonical_name`, `projects.name`, blocklist pair).

---

## 9) Dependencies

- **Reads normative conventions from Step 0:** enum policy, `shredder_version`, Q4 re-shred.
- **Feeds Step 2:** schema contract for writes from shredder.
- **Feeds Step 3/4/5:** proposal and blocklist storage contract.

---

## 10) Definition of done

Step 1 is complete when:

- All listed tables/columns/enums are implemented in ORM + migration files.
- Migration sequence works on both fresh and existing V1 DB.
- `life_events` no longer uses float sentiment in active code path.
- FK cascade behavior supports Q4 full re-shred safety.
- Step 1 changelog is updated with final implemented deviations (if any).

---

## Changelog

- 2026-04-22 — Initial complete Step 1 spec drafted from ideation + Step 0 conventions. Includes schema decisions for `entity_proposals` and `entity_blocklist`, plus migration order and Q4 FK rules.
