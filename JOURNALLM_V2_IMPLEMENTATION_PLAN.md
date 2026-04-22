# JournalLM V2 — High-Level Implementation Plan

**Status:** Outline (feeds **per-step spec docs** and tickets)  
**Source of truth for product intent:** [JOURNALLM_V2_IDEATION.md](./JOURNALLM_V2_IDEATION.md)  
**Specification layout:** One Markdown file per implementation step under [`docs/journallm-v2/`](./docs/journallm-v2/) — see [index README](./docs/journallm-v2/README.md). There is **no** monolithic `JOURNALLM_V2_SPEC.md`; cross-cutting concerns are owned by Step 0 and repeated by reference only where needed.  
**Base stack:** Existing V1 hybrid (Next.js + FastAPI + SQLite + Gemini + Whoop)

This document is the **step-by-step implementation order**. Each step’s companion spec should define: tables/columns touched in that step, endpoint contracts (if any), state machines, transaction boundaries, prompt diffs, feature flags, test cases, and rollback notes — with links back to ideation subsection IDs (e.g. §1.5, §2.5).

---

## Specification map (filename per step)

| Step | Spec document |
|------|----------------|
| 0 | [docs/journallm-v2/00-versioning-and-conventions.md](./docs/journallm-v2/00-versioning-and-conventions.md) |
| 1 | [docs/journallm-v2/01-database-foundation.md](./docs/journallm-v2/01-database-foundation.md) |
| 2 | [docs/journallm-v2/02-shredder-v2.md](./docs/journallm-v2/02-shredder-v2.md) |
| 3 | [docs/journallm-v2/03-entity-resolution.md](./docs/journallm-v2/03-entity-resolution.md) |
| 4 | [docs/journallm-v2/04-entity-inbox-api.md](./docs/journallm-v2/04-entity-inbox-api.md) |
| 5 | [docs/journallm-v2/05-entity-inbox-ui.md](./docs/journallm-v2/05-entity-inbox-ui.md) |
| 6 | [docs/journallm-v2/06-backfill-and-operations.md](./docs/journallm-v2/06-backfill-and-operations.md) |
| 7 | [docs/journallm-v2/07-dashboard-data-layer.md](./docs/journallm-v2/07-dashboard-data-layer.md) |
| 8 | [docs/journallm-v2/08-dashboard-editorial-ui.md](./docs/journallm-v2/08-dashboard-editorial-ui.md) |
| 9 | [docs/journallm-v2/09-embeddings-and-rag.md](./docs/journallm-v2/09-embeddings-and-rag.md) |
| 10 | [docs/journallm-v2/10-people-and-projects-pages.md](./docs/journallm-v2/10-people-and-projects-pages.md) |
| 11 | [docs/journallm-v2/11-entity-aware-chat-retrieval.md](./docs/journallm-v2/11-entity-aware-chat-retrieval.md) |
| 12 | [docs/journallm-v2/12-coach-chat-mode.md](./docs/journallm-v2/12-coach-chat-mode.md) |
| 13 | [docs/journallm-v2/13-release-and-hardening.md](./docs/journallm-v2/13-release-and-hardening.md) |

---

## Locked constraints (do not re-litigate in spec)

Summarized from **Locked product decisions (Q1–Q5)** in the ideation doc:

| ID | Constraint |
|----|------------|
| Q1 | Entity inbox before new `people` / `projects` rows; merge / dismiss / blocklist; project reject behavior as specified. |
| Q2 | Match: exact + aliases first; light fuzzy **only** for candidate **ranking**; never auto-merge. |
| Q3 | Shredder/resolution **may** infer `projects.status`; UI **always** may override. |
| Q4 | Re-shred = **full re-extract** for that date; replace `life_events` / `journal_reflections`; fix up FK children in same flow. |
| Q5 | Dashboard: **fixed curated grid** for V2 ship; configurable layout is backlog (§5.5). |

---

## Step 0 — Spec and versioning hygiene

**Specification:** [00-versioning-and-conventions.md](./docs/journallm-v2/00-versioning-and-conventions.md)

**Goal:** Make implementation traceable before schema churn.

1. Fill Step 0 spec: shared enum definitions, `shredder_version` semantics (ideation §1.4), sentiment enum + migration from `sentiment_score`, naming conventions, and how step specs reference each other (avoid duplicating full ERD in every file — Step 1 owns the entity ERD detail).
2. Keep [docs/journallm-v2/README.md](./docs/journallm-v2/README.md) updated as the **navigation index** (status column, optional assignee).

**Exit:** Step 0 spec complete enough that Step 1 can start without ambiguity.

---

## Step 1 — Database foundation (entities + inbox + sentiment)

**Specification:** [01-database-foundation.md](./docs/journallm-v2/01-database-foundation.md)

**Goal:** Persist everything the Shredder and inbox need without yet depending on perfect UI.

1. Create ORM models and migrations for:
   - `people`, `person_mentions` (with `sentiment` enum, not float).
   - `projects`, `project_events`.
   - **`entity_proposals`** (or split tables) with types, statuses, payload JSON, timestamps — supports Q1 inbox flows.
   - **Blocklist / dismiss** storage if not embedded in proposal rows (decide in Step 1 spec).
2. Alter `life_events`: replace `sentiment_score` with `sentiment` enum; run data migration on existing rows (thresholds in Step 0 spec).
3. Foreign keys and delete rules: align with **Q4** (re-shred replaces events — children referencing `life_event_id` must be cleared/rebuilt in the same transaction as shred for that `entry_date`).
4. Optional: `projects` alias storage if not only `name`.

**Exit:** Migrations apply cleanly; Step 1 doc contains authoritative DDL/ORM notes for Steps 2–3.

---

## Step 2 — Shredder V2 (extraction schema + prompt)

**Specification:** [02-shredder-v2.md](./docs/journallm-v2/02-shredder-v2.md)

**Goal:** One structured JSON output that includes life events, reflections, people mentions, and project events, plus optional project status signal.

1. Extend Pydantic response models: `people_mentioned`, `project_events`, optional `suggested_project_status` (or equivalent per spec).
2. Update `SYSTEM_INSTRUCTION` / user payload per ideation §1.4; keep **temperature 0.2**.
3. Map model output into **staging structures** (not necessarily final DB rows for people/projects — those go through proposals per Q1).
4. Implement **sentiment enum** on new and migrated `life_events` writes.
5. **Full re-extract** behavior for a single date: delete/replace `life_events` + `journal_reflections` as today, extended to clear dependent rows per Q4 before insert.

**Exit:** Step 2 spec includes full JSON schema + golden fixture expectations.

---

## Step 3 — Entity resolution + proposal creation

**Specification:** [03-entity-resolution.md](./docs/journallm-v2/03-entity-resolution.md)

**Goal:** Deterministic pipeline after LLM: match, rank, enqueue — no auto-create of `people` / `projects`.

1. Implement **`entity_resolution.py`** (or equivalent module):
   - Normalize surface strings.
   - **People:** exact/alias match; fuzzy **ranking only** for proposal UI (Q2); on no match → `entity_proposals` row (`person`).
   - **Projects:** same for `project` proposals.
2. For rows that **do** match existing entities: create `person_mentions` / `project_events` with correct FKs to `life_events` where applicable.
3. **Project status inference (Q3):** when linking to an existing `project_id`, apply status updates from rules in this spec.
4. Update aggregates (`mention_count`, `last_seen_date`, etc.) **only** for confirmed-linked rows, not for pending proposals.

**Exit:** Step 3 spec documents algorithms, scoring for candidate lists, and idempotency on re-run.

---

## Step 4 — Entity inbox API (backend)

**Specification:** [04-entity-inbox-api.md](./docs/journallm-v2/04-entity-inbox-api.md)

**Goal:** All Q1 user actions are possible without the full dashboard polish.

1. **List proposals:** filter by status, type, date; include merge candidate list (precomputed scores for ordering).
2. **Actions:**
   - Person: confirm new, merge into existing (add alias), dismiss, blocklist.
   - Project: confirm new, merge into existing, reject (no row + dismiss/blocklist options per ideation §1.5).
3. **Apply actions in transactions:** create parent entity rows, rewrite FKs, mark proposal resolved, update aggregates.
4. **Idempotency / race:** define in Step 4 spec.

**Exit:** OpenAPI-level detail lives in Step 4 doc only.

---

## Step 5 — Entity inbox UI (frontend)

**Specification:** [05-entity-inbox-ui.md](./docs/journallm-v2/05-entity-inbox-ui.md)

**Goal:** Human-in-the-loop is usable daily (unblocks trustworthy People/Projects data).

1. New route (e.g. `/inbox` or modal from Command Center): list pending proposals, show ranked candidates, blocklist/dismiss controls.
2. Wire to Step 4 APIs; empty state when clean.
3. Optional: second-pass LLM “hint” badge (never auto-merges) — defer if needed to hit MVP.

**Exit:** Step 5 spec has flows, components, and accessibility notes.

---

## Step 6 — Backfill and operational scripts

**Specification:** [06-backfill-and-operations.md](./docs/journallm-v2/06-backfill-and-operations.md)

**Goal:** Move from dev fixtures to real corpus safely.

1. Batch job or admin endpoint: re-shred date range with **Q4** semantics; re-embed if chunk boundaries change (decide in Step 6 / Step 9 specs).
2. Logging: proposal counts, resolution match rates, shred failures.
3. Document **order of operations:** ingest → shred → resolve → inbox → optional second shred after merges (if required).

**Exit:** Runbook in Step 6 doc; safe defaults for personal data.

---

## Step 7 — Dashboard data layer extensions

**Specification:** [07-dashboard-data-layer.md](./docs/journallm-v2/07-dashboard-data-layer.md)

**Goal:** API supports richer weekly payload without yet redesigning every widget.

1. Extend **`/api/dashboard/data`** (or successor) to include:
   - Inner Circle payload: confirmed `person_mentions` in window, grouped by person, counts, last snippet, sentiment enum, relationship type.
   - Active Projects payload: `projects` where `status=ACTIVE` (or as spec’d), `project_events` in window, dormancy heuristic (ideation §2.6).
2. **Narrative service:** pass **two weeks** of summaries for comparative copy (ideation §2.1); inject entity names when available.
3. **Dining log:** repeat-visit counts across full history (or rolling N months — spec).
4. **Reflections / learning:** data for actionable follow-up and topic continuity.

**Exit:** Response JSON schemas documented in Step 7 file; feature flags noted if used.

---

## Step 8 — Editorial dashboard UI (fixed grid, Q5)

**Specification:** [08-dashboard-editorial-ui.md](./docs/journallm-v2/08-dashboard-editorial-ui.md)

**Goal:** Command Center matches “push-based editor” quality bar.

1. **Polish existing widgets** per ideation §2.1–§2.4 (narrative, dining, reflections, learning) using Step 7 data.
2. **Add Inner Circle + Active Projects** widgets in the **curated** layout (order and span per Step 8 spec — ASCII grid or component tree).
3. Link rows to future detail routes (placeholders acceptable until Step 10).

**Exit:** Visual/layout acceptance criteria in Step 8 doc; confirms Q5 (no layout controls).

---

## Step 9 — Embeddings and RAG compatibility

**Specification:** [09-embeddings-and-rag.md](./docs/journallm-v2/09-embeddings-and-rag.md)

**Goal:** Chat and search stay correct after schema and content changes.

1. Re-embed policy when `life_events` text or `chunk_text` inputs change (trigger: shred vs nightly — Step 9 spec).
2. Update **`retrieval.py`** / intent schema placeholders for future entity queries (Step 11 fully wires).

**Exit:** Regression matrix in Step 9 doc.

---

## Step 10 — Dedicated surfaces: People and Projects

**Specification:** [10-people-and-projects-pages.md](./docs/journallm-v2/10-people-and-projects-pages.md)

**Goal:** Deep views from ideation Phase 3.

1. **`/people`:** list, detail, edit canonical name/aliases/relationship/notes; timeline of `person_mentions`; sentiment distribution; co-occurrence placeholder or v1 simple version.
2. **`/projects`:** board by status; detail timeline of `project_events`; manual status override (Q3).
3. **TopNav** + links from Inner Circle / Active Projects (ideation §3.3).

**Exit:** Routes and edit forms specified in Step 10 doc.

---

## Step 11 — Entity-aware chat retrieval

**Specification:** [11-entity-aware-chat-retrieval.md](./docs/journallm-v2/11-entity-aware-chat-retrieval.md)

**Goal:** “When did I last see Sam?” hits SQL, not only vectors.

1. Extend intent classification for **person** / **project** / **mention** query shapes.
2. SQL pull from `people`, `person_mentions`, `projects`, `project_events` with date filters.
3. Context block formatting in **`chat_engine.py`** for entity rows.

**Exit:** Golden questions listed in Step 11 doc.

---

## Step 12 — Coach chat mode

**Specification:** [12-coach-chat-mode.md](./docs/journallm-v2/12-coach-chat-mode.md)

**Goal:** Project accountability mode per ideation §4.2.

1. Backend: register `coach` in `MODE_CONFIGS` with system prompt grounded in projects + events.
2. Frontend: **`chat-modes.ts`** entry (accent green), disclaimers if any.
3. Ensure retrieval supplies enough project context in this mode.

**Exit:** Prompt text and mode safety notes in Step 12 doc.

---

## Step 13 — Hardening, docs, release

**Specification:** [13-release-and-hardening.md](./docs/journallm-v2/13-release-and-hardening.md)

**Goal:** V2 is operable for personal daily use.

1. Update **README** / env vars / migration notes for V2.
2. Performance: batch shred, N+1 dashboard queries, SQLite indices on FKs and dates.
3. **Regression checklist:** ingest, shred, inbox, dashboard, chat, Whoop unchanged where applicable.

**Exit:** Release tag criteria and changelog template in Step 13 doc.

---

## Backlog (post–Step 13)

Tracked in ideation **Phase 5**: Calendar, templated journaling, weekly digest, health correlation, configurable dashboard (§5.5). When any backlog item is pulled forward, add a **new** numbered spec (e.g. `14-calendar-integration.md`) and extend this plan — do not overload Step 13.

---

## Dependency overview (quick reference)

```
Step 0 (conventions + index)
    → Step 1 (DB)
        → Step 2 (Shredder V2)
            → Step 3 (Resolution + proposals)
                → Step 4 (Inbox API)
                    → Step 5 (Inbox UI)
                        → Step 6 (Backfill)
                            → Step 7 (Dashboard API)
                                → Step 8 (Dashboard UI)
                                    → Step 9 (Embeddings/RAG touch-up)
                                        → Step 10 (People/Projects pages)
                                            → Step 11 (Entity-aware retrieval)
                                                → Step 12 (Coach mode)
                                                    → Step 13 (Ship)
```

**Parallelism note:** Step 7 narrative/dining/reflections sub-work can be specified alongside Step 4–5 if staffed split — but **Inner Circle / Active Projects** data in Step 7 should assume **confirmed** entities after Step 5 for production-quality UX.

---

## What each step spec must contain (checklist)

Use this list inside each `docs/journallm-v2/NN-*.md` file so quality stays consistent:

- **Scope:** In-scope / explicitly out-of-scope for this step only.
- **Ideation links:** subsection IDs (§…) and which Locked decisions (Q…) apply.
- **Data:** Tables/columns touched; migrations; rollback notes.
- **API / jobs:** Request/response shapes, errors, auth assumptions (single-user today).
- **Behavior:** State machines, transaction boundaries (especially Q4 next to any shred).
- **AI:** Prompt snippets or diff summary vs V1 (Steps 2, 3, 11, 12).
- **UI:** Components and routes (Steps 5, 8, 10) — wireframes optional.
- **Testing:** Unit, integration, manual golden paths.
- **Dependencies:** “Reads normative detail from Step N spec” where split avoids duplication.
