# JournalLM V2 — Feature Ideation Document

**Status:** Ideation (Not Yet Scoped)  
**Author:** Product Session — April 2026  
**Base:** JournalLM V1 (Next.js + FastAPI + SQLite, fully functional)

---

## V2 North Star

> Evolve JournalLM from a system that *extracts and recalls* journal data into one that
> **understands the recurring characters and ongoing storylines of your life** — the people
> you see, the projects you're building, how both evolve over time — and surfaces that
> understanding through editorially sharp, push-based intelligence.

### Design Principles (Carried Forward + New)

| Principle | Description |
|-----------|-------------|
| **Personal-first, product-aware** | Optimize for a single power user. Avoid architectural choices that would block future multi-tenancy or templated journaling. |
| **Chat = Oracle, Dashboard = Editor** | Chat remains pull-based and deep. Dashboard earns its "Command Center" name by doing the thinking *for* you. |
| **Editorial over exhaustive** | Every widget must pass the test: "Would I stop and read this on a Monday morning?" No noise. |
| **Depth before breadth** | Go deeper on journals before adding new data sources. Perfect a few widgets before adding new pages. |
| **The Shredder is the moat** | All new intelligence flows from richer, entity-aware extraction — not bolted-on analytics. |

---

## Architecture: What Changes

The V1 pipeline remains intact:

```
Ingest → Shred → Embed → Retrieve → Chat/Dashboard
```

V2 extends it by introducing a **persistent entity layer** between the Shredder and the rest of the system. The Shredder currently treats each journal entry in isolation — it extracts events and reflections but has no memory of *who* "Sam" is or *what* "Urban Garden" refers to across entries. V2 makes entities first-class citizens.

```
Ingest → Shred → [Entity Resolution] → Embed → Retrieve → Chat/Dashboard
                        ↓
               People / Projects tables
               (persistent, cross-entry)
```

---

## Phase 1: The Entity-Aware Shredder

**Goal:** Teach the Shredder to recognize and persist the *people* and *projects* that recur across journal entries, turning isolated extractions into a longitudinal knowledge graph.

### 1.1 — People Entity Model

**New table: `people`**

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK | |
| `canonical_name` | String(200), unique | Display name ("Sam Chen") |
| `aliases` | TEXT (JSON array) | Alternative references (["Sam", "Samuel", "S.C."]) |
| `relationship_type` | String(50), nullable | e.g., "friend", "colleague", "family", "client" |
| `notes` | TEXT, nullable | User-editable context |
| `first_seen_date` | DATE | Earliest journal mention |
| `last_seen_date` | DATE | Most recent journal mention |
| `mention_count` | INTEGER, default 0 | Running total |
| `created_at`, `updated_at` | Timestamps | |

**New table: `person_mentions`**

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK | |
| `person_id` | FK → people.id | |
| `entry_date` | FK → journal_entries.entry_date | |
| `life_event_id` | FK → life_events.id, nullable | Which event they appeared in |
| `context_snippet` | String(500) | Sentence/phrase where they were mentioned |
| `sentiment` | Enum (POSITIVE, NEGATIVE, NEUTRAL), nullable | Sentiment of this specific interaction |
| `created_at` | Timestamp | |

**Shredder enhancement:** Add a `people_mentioned` array to the extraction schema. Each item includes `name`, `relationship_hint` (if inferable from context), and `context`. Post-extraction, resolution matches against existing `people` rows; **unmatched** surface strings become **person proposals** in the inbox — not new `people` rows until confirmed (§1.5).

### 1.2 — Projects Entity Model

**New table: `projects`**

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK | |
| `name` | String(200), unique | e.g., "10k Training", "Portuguese", "Urban Garden" |
| `category` | String(50) | e.g., "fitness", "learning", "creative", "professional" |
| `status` | Enum | ACTIVE, PAUSED, COMPLETED, ABANDONED |
| `description` | TEXT, nullable | What this project is about |
| `target_date` | DATE, nullable | Optional deadline or target |
| `first_seen_date` | DATE | First journal mention |
| `last_seen_date` | DATE | Most recent mention |
| `mention_count` | INTEGER, default 0 | |
| `created_at`, `updated_at` | Timestamps | |

**New table: `project_events`**

| Column | Type | Purpose |
|--------|------|---------|
| `id` | INTEGER PK | |
| `project_id` | FK → projects.id | |
| `entry_date` | FK → journal_entries.entry_date | |
| `life_event_id` | FK → life_events.id, nullable | |
| `event_type` | String(50) | "progress", "milestone", "setback", "reflection", "start", "pause" |
| `content` | TEXT | What happened with this project |
| `created_at` | Timestamp | |

**Shredder enhancement:** Add a `project_events` array to the extraction schema. Each item includes `project_name`, `event_type`, and `content`. Entity resolution matches against existing `projects` rows. **New projects are not created automatically** — see §1.5 (entity inbox). Once a project exists and is confirmed, the **Shredder / resolution step may infer and update `projects.status`** from lifecycle language and `event_type` (Locked Q3); the user can **always override** status in the UI.

### 1.3 — Entity Resolution Service

A new `entity_resolution.py` service that runs after each Shredder extraction:

- **People resolution:** Normalize extracted surface strings → deterministic match against `people.canonical_name` and `people.aliases` (case-insensitive; light fuzzy **only** for ranking merge candidates per Locked Q2). **If no confident match**, enqueue a **person proposal** for human review — do **not** insert a new `people` row until confirmed (see §1.5).
- **Project resolution:** Same pattern — match against existing `projects.name` / aliases (case-insensitive + light fuzzy for **candidate ranking** only); on ambiguity or novelty, enqueue a **project proposal** instead of auto-creating.
- **Project status (Locked Q3):** After linking extraction to a confirmed project, **infer `projects.status`** when the journal clearly signals it (e.g. completion → `COMPLETED`, explicit pause → `PAUSED`, abandonment language → `ABANDONED`). Map strong `event_type` values (e.g. `milestone` + completion cues) to status updates. **User overrides in UI always win** for subsequent edits.
- **Aggregate stat updates:** After a person or project is **confirmed** and mentions/events are linked, update `mention_count`, `last_seen_date` on parent entity rows.

### 1.4 — Shredder Prompt V2

The current `SYSTEM_INSTRUCTION` needs to expand to extract structured people and project data alongside life events and reflections. Key changes:

- Add `people_mentioned` to the output schema with fields: `name`, `relationship_hint`, `interaction_context`.
- Add `project_events` to the output schema with fields: `project_name`, `event_type` (enum: progress, milestone, setback, reflection, start, pause), `description`.
- Add extraction guidance: "Identify every named person. Infer relationship type from context (friend, colleague, family, client). For recurring projects, classify the type of event." Optionally emit a **`suggested_project_status`** (or encode in `event_type`) when the entry clearly signals completion, pause, or abandonment — resolution applies Locked Q3.
- Keep temperature at 0.2 for consistency.

**Migration concerns:**
- Re-running the Shredder on already-processed entries will be necessary to backfill entity data. Add a `shredder_version` column to `journal_entries` so the system knows which entries were processed with which prompt version, enabling **selective** re-runs. **Re-shred policy (Locked Q4):** each targeted re-run performs a **full re-extract** — existing `life_events` and `journal_reflections` for that date are **replaced** by a fresh Shredder pass (IDs may change). Any rows that FK to `life_events` (e.g. `person_mentions`, `project_events`) for that entry must be **cleared and rebuilt** in the same transaction or via a follow-up resolution pass so the DB stays consistent.
- **Sentiment model change:** V1 uses `sentiment_score` (Float, -1.0 to 1.0) on `life_events`. V2 replaces this with `sentiment` (Enum: POSITIVE, NEGATIVE, NEUTRAL) across all tables. Float scores are false precision — LLMs can reliably classify valence but not magnitude. Migration should convert existing float scores (> 0.3 → POSITIVE, < -0.3 → NEGATIVE, else NEUTRAL) and update the Shredder prompt to emit the enum instead of a float.

### 1.5 — Entity inbox, confirmation, and disambiguation *(locked — see §Locked product decisions, Q1)*

The Shredder cannot reliably know whether "Sam" is the same person as "Samuel," or whether two different people share the first name "Alex." **Decisions:** use a lightweight **entity inbox** after each run; **no new `people` or `projects` row** until the user confirms or merges.

**Inbox item (conceptual):** Each proposal carries the extracted surface string(s), `entry_date`, optional `life_event_id`, relationship/project hints from the extraction, and **merge candidates** — existing entities ranked by deterministic signals (not auto-applied):

| Signal | Use |
|--------|-----|
| Exact / case-insensitive alias match | High confidence candidate |
| Same-day co-occurrence with another resolved person | Weak hint for UI only |
| String similarity (prefix, token overlap, light edit distance e.g. Levenshtein) | Candidate ordering only — **never auto-merge** (see Locked Q2) |
| Optional **LLM merge suggestion** (second pass) | "Likely same as X" badge in UI only — never auto-merge without user action |

**User actions on a person proposal:**

- **Confirm new person** — create `people` + link this mention (and optionally add aliases the user types).
- **Merge into existing** — add the surface string as an alias on the chosen person; link `person_mentions` to that `person_id`.
- **Ignore / not a person** — discard proposal (e.g. mis-extracted phrase); optionally **blocklist** that string so it is not proposed again.

**User actions on a project proposal:**

- **Confirm new project** — create `projects` + attach pending `project_events` for that name on linked dates.
- **Merge into existing project** — attach events to the chosen `project_id`; no new row.
- **Reject — not a project** — do **not** create a project. **Behavior (locked):** (a) **Drop linkage** for that extraction only — the underlying `life_event` / journal text remains unchanged; no `project_events` row tied to a canonical project. (b) Optional **blocklist** of the proposed name string so future runs do not re-open the same inbox noise. (c) Optional **"one-time dismiss"** without blocklist if the string might be a real project later in another context.

**Implementation note:** Persist pending rows in something like `entity_proposals` (type: `person` | `project`, status: `pending` | `accepted` | `merged` | `rejected`, payload JSON) or split tables — exact schema left to V2 technical spec.

---

## Phase 2: Editorial Dashboard — Widget Polish

**Goal:** Before adding new widgets, make the existing dashboard smarter, more contextual, and editorially sharp. Then introduce two new widgets aligned with the Social and Productivity axes.

### 2.1 — Narrative Snapshot Enhancement

**Current state:** Single paragraph, ~80 words, generated from event + reflection summaries.

**V2 enhancements:**
- **Comparative framing:** The narrative should reference the *previous* week when relevant. "You were more socially active than last week — three dinners vs. one." This requires passing two weeks of data to the prompt.
- **Entity-aware narrative:** Mention people and projects by name. "You saw Sam twice and made progress on Portuguese, but the Urban Garden went quiet."
- **Tone calibration:** The prompt should vary tone based on the data. A week dominated by positive-sentiment events and high activity gets an energetic summary. A low-data or rough week gets something gentler.

### 2.2 — Dining Log Polish

**Current state:** Lists meals with emoji, sentiment, dishes, date.

**V2 enhancements:**
- **Repeat visit detection:** Flag restaurants you've been to before with a visit count. "Third visit" badge.
- Minor: fix pluralization, show `description` on expand/hover.

### 2.3 — Reflections Panel Polish

**Current state:** Lists reflections with topic, actionable badge, date, content.

**V2 enhancements:**
- **Actionable item follow-up:** If a reflection was marked `is_actionable` in a previous week and a related event or project update appears this week, link them. "You said you'd start running again → You logged 3 runs this week."
- **Topic continuity:** If the same topic appears across multiple weeks, show a "recurring theme" indicator.

### 2.4 — Learning Progress Polish

**Current state:** Grid of cards with subject, milestone, description, date.

**V2 enhancements:**
- **Milestone timeline:** Rather than individual cards, consider a compact timeline view per subject showing progression.
- Display sentiment (currently extracted but not rendered).

### 2.5 — New Widget: Inner Circle (Social)

**A new dashboard widget for Phase 2, once the entity model exists.**

- **Purpose:** Show the people you interacted with this week, ranked by mention frequency.
- **Display:** Compact list — name, interaction count this week, last interaction context snippet, sentiment indicator.
- **Insight line:** "You connected with 4 people this week" or "Quieter week — 1 social interaction."
- **Design:** Follows existing card pattern. Accent-left-rule per person, using a consistent color per relationship type.

### 2.6 — New Widget: Active Projects (Productivity)

**A new dashboard widget for Phase 2, once the entity model exists.**

- **Purpose:** Show your active projects with this week's activity.
- **Display:** Each project as a compact row — name, category chip, update count this week, last update snippet, streak indicator.
- **Insight line:** "3 of 5 active projects saw progress this week."
- **Dormancy flag:** If a project hasn't been mentioned in 2+ weeks, show a subtle "dormant" indicator.
- **Design:** Compact, scannable. Progress-bar or dot-sequence for streak visualization.

---

## Phase 3: Dedicated Surfaces

**Goal:** Once the entity model is stable and dashboard widgets are proven, build dedicated pages for deeper exploration.

### 3.1 — People Page (`/people`)

- **List view:** All known people, sortable by last seen, mention count, relationship type.
- **Person detail view:** Click into a person to see:
  - Interaction timeline (every `person_mention` plotted chronologically).
  - Sentiment history over time (positive/negative/neutral distribution per interaction).
  - Co-occurrence: other people frequently mentioned in the same entries.
  - Related life events (linked via `life_event_id`).
  - Editable fields: canonical name, aliases, relationship type, notes.
- **"Haven't seen in a while" section:** People whose `last_seen_date` is notably older than their typical cadence.

### 3.2 — Projects Page (`/projects`)

- **Board view:** Projects grouped by status (Active / Paused / Completed), inspired by a lightweight Kanban.
- **Project detail view:** Click into a project to see:
  - Update timeline (every `project_event` chronologically).
  - Milestone highlights extracted from updates.
  - Activity heatmap or streak calendar (which days/weeks this project was mentioned).
  - Related reflections that reference this project's topic.
- **Status management:** Manual override for status (mark as paused, completed, etc.) — corrects or supersedes Shredder-inferred status (Locked Q3).

### 3.3 — Navigation Update

- **TopNav expansion:** Add "People" and "Projects" as nav items alongside Dashboard and Chat.
- **Dashboard → Surface linking:** Widgets like "Inner Circle" and "Active Projects" link out to their respective detail pages.

---

## Phase 4: Chat Intelligence Upgrades

**Goal:** Make the chat aware of the new entity layer so it can answer relationship and project questions natively.

### 4.1 — Entity-Aware Retrieval

- **Intent classification update:** Add entity-type intents. "When did I last see Sam?" should trigger a `person_mentions` lookup, not a full-text search.
- **Structured queries:** The retrieval service should be able to query `people`, `person_mentions`, `projects`, and `project_events` tables directly when the intent involves named entities.
- **Context enrichment:** When a person or project is referenced in a chat query, include their entity metadata (relationship type, mention count, last seen) in the context block.

### 4.2 — New Chat Mode: Coach

- **Purpose:** A project-oriented mode that focuses on accountability and progress review.
- **System prompt:** Aware of `projects` and `project_events`. Can summarize progress, identify stalled projects, suggest next steps.
- **Accent color:** Green (`--color-brand-accent-green`).
- **Starter prompts:** "How's my Portuguese going?", "What projects have I neglected?", "Summarize my 10k training progress."

---

## Phase 5: Future Enrichments (Backlog)

These are intentionally deferred but architecturally accounted for.

### 5.1 — Google Calendar Integration
- Sync calendar events as a new data source alongside journals and Whoop.
- New `calendar_events` table with start/end time, title, attendees, location.
- Cross-reference calendar attendees with `people` entities for richer social intelligence.
- Dashboard could show "Journaled vs. Calendared" discrepancies — what you scheduled vs. what you actually wrote about.

### 5.2 — Templated Journaling (Product Path)
- Define journal templates with structured sections (e.g., "Morning Check-in", "Daily Wins", "People I Saw", "Project Progress").
- Templates ensure consistent data collection, making extraction more reliable.
- Templates could be user-configurable (personal tool) or predefined (product version).
- Potential in-app journaling editor rather than Obsidian-only ingestion.

### 5.3 — Weekly Digest / Briefing
- Automated Monday-morning email or in-app notification summarizing last week.
- Combines narrative snapshot + inner circle + project status into a single editorial briefing.
- Light push-based intelligence without adding dashboard clutter.

### 5.4 — Additional Health Correlation
- Overlay Whoop recovery/HRV with social activity frequency and project progress.
- "Your recovery tends to be higher on weeks you see friends 3+ times."
- Requires enough longitudinal data to be statistically meaningful.

### 5.5 — Configurable dashboard layout *(Locked Q5 — deferred)*
- User preferences for which dashboard widgets appear and in what order (optional compact mode).
- Deferred until the fixed-layout Command Center is validated in daily use.

---

## Implementation Priority (Suggested)

| Order | Work | Dependencies |
|-------|------|--------------|
| **1** | People + Projects data models + migrations | None |
| **2** | Shredder V2 prompt + entity resolution service | Models from #1 |
| **3** | Re-process existing entries with V2 Shredder | #2 complete |
| **4** | Dashboard widget polish (Narrative, Dining, Reflections, Learning) | Minimal — mostly prompt/UI work |
| **5** | Inner Circle widget + Active Projects widget | Entity data from #3 |
| **6** | Entity-aware retrieval for Chat | Entity data from #3 |
| **7** | People page (`/people`) | Stable entity data + proven widget designs |
| **8** | Projects page (`/projects`) | Stable entity data + proven widget designs |
| **9** | Coach chat mode | Entity-aware retrieval from #6 |
| **10** | Calendar integration / Templated journaling | After core V2 is stable |
| **—** | **Entity inbox UI** (review proposals after shred) | After #2; blocks fully automatic People/Projects widgets until resolved |

---

## Locked product decisions

| # | Topic | Decision |
|---|--------|----------|
| **Q1** | **Entity approval flow** | **People:** lightweight confirmation before any new `people` row. Inbox shows merge candidates (aliases, string similarity, optional LLM hint only as UI assist). User confirms new, merges into existing, or dismisses / blocklists. **Projects:** same — confirm before new `projects` row. **Reject project proposal:** do not create project; leave journal / `life_events` unchanged; optionally blocklist the proposed name or one-time dismiss without blocklist (see §1.5). |
| **Q2** | **Alias / merge candidate matching** | **Simple + light fuzzy:** case-insensitive exact match on canonical name and manual aliases first; then **token overlap** and **edit-distance-style** similarity (e.g. Levenshtein) **only to rank** inbox merge candidates — **never auto-merge**. No phonetic/Soundex in v1 unless we add it later. |
| **Q3** | **Project status inference** | **Automatic inference allowed:** the Shredder and/or resolution step may set or update `projects.status` (e.g. `COMPLETED`, `PAUSED`, `ABANDONED`) when journal text and `event_type` support it. **Manual UI override** remains always available and supersedes inferred status when the user corrects it. |
| **Q4** | **Re-shredding strategy** | **Full re-extract:** when an entry is re-processed, **replace** `life_events` and `journal_reflections` for that `entry_date` with fresh model output. Do **not** preserve prior rows for merge-only updates. **Implication:** `life_event` row IDs may change — child rows that reference `life_event_id` must be dropped and recreated (or re-linked after resolution) in the same operational flow so foreign keys never dangle. |
| **Q5** | **Widget density / layout** | **V2 default: curated fixed grid** — one opinionated Command Center layout; no show/hide/reorder controls in the first ship. **Later:** configurable widget layout (visibility + order), saved per user, once the core widgets are proven. |

*No remaining open questions from the original ideation checklist.*
