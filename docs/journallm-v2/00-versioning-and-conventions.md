# Step 0 — Versioning and conventions

**Index:** [README.md](./README.md) lists all step specs.  
**Plan reference:** [JOURNALLM_V2_IMPLEMENTATION_PLAN.md](../../JOURNALLM_V2_IMPLEMENTATION_PLAN.md)  
**Status:** Complete (foundation conventions locked)  
**Ideation refs:** §1.4, §1.5, Locked Q1–Q5.

---

## Purpose of Step 0

Step 0 defines shared rules for all V2 specs and implementation work so later steps do not re-decide core semantics.

This step is the canonical source for:
- Versioning behavior (`shredder_version` and re-shred policy).
- Shared enums (especially sentiment).
- Naming and API conventions.
- Cross-document traceability and ownership.

Step 0 does **not** define full table DDL for new entities; Step 1 owns final schema details.

---

## Locked decisions carried into implementation

These are normative and must be treated as requirements by Steps 1–13:

- **Q1:** Human confirmation required for new `people` and `projects` via inbox workflow.
- **Q2:** Matching order is exact/alias first; light fuzzy only for ranking; never auto-merge.
- **Q3:** Shredder/resolution can infer project status; user override always wins.
- **Q4:** Re-shred is full re-extract for a target date; dependent rows must be rebuilt safely.
- **Q5:** V2 dashboard ships with fixed curated layout; configurability is deferred.

---

## Versioning model

### `shredder_version` semantics

`journal_entries.shredder_version` tracks which extraction contract produced the current derived rows.

- **Type:** string (recommended), e.g. `v1`, `v2.0`, `v2.1`.
- **Write timing:** set when shred operation for an entry successfully commits.
- **Use cases:**
  - Selective backfill (find entries where version is old or null).
  - Safe rollouts of prompt/schema updates.
  - Auditability for debugging extraction drift.

Recommended version format: `major.minor` string.  
Examples:
- `v1.0` = current V1 extraction.
- `v2.0` = first entity-aware extraction contract.
- `v2.1` = same contract family with non-breaking prompt tuning.

### Version bump rules

- **Major bump (`v2.x` -> `v3.x`)** when output contract changes in a way that requires migration/backfill.
- **Minor bump (`v2.0` -> `v2.1`)** for prompt behavior changes that keep schema/API compatibility.

---

## Re-shred contract (Q4)

Re-shredding a date is always a **full re-extract**:

1. Delete or replace derived rows for that `entry_date`:
   - `life_events`
   - `journal_reflections`
   - Any rows FK-linked to replaced `life_events` (e.g. `person_mentions`, `project_events`).
2. Re-run extraction + resolution.
3. Rebuild dependent rows and set `shredder_version`.

### Transaction boundary requirement

For each re-shredded date, the operation must avoid dangling FKs:
- Preferred: single transaction for clear + insert + relink.
- Acceptable: two-phase flow only if intermediate state is internally valid and resumable.

### Idempotency requirement

Running re-shred twice on the same date should converge to the same persisted state for a fixed input and model response class (allowing nondeterministic wording variance from LLM output).

---

## Sentiment standardization

V2 sentiment uses categorical enum everywhere:
- `POSITIVE`
- `NEGATIVE`
- `NEUTRAL`

No float sentiment scores in V2-facing schemas.

### Migration from V1 float scores

Current V1 stores `life_events.sentiment_score` as float `[-1.0, 1.0]`.  
Migration mapping:
- `score > 0.3` -> `POSITIVE`
- `score < -0.3` -> `NEGATIVE`
- otherwise -> `NEUTRAL`
- null -> null (if field nullable in destination) or explicit default per Step 1 schema decision

### Rationale

Float sentiment from LLM output implies precision that is not reliable.  
Categorical valence improves:
- cross-run consistency,
- UI clarity,
- and easier aggregation (distribution, counts, trends).

---

## Naming conventions (V2)

### Database and model naming

- Table names are plural snake_case: `people`, `project_events`.
- Entity-link tables use `<entity>_<relation>` pattern: `person_mentions`.
- Enum values are uppercase snake case.

### API naming

- REST paths use plural nouns and stable resource semantics.
- New response fields should be additive where possible.
- Breaking response shape changes must be called out in step spec and changelog.

### Proposal / inbox semantics

Use consistent vocabulary across backend and UI:
- **proposal**: unresolved candidate entity from extraction.
- **confirm**: create new canonical entity.
- **merge**: link proposal to existing entity.
- **dismiss**: ignore without creating entity.
- **blocklist**: suppress recurring noisy surface string.

---

## Cross-step ownership and anti-duplication rules

To keep specs modular and prevent drift:

- **Step 0 owns:** conventions, versioning, migration policy standards.
- **Step 1 owns:** final schema/DDL definitions.
- **Step 2 owns:** Shredder output contract and prompt contract.
- **Step 4 owns:** inbox API contracts.
- **Step 5 owns:** inbox UX flows.

When another step depends on owned details, reference the owning step doc rather than copy-pasting full content.

---

## Required section template for every step spec

Every `docs/journallm-v2/NN-*.md` must include:

1. **Scope** (in / out).
2. **Ideation references** and applicable locked decisions (Q#).
3. **Data changes** (tables/columns/indexes/migrations).
4. **API / job contracts** (inputs, outputs, errors).
5. **Behavior/state machine** (especially transactional guarantees).
6. **Testing plan** (unit/integration/manual golden paths).
7. **Rollout/backfill/rollback** notes.
8. **Dependencies** (which other step specs are normative).
9. **Definition of done** for the step.

---

## Change control and traceability

### Spec change protocol

- If a change affects locked decisions Q1–Q5, update ideation first, then Step 0.
- If a change affects shared conventions but not product intent, update Step 0 directly and reference PR/commit in the changelog section.

### Changelog format (inside each step spec)

Use a short log at bottom:
- Date
- Author
- What changed
- Why
- Whether migration/backfill implications exist

---

## Step 0 definition of done

Step 0 is complete when:

- `shredder_version` semantics are defined and adopted by Step 1/2 specs.
- Re-shred (Q4) behavior is explicitly documented and referenced by all shred-related steps.
- Sentiment enum and migration mapping are fixed.
- Naming/API conventions are explicit.
- Step spec template/checklist is established for all remaining docs.

This file now satisfies that baseline and should be treated as normative for V2 specification work.
