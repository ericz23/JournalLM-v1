# Step 7 — Dashboard data layer extensions

**Index:** [README.md](./README.md)  
**Plan reference:** [JOURNALLM_V2_IMPLEMENTATION_PLAN.md](../../JOURNALLM_V2_IMPLEMENTATION_PLAN.md)  
**Status:** Complete (spec baseline ready for implementation)  
**Ideation refs:** §2.1, §2.2, §2.3, §2.4, §2.5, §2.6, Locked Q3, Q5.

---

## 1) Scope

### In scope

- A single weekly payload at `GET /api/dashboard/data` extended with **Inner Circle** (people) and **Active Projects** sections, plus enrichments to the existing **Dining**, **Reflections**, and **Learning** sections.
- A clear, single window definition shared by every widget on the dashboard route.
- Narrative generation upgraded to consume **two** weeks of data (current + previous) plus confirmed entity rollups, with comparative + entity-aware tone calibration. Cache key migrated from `week_start` (Mon–Sun) to `window_end` (rolling 7-day) so the dashboard and narrative agree on what "this week" means.
- Dormancy heuristic for projects (§2.6).
- Repeat-visit counter for restaurants (§2.2).
- Actionable-follow-up linking and recurring-topic flag for reflections (§2.3).
- Sentiment + per-subject milestone grouping for learning (§2.4).
- Indices on the new query paths so cold dashboard loads stay <250ms on a personal corpus (~5k events).

### Out of scope

- New widgets in the UI itself — Step 8 owns the editorial grid.
- Configurable widget layout (Locked Q5: deferred).
- Full People / Projects detail pages and their data (Step 10).
- Entity-aware **chat** retrieval (Step 11).
- Whoop / health correlation widgets (Phase 5 backlog).
- New schema / columns. Step 7 reads only what Steps 1–4 already shipped; the only non-data change is adding two SQLite indices that should land in Step 1 if not already present (called out in §11).

---

## 2) Locked decisions applied

- **Q3 (project status inference):** dormancy is a **derived** signal computed at read time from `last_seen_date` — it never writes to `projects.status`. Manual user status (Step 10) always wins; dormancy is purely a UI badge.
- **Q5 (curated grid):** the response shape is opinionated and ordered for a single layout. Field ordering is stable; no per-user toggles.

---

## 3) Dependencies

- **Reads normative detail from:**
  - Step 0 — naming/API conventions (additive fields preferred), shared sentiment enum.
  - Step 1 — schema for `people`, `person_mentions`, `projects`, `project_events`, `life_events`, `journal_reflections`, `narrative_cache`.
  - Step 3 — aggregate semantics on `people` / `projects` (`mention_count`, `last_seen_date`).
  - Step 4 — confirmed mentions/events are the only rows that surface; pending proposals never land here.
- **Feeds:**
  - Step 8 — editorial dashboard UI binds 1:1 to this payload.
  - Step 10 — People / Projects pages link from Inner Circle / Active Projects rows; the IDs returned here are the link targets.
  - Step 11 — entity-aware retrieval reuses some of the same precomputed person-mention rollups via a service helper.

---

## 4) Module layout

New / restructured backend files:

```
backend/app/services/dashboard.py            # all read-side aggregation, no I/O outside DB
backend/app/services/narrative.py            # extended; same file, additive changes
backend/app/routes/dashboard.py              # slimmer; delegates to dashboard service
```

`backend/app/services/dashboard.py` is new. The route becomes a thin adapter: parse `ref_date`, call `services.dashboard.build_payload(db, ref_date)`, return.

Helper layout inside the new service:

```
build_payload(db, ref_date) -> DashboardPayload
  ├── _resolve_window(...)
  ├── _load_events_in_window(...)
  ├── _load_reflections_in_window(...)
  ├── _build_dining(events, db)             # repeat-visit counts (§7)
  ├── _build_learning(events)               # subject grouping + sentiment (§9)
  ├── _build_reflections(reflections, db)   # follow-up + recurring (§8)
  ├── _build_inner_circle(db, window)       # §5
  ├── _build_active_projects(db, window)    # §6
  └── _build_window_meta(window)
```

Each `_build_*` returns a typed dict (Pydantic model in §13). They run in parallel where independent (asyncio.gather over the four entity queries).

---

## 5) Window definition (single source of truth)

`/api/dashboard/data` operates on a **rolling 7-day window** ending on `ref_date`:

- `window_end = ref_date or latest_journal_entry.entry_date`
- `window_start = window_end - 6 days`
- `previous_window_end = window_start - 1 day`
- `previous_window_start = previous_window_end - 6 days`

This is unchanged from V1's `_resolve_week`. The narrative service migrates **to** this window in §10. The dashboard payload includes both ranges so widgets can phrase "vs. last week" copy correctly:

```jsonc
"window": {
  "start": "2026-04-21",
  "end":   "2026-04-27",
  "previous_start": "2026-04-14",
  "previous_end":   "2026-04-20"
}
```

When the corpus is empty, the route returns `has_data: false` and omits all widget arrays (matches today's behavior).

---

## 6) Active Projects payload (§2.6)

### 6.1 Data definition

A project row is included if **any** of:
1. It has at least one `project_events` row in the current window, OR
2. `projects.status == 'ACTIVE'` and `projects.last_seen_date` is within the **last 28 days** (so a quiet but recently-active project still appears with a "dormant" badge).

Rationale: Step 8's widget should never feel empty when the user is between project bursts. 28 days is the cap on how far back a project can hide before the dashboard stops showing it; it still appears in `/projects` (Step 10).

Excluded: any project whose `status` is `COMPLETED` or `ABANDONED`, **regardless of recent events**. Those move to a future "recently completed" sub-section if we add one (backlog).

### 6.2 Per-row payload

```python
class ActiveProject(BaseModel):
    project_id: int
    name: str
    category: str | None
    status: Literal["ACTIVE", "PAUSED"]
    update_count_window: int            # project_events in current window
    update_count_previous: int          # project_events in previous window
    last_event_date: date               # max entry_date over all events for the project
    last_event_snippet: str | None      # content from the most-recent event row, truncated to 220 chars
    last_event_type: str | None         # event_type of that row (lowercase)
    streak_dot_sequence: list[bool]     # length 7, oldest → newest, True = at least one event on that date in current window
    is_dormant: bool                    # last_event_date < window_start - 14 days
    days_since_last_event: int
    target_date: date | None
```

Ordering: `(update_count_window DESC, last_event_date DESC, name ASC)`.

Cap at **8** rows in the response. Widget shows "+N more" with a link to `/projects` if `len(rows) == 8 AND total_active > 8`. Total count returned alongside as `active_total`.

### 6.3 Insight line

Computed server-side so the UI does not re-derive copy:

```python
"insight": "3 of 5 active projects saw progress this week."
```

Template:
- `{n_with_events}` = projects with `update_count_window > 0`.
- `{n_total}` = `active_total`.
- If `n_total == 0`: `"No active projects yet."`
- If `n_with_events == 0`: `"All {n_total} active projects went quiet this week."`
- Else: `"{n_with_events} of {n_total} active projects saw progress this week."`

### 6.4 Dormancy heuristic

`is_dormant = (window_start - last_event_date).days > 14`. The 14-day threshold matches the ideation §2.6 "2+ weeks" wording. Surfaced as a chip in Step 8.

---

## 7) Inner Circle payload (§2.5)

### 7.1 Data definition

A person row is included if they have at least one `person_mentions` row in the current window. The widget is purely "who did you interact with this week"; the rolling cadence dashboard for under-seen people lives on `/people` (Step 10 §3.1 "Haven't seen in a while").

### 7.2 Per-row payload

```python
class InnerCirclePerson(BaseModel):
    person_id: int
    canonical_name: str
    relationship_type: str | None
    mention_count_window: int
    mention_count_previous: int
    last_mention_date: date              # max entry_date in current window
    last_mention_snippet: str | None     # context_snippet from most recent mention, truncated to 220 chars
    sentiment_distribution: dict         # {"POSITIVE": 2, "NEUTRAL": 1, "NEGATIVE": 0}
    dominant_sentiment: Literal["POSITIVE", "NEUTRAL", "NEGATIVE", "MIXED"] | None
    days_since_last_mention: int
```

`dominant_sentiment` rules:
- If all counts are 0: `None`.
- If one label > 60% of total: that label.
- Otherwise: `"MIXED"`.

Ordering: `(mention_count_window DESC, last_mention_date DESC, canonical_name ASC)`.

Cap at **6** rows. Widget shows "+N more" linking to `/people` (Step 10) when truncated. Total count: `inner_circle_total`.

### 7.3 Insight line

```python
"insight": "You connected with 4 people this week."
```

Template:
- 0: `"Quiet week — no logged social interactions."`
- 1: `"One interaction this week — {name}."`
- 2–3: `"You connected with {n} people this week."`
- ≥4: `"You connected with {n} people this week — {top_name} most often."`

`top_name` = the highest `mention_count_window` row's canonical name.

---

## 8) Reflections enrichment (§2.3)

The existing `reflections` array is extended additively. Each row gains:

```python
class ReflectionRow(BaseModel):
    date: date
    topic: str
    content: str
    is_actionable: bool
    is_recurring: bool             # NEW: same topic seen in previous 4 weeks
    follow_up: FollowUpLink | None # NEW: see §8.1
```

### 8.1 Actionable follow-up linking

Goal: surface the ideation example: *"You said you'd start running again → You logged 3 runs this week."*

Algorithm (executed for any reflection with `is_actionable=True` from the **last 4 weeks**, not just the current window):

1. Tokenize `topic` + `content` to a small bag-of-keywords (lowercased, stopword-filtered, length ≥ 4 chars). Cache stop list as a module constant.
2. For each candidate reflection, scan the **current window** for:
   - `life_events.description` containing any of the keywords.
   - `project_events.content` containing any of the keywords.
3. If matches exist, attach:

```python
class FollowUpLink(BaseModel):
    matched_kind: Literal["life_event", "project_event"]
    matched_count: int            # total matched rows in current window
    sample_description: str       # first match's description/content, ≤180 chars
    sample_date: date
    project_id: int | None        # populated when matched_kind = project_event
```

If a reflection has multiple match kinds, prefer `project_event`. Cap follow-up keyword scan to 50 keywords per reflection (defensive only — typical reflections produce <20 tokens after stopword filtering).

### 8.2 Recurring topic flag

`is_recurring = exists reflection with same lowercased topic in [window_start - 28 days, window_start - 1 day]`. Computed via a single grouped query at the top of `_build_reflections`.

### 8.3 Ordering and cap

Order: actionable first, then recurring, then by `date DESC`. Keep all reflections from the window — no cap. Reflections are sparse (~1–5 per week).

---

## 9) Dining payload (§2.2)

Existing fields preserved. Each row adds:

```python
class DiningRow(BaseModel):
    date: date
    restaurant: str
    dishes: list[str]
    meal_type: str
    sentiment: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"] | None  # CHANGED: enum string, not float
    description: str
    visit_count_total: int        # NEW: total times this restaurant appears across the entire corpus
    visit_count_window: int       # NEW: visits within the current window
    is_repeat: bool               # NEW: visit_count_total > 1
```

### 9.1 Repeat-visit counter

Strategy:
- One pass over all `life_events` with `category = DIETARY` to build `{lowercased_restaurant: total_count}`.
- Then per-row in the window, look up `visit_count_total` and count occurrences within the window itself.
- Restaurant equality is **case-insensitive whitespace-collapsed** to merge "Lula Cafe" and "lula cafe" without normalizing the display string. Diacritics preserved.

Backlog (§16): a future `restaurants` canonical table (mirrors people/projects) once we accumulate enough drift between user spellings to warrant it. For Step 7 the heuristic above is fine.

### 9.2 Sentiment field migration

The current frontend `DashboardData.dining[].sentiment` is typed as `number` even though the backend already writes the enum string (Step 1 sentiment migration). Step 7 finalizes the type as `Literal["POSITIVE","NEGATIVE","NEUTRAL"] | None`. The frontend `DashboardData` type in `frontend/src/lib/api.ts` updates correspondingly in Step 8.

This is the **single intentional contract change** in Step 7. Called out in the changelog and in Step 8's spec.

---

## 10) Learning payload (§2.4)

Two views shipped together so Step 8 can choose between flat list and timeline:

```python
class LearningRow(BaseModel):
    date: date
    subject: str
    milestone: str
    description: str
    sentiment: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"] | None  # CHANGED: enum string

class LearningSubjectTimeline(BaseModel):
    subject: str
    sessions_window: int
    last_milestone: str | None
    last_session_date: date
    sentiment_distribution: dict        # POSITIVE/NEUTRAL/NEGATIVE counts in window
```

Response top-level:

```jsonc
"learning": [LearningRow, ...],            // unchanged ordering: date DESC
"learning_by_subject": [LearningSubjectTimeline, ...]  // new — sorted by sessions_window DESC
```

The existing `learning` array stays for backward compatibility through Step 8's transition; once the timeline view ships, the flat array becomes optional and may be removed in Step 13. Note in changelog.

---

## 11) Narrative service upgrade (§2.1)

### 11.1 Window alignment

`narrative_cache` is keyed today on `week_start` (Monday). This conflicts with the dashboard's rolling-7 model. Step 7 migrates the narrative cache to key on `window_end`:

- Add a column `window_end` (DATE, indexed). Backfill from existing `week_end` if column already exists, otherwise from `week_start + 6`. Step 1 owns the schema migration; Step 7 only specifies it.
- New uniqueness constraint: `unique(window_end)`.
- Lookup key in `get_or_generate_narrative` switches from `week_start` to `window_end`. Old rows remain queryable but become orphaned for new requests; backfill via a one-shot in Step 6's CLI is acceptable. Document at end of §11.

### 11.2 Two-week prompt input

`_gather_window_data` (renamed from `_gather_week_data`) returns:

```python
@dataclass
class NarrativeWindow:
    current: WeekDataBundle
    previous: WeekDataBundle | None         # None if no entries in previous window

@dataclass
class WeekDataBundle:
    start: date
    end: date
    event_lines: list[str]
    reflection_lines: list[str]
    inner_circle_top: list[tuple[str, int]]   # (canonical_name, mention_count) — top 5
    active_projects_top: list[tuple[str, int, str | None]]  # (name, update_count, last_event_type)
```

Inner-circle and active-projects rollups come from the same helpers used by `build_payload`, so the dashboard payload and the narrative input are computed from one source of truth.

### 11.3 Updated prompt skeleton

```
NARRATIVE_PROMPT_V2 = """
You are the editorial voice of JournalLM.

Compare THIS WEEK ({current.start}..{current.end}) to LAST WEEK ({previous.start}..{previous.end}, may be empty)
and write a 2–3 sentence "Narrative Snapshot" capturing trajectory, themes,
and any forward-looking thread the reflections suggest.

Reference people and projects by name when relevant. Vary tone:
- Many positive events + high social/learning activity → energetic.
- Sparse data or many negative-sentiment events → gentler, less performative.

Keep under 80 words. Second person ("You..."). No bullet points, no headings.

━━━ THIS WEEK ━━━
EVENTS:
{current.event_lines}

REFLECTIONS:
{current.reflection_lines}

INNER CIRCLE:
{current.inner_circle_top}

ACTIVE PROJECTS:
{current.active_projects_top}

━━━ LAST WEEK (for comparison only) ━━━
EVENTS:
{previous.event_lines or 'No data'}

INNER CIRCLE:
{previous.inner_circle_top or 'No data'}

ACTIVE PROJECTS:
{previous.active_projects_top or 'No data'}
"""
```

Temperature stays at 0.5 (matches V1 narrative). Model unchanged (`settings.GEMINI_MODEL`).

### 11.4 Cache invalidation

`narrative_cache` rows for a window become stale when:
- A new shred or backfill modifies any `life_event` / `journal_reflection` with `entry_date` inside `[window_start, window_end]`.
- A user resolves an inbox proposal whose `entry_date` falls inside the window (entity rollups may change).

Implementation:
- Add a `stale_at` column (nullable timestamp). Step 1 migration if not present, otherwise Step 7 adds it.
- On per-entry shred commit (Step 2 hook): mark all narrative rows whose `[window_start, window_end]` contains `entry_date` as stale.
- On inbox action commit (Step 4 hook): same predicate against `proposal.entry_date`.
- `get_or_generate_narrative` regenerates when `stale_at IS NOT NULL`, then clears it.

This avoids both stale narratives and over-eager regeneration on every page load. The hook is a one-line `UPDATE narrative_cache SET stale_at = now() WHERE window_start <= :d AND window_end >= :d`.

### 11.5 Empty / quiet weeks

When the current window has zero events, return the existing copy: `"No journal data available for this week yet."` with `cached: False`. No LLM call.

---

## 12) Indices (read-side performance)

For a personal corpus the queries are small, but the new aggregation paths benefit from these indices. Step 1 may already cover most; Step 7 audits and adds anything missing.

| Index | Table | Columns | Purpose |
|-------|-------|---------|---------|
| `ix_person_mentions_entry_date_person` | `person_mentions` | `entry_date, person_id` | Window grouping for Inner Circle. |
| `ix_project_events_entry_date_project` | `project_events` | `entry_date, project_id` | Window grouping for Active Projects. |
| `ix_life_events_dietary` | `life_events` | `category, entry_date` | Dining repeat-visit scan stays cheap. |
| `ix_journal_reflections_topic_lower` | `journal_reflections` | `lower(topic), entry_date` | Recurring-topic check. SQLite expression index. |

If any are already created in Step 1, no change. If missing, Step 7 ships them in a small Alembic-style migration alongside the narrative cache changes.

---

## 13) Pydantic response model

A single `DashboardPayload` schema at `backend/app/services/dashboard.py`:

```python
class DashboardPayload(BaseModel):
    has_data: bool
    window: WindowMeta | None
    inner_circle: list[InnerCirclePerson] = []
    inner_circle_total: int = 0
    inner_circle_insight: str | None = None
    active_projects: list[ActiveProject] = []
    active_projects_total: int = 0
    active_projects_insight: str | None = None
    dining: list[DiningRow] = []
    reflections: list[ReflectionRow] = []
    learning: list[LearningRow] = []
    learning_by_subject: list[LearningSubjectTimeline] = []
```

Empty-state shape: `{"has_data": false, "window": null}` and all arrays empty (omitted via `default_factory=list`). Matches today's empty path.

The route handler returns `payload.model_dump()` — no manual JSON shaping.

---

## 14) Endpoint contracts

### 14.1 `GET /api/dashboard/data`

Unchanged path and query. New response shape per §13. Backward-compatible additions only; the only change is `dining[].sentiment` and `learning[].sentiment` becoming an enum string instead of a float (§9.2).

Query:

| Name | Type | Default | Notes |
|------|------|---------|-------|
| `ref_date` | date | latest entry | Same semantics as today. |

Errors:
- `400` for malformed `ref_date`.
- `500` for unexpected DB errors. (No external API calls inside this endpoint — narrative is separate.)

Latency target: **<250ms** on a personal corpus (warm cache, ~5k events).

### 14.2 `GET /api/dashboard/narrative`

Unchanged path. Same query (`ref_date`). Behavior: returns cached narrative for the rolling window ending at `ref_date`, generates one if missing or stale (§11.4). Response fields unchanged:

```jsonc
{
  "content": "...",
  "window_start": "2026-04-21",
  "window_end":   "2026-04-27",
  "generated_at": "2026-04-27T18:00:00Z",
  "cached": true
}
```

Field rename note: `week_start`/`week_end` become `window_start`/`window_end`. The frontend type updates in Step 8. This is the **second** intentional contract change in Step 7 and motivated by §11.1 alignment.

### 14.3 No new endpoints

The plan called out potential carve-outs (`/inner-circle`, `/active-projects`). They are deferred. Rationale: the curated grid (Q5) renders all widgets together; one network round-trip is simpler and the payload stays small (<30KB on a typical week). If later widgets need partial reloads, they can be added without breaking `data` (additive paths).

---

## 15) Behavior, transactions, and failure modes

- All reads use a single `AsyncSession` per request. No write paths.
- Independent `_build_*` helpers run via `asyncio.gather` so the four entity passes overlap. Dietary repeat-visit lookup is sequential (it depends on the corpus-wide DIETARY scan).
- Failures in any single helper raise; the route returns 500 — preferred over partial widgets, which would be confusing for a curated layout. Add `try/except` only around narrative generation (since it calls Gemini); narrative failures degrade to `cached: false, content: <last_known or fallback>`.
- The narrative endpoint's `stale_at` UPDATE hooks added in Step 2 / Step 4 must be idempotent — calling them on an absent row is a no-op.

---

## 16) Backward compatibility

- `dining`, `reflections`, `learning` arrays remain in place. New fields are additive.
- Sentiment: `dining[].sentiment` and `learning[].sentiment` change from float to enum string. Frontend type fix lives in Step 8 PR; no parallel-shipping period — V2 ships them together.
- Narrative response fields renamed `week_start`/`week_end` → `window_start`/`window_end`. Same shape otherwise. Frontend `NarrativeData` type updates in Step 8.
- Old narrative cache rows keyed on `week_start` continue to exist; the lookup migration in §11.1 ignores them and they get superseded on next regeneration. A one-time cleanup pass can be run via Step 6's backfill CLI.

---

## 17) Testing plan

### 17.1 Unit tests (`services/dashboard.py`)

- `_resolve_window` — boundary correctness around month/year edges.
- `_build_inner_circle` — sentiment_distribution math; `dominant_sentiment` thresholds; tie-breaking on ordering.
- `_build_active_projects` — dormancy boundary at 14 days; status filter excludes COMPLETED/ABANDONED; streak_dot_sequence length always 7.
- `_build_dining` — case-insensitive restaurant grouping; visit_count_total stable across runs.
- `_build_reflections` — actionable follow-up keyword matching; recurring detection across the previous 4 weeks; cap at 50 keywords.

### 17.2 Integration tests (FastAPI TestClient + in-memory SQLite)

Seed a fixture database with:
- Two confirmed people, three confirmed projects (one COMPLETED, two ACTIVE).
- 4 weeks of journal entries and shredded `life_events` / `journal_reflections`.
- Sample restaurants with one repeat (3 visits over the corpus).
- One actionable reflection in week N-2 whose keywords match a `project_events` row in week N.

Assertions:
- `GET /api/dashboard/data` returns the documented shape with all fields populated.
- `inner_circle_insight` matches template for the seeded counts.
- `active_projects_total` matches the count of non-COMPLETED projects with events in the last 28 days.
- One reflection in the response has `is_recurring=True` and one has a non-null `follow_up`.
- Dietary row for the repeated restaurant has `is_repeat=True`, `visit_count_total=3`.
- `dining[].sentiment` is one of the three enum strings (or null), never a float.
- The COMPLETED project does not appear.
- An empty corpus returns `has_data: false` and no widget arrays.

### 17.3 Narrative integration

Patch `client.aio.models.generate_content` to a stub returning a fixed string.

- Two-week prompt assembly contains both `THIS WEEK` and `LAST WEEK` blocks.
- A second call with no underlying changes returns `cached: true` and does not invoke the patched LLM.
- After a simulated shred-hook UPDATE setting `stale_at`, the next call regenerates and clears `stale_at`.
- A window with no events returns the no-data fallback string and does not call the LLM.

### 17.4 Performance smoke

- Seed 5k `life_events` + 1k `person_mentions` + 500 `project_events`.
- `GET /api/dashboard/data` end-to-end stays <250ms warm and <500ms cold on the developer machine. Documented as a target, not a CI gate (no perf harness yet).

---

## 18) Observability

INFO log per request:

```
dashboard payload built window=2026-04-21..2026-04-27 inner_circle=4 active_projects=3 dining=5 reflections=2 learning=4 ms=78
```

INFO log per narrative generate:

```
narrative generated window=2026-04-21..2026-04-27 events=42 reflections=4 inner_circle=4 cached=False ms=1124
```

WARNING on:
- `dominant_sentiment` computed from zero counts (defensive — should not happen).
- More than 200 reflections in the recurring-topic lookup window (sign that stop-list needs tuning).

DEBUG on:
- Per-row follow-up keyword match count.
- Per-project dormancy days.

---

## 19) Configuration

No new env vars required. Optional additions to `app.core.config.Settings`:

```python
DASHBOARD_INNER_CIRCLE_CAP: int = 6
DASHBOARD_ACTIVE_PROJECTS_CAP: int = 8
DASHBOARD_DORMANCY_DAYS: int = 14
DASHBOARD_PROJECT_RECENT_DAYS: int = 28
NARRATIVE_REFLECTION_LOOKBACK_DAYS: int = 28
```

Defaults match the inline numbers used throughout this spec. Operators can tune without code changes; tests override via fixture monkeypatch.

---

## 20) Backlog (explicitly deferred)

1. **Restaurants canonical table** (mirrors people/projects) once spelling drift becomes a real problem.
2. **"Recently completed" sub-section** in Active Projects so completed work gets a moment of celebration before disappearing.
3. **"Haven't seen in a while" inverse Inner Circle** — surfaced on `/people` (Step 10), not the dashboard.
4. **Trend deltas on Whoop** — Phase 5 health correlation.
5. **Per-widget partial reload endpoints** — split out only when measured TTI demands it.
6. **Sparkline arrays** for dining frequency, project activity — small additive fields once the curated layout proves stable.
7. **Pre-computed `dashboard_snapshots` table** — write-side caching if the read path ever exceeds 250ms.

---

## 21) Definition of done

Step 7 is complete when:

- `services/dashboard.py` exists and exposes a single `build_payload(db, ref_date)` returning the documented `DashboardPayload`.
- `services/narrative.py` consumes a two-week window, includes entity rollups in the prompt, and uses the `window_end` cache key with `stale_at` invalidation hooks.
- `routes/dashboard.py` is a thin adapter calling the service.
- `/api/dashboard/data` returns Inner Circle, Active Projects, enriched Dining/Reflections/Learning sections per §6–§10.
- Sentiment fields in dining/learning are enum strings.
- All unit and integration tests in §17 pass.
- Indices in §12 are present (or shipped here).
- Empty-corpus and stale-cache paths behave per §15 and §11.4.
- Step 8's UI work can bind to the documented `DashboardPayload` without further backend changes.

---

## Changelog

- 2026-04-27 — Initial complete Step 7 spec. Defines a single rolling-7-day window shared by all widgets, extends `/api/dashboard/data` with Inner Circle and Active Projects sections, adds repeat-visit / actionable-follow-up / recurring-topic / per-subject-timeline enrichments, migrates narrative cache to align with the dashboard window and adds two-week comparative prompting plus stale-on-shred invalidation. Calls out two intentional response-shape changes (sentiment enum strings, narrative `window_*` field rename) handed off to Step 8 for the frontend update.
