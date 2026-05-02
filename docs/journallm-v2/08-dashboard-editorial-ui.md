# Step 8 — Editorial dashboard UI (fixed grid)

**Index:** [README.md](./README.md)  
**Plan reference:** [JOURNALLM_V2_IMPLEMENTATION_PLAN.md](../../JOURNALLM_V2_IMPLEMENTATION_PLAN.md)  
**Status:** Complete (spec baseline ready for implementation)  
**Ideation refs:** §2.1, §2.2, §2.3, §2.4, §2.5, §2.6, §3.3, Locked Q5.

---

## 1) Scope

### In scope

- Re-render `/` (Command Center) against the V2 `DashboardPayload` (Step 7) with two **new widgets** — Inner Circle (`InnerCircleWidget`) and Active Projects (`ActiveProjectsWidget`) — and **polished** versions of the four existing widgets.
- A single curated grid layout (Locked Q5 — no per-user toggles).
- Frontend type updates in `lib/api.ts` to match Step 7's response shape, including the two intentional contract changes (sentiment enum strings, narrative `window_*` fields).
- Insight lines, dormancy chips, repeat-visit badges, recurring-topic flags, actionable follow-up links, and per-subject learning timeline rendered from server-precomputed fields.
- "Visit detail" affordances on Inner Circle and Active Projects rows that link to `/people/[id]` and `/projects/[id]` placeholders (Step 10 routes — until those exist, links land on the existing inbox or a 404 page; this is documented as acceptable for the V2 ship gate).
- Empty / loading / error states per widget styled in Luminous Codex tokens.

### Out of scope

- Configurable widget layout, drag-and-drop, hide/show toggles (Locked Q5: deferred to Phase 5 §5.5).
- Mobile-first redesign. The dashboard targets ≥1024px desktop; below that, widgets stack to single column (matches today).
- People / Projects detail page implementation (Step 10).
- New backend endpoints. Step 8 consumes exactly what Step 7 ships.
- Whoop / health correlation widgets (Phase 5).
- Accessibility audit beyond the Step 5 baseline.

---

## 2) Locked decisions applied

- **Q5 (curated layout):** the grid order, column spans, and widget composition are normative in §4. No code paths that rearrange them at runtime.
- **Q3 (project status inference):** dormancy chip on Active Projects is a **read-time** signal (see Step 7 §6.4). The UI never edits status here; that lives on `/projects` (Step 10).

---

## 3) Dependencies

- **Reads normative detail from:**
  - Step 0 — Luminous Codex design tokens, naming conventions.
  - Step 7 — `DashboardPayload` and `NarrativeData` shapes; field semantics; insight line copy templates; dormancy / recurring / follow-up rules.
  - Step 5 — TopNav structure (Inbox badge already added there); reused card / chip patterns.
- **Feeds:**
  - Step 10 — Inner Circle and Active Projects rows are the entry points to `/people/[id]` and `/projects/[id]`.
  - Step 11 / 12 — chat surfaces remain a sibling route; no dependency direction here.

---

## 4) Layout (Q5 fixed grid)

```
┌────────────────────────────────────────────────────────────────────────────┐
│  TopNav  (Dashboard · Inbox · People · Projects · Chat)                    │
├────────────────────────────────────────────────────────────────────────────┤
│  Header                                                                    │
│   "Command Center"   <window range>  ◀ ▶                                   │
│   StatPill row:  N days · M meals · K insights · S sessions · P proposals  │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  NarrativeSnapshot                                              full │  │
│  │  (entity-aware, comparative copy from Step 7 §11)                    │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌──────────────────────────────┐  ┌──────────────────────────────────┐   │
│  │  InnerCircleWidget           │  │  ActiveProjectsWidget            │   │
│  │  insight line + 6 person rows│  │  insight line + ≤8 project rows  │   │
│  │  link → /people/[id]         │  │  link → /projects/[id]           │   │
│  └──────────────────────────────┘  └──────────────────────────────────┘   │
│                                                                            │
│  ┌──────────────────────────────┐  ┌──────────────────────────────────┐   │
│  │  DiningLog                   │  │  ReflectionsPanel                │   │
│  │  repeat-visit badge          │  │  recurring + follow-up chips     │   │
│  └──────────────────────────────┘  └──────────────────────────────────┘   │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  LearningProgress                                              full  │  │
│  │  toggle: "Sessions" (current grid) ↔ "By subject" (timeline view)   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────┘
```

Container: `max-w-6xl mx-auto px-6 py-8`. Grid: `grid grid-cols-1 lg:grid-cols-2 gap-5`. Full-width widgets use `lg:col-span-2`.

Widget order (top → bottom) is intentional:
1. **Narrative** — the editorial headline; sets tone for the week.
2. **Inner Circle + Active Projects** — the V2 "longitudinal storyline" widgets, immediately reinforcing the narrative's references to people and projects.
3. **Dining + Reflections** — high-value-density carryovers from V1.
4. **Learning** — full-width because the new timeline view benefits from horizontal space.

The `max-w-` bumps from `5xl` (V1) to `6xl` to give the four side-by-side widgets enough breathing room.

---

## 5) File layout

### New files

```
frontend/src/components/dashboard/InnerCircleWidget.tsx
frontend/src/components/dashboard/ActiveProjectsWidget.tsx
frontend/src/components/dashboard/widgets/StreakDots.tsx
frontend/src/components/dashboard/widgets/SentimentBar.tsx
frontend/src/components/dashboard/widgets/InsightLine.tsx
frontend/src/components/dashboard/widgets/EmptyState.tsx
frontend/src/components/dashboard/LearningSubjectTimeline.tsx
```

### Modified files

```
frontend/src/app/page.tsx                              # bind to new payload, add new widgets
frontend/src/lib/api.ts                                # update DashboardData & NarrativeData
frontend/src/components/dashboard/NarrativeSnapshot.tsx
frontend/src/components/dashboard/DiningLog.tsx
frontend/src/components/dashboard/ReflectionsPanel.tsx
frontend/src/components/dashboard/LearningProgress.tsx
frontend/src/components/layout/TopNav.tsx              # add People + Projects placeholders
```

The `widgets/` subdirectory holds small reusable primitives (≈30 lines each) shared across multiple cards. Splitting them out keeps the parent components scannable.

---

## 6) API client updates (`lib/api.ts`)

Replace `DashboardData` and `NarrativeData` with shapes that mirror Step 7 §13 exactly. No optional escape hatches — this is a hard cutover with the backend change.

```typescript
export type Sentiment = "POSITIVE" | "NEGATIVE" | "NEUTRAL";

export type DashboardWindow = {
  start: string;
  end: string;
  previous_start: string;
  previous_end: string;
};

export type InnerCirclePerson = {
  person_id: number;
  canonical_name: string;
  relationship_type: string | null;
  mention_count_window: number;
  mention_count_previous: number;
  last_mention_date: string;
  last_mention_snippet: string | null;
  sentiment_distribution: Record<Sentiment, number>;
  dominant_sentiment: Sentiment | "MIXED" | null;
  days_since_last_mention: number;
};

export type ActiveProject = {
  project_id: number;
  name: string;
  category: string | null;
  status: "ACTIVE" | "PAUSED";
  update_count_window: number;
  update_count_previous: number;
  last_event_date: string;
  last_event_snippet: string | null;
  last_event_type: string | null;
  streak_dot_sequence: boolean[];   // length 7
  is_dormant: boolean;
  days_since_last_event: number;
  target_date: string | null;
};

export type DiningRow = {
  date: string;
  restaurant: string;
  dishes: string[];
  meal_type: string;
  sentiment: Sentiment | null;       // CHANGED from number
  description: string;
  visit_count_total: number;
  visit_count_window: number;
  is_repeat: boolean;
};

export type FollowUpLink = {
  matched_kind: "life_event" | "project_event";
  matched_count: number;
  sample_description: string;
  sample_date: string;
  project_id: number | null;
};

export type ReflectionRow = {
  date: string;
  topic: string;
  content: string;
  is_actionable: boolean;
  is_recurring: boolean;
  follow_up: FollowUpLink | null;
};

export type LearningRow = {
  date: string;
  subject: string;
  milestone: string;
  description: string;
  sentiment: Sentiment | null;       // CHANGED from number
};

export type LearningSubjectTimeline = {
  subject: string;
  sessions_window: number;
  last_milestone: string | null;
  last_session_date: string;
  sentiment_distribution: Record<Sentiment, number>;
};

export type DashboardPayload = {
  has_data: boolean;
  window: DashboardWindow | null;
  inner_circle: InnerCirclePerson[];
  inner_circle_total: number;
  inner_circle_insight: string | null;
  active_projects: ActiveProject[];
  active_projects_total: number;
  active_projects_insight: string | null;
  dining: DiningRow[];
  reflections: ReflectionRow[];
  learning: LearningRow[];
  learning_by_subject: LearningSubjectTimeline[];
};

export type NarrativeData = {
  content: string;
  window_start: string;              // RENAMED from week_start
  window_end: string;                // RENAMED from week_end
  generated_at: string | null;
  cached: boolean;
};
```

Function signatures unchanged:

```typescript
export async function getDashboardData(signal?: AbortSignal, refDate?: string): Promise<DashboardPayload>;
export async function getDashboardNarrative(signal?: AbortSignal, refDate?: string): Promise<NarrativeData>;
```

The existing `DashboardData` alias is removed; `DashboardPayload` is the only exported type. Any frontend file that still imports `DashboardData` is updated in the same PR.

---

## 7) Page shell (`app/page.tsx`)

Re-bind the existing component:

- State types: `useState<DashboardPayload | null>(null)`.
- Window source: `data?.window?.end` replaces the V1 `data?.date_range?.end`.
- Stat pills update to use the new payload:
  - `days` — count of unique dates across `dining + reflections + learning + inner_circle.last_mention_date + active_projects.last_event_date` clipped to the window. Falls back to V1 calculation if the new arrays are all empty.
  - `meals` — `data.dining.length`.
  - `insights` — `data.reflections.length`.
  - `sessions` — `data.learning.length`.
  - **NEW:** `people` — `data.inner_circle_total`, color `var(--chart-3)`.
  - **NEW:** `projects` — `data.active_projects_total`, color `var(--chart-4)`.
- Pass `window={data.window}` to widgets that compare current vs previous (for "vs N last week" copy).

The Prev/Next buttons keep the existing 7-day shift; they now move `data.window.end` instead of `data.date_range.end`.

The error and loading paths are unchanged; only field references move.

---

## 8) NarrativeSnapshot (polished)

Visual treatment unchanged (full-width, gradient surface, accent glow). Updates:

- Props rename: `weekStart`/`weekEnd` → `windowStart`/`windowEnd`.
- Date pill format unchanged (`Apr 21 — Apr 27, 2026`).
- Subline label changes from "AI-Generated Summary" to **"Comparative summary"** when `cached === false` and to **"Cached summary"** when `cached === true`. Mono, accent-color, 10px.
- Empty state copy unchanged: `"No journal data available for this week yet."`
- A small `Regenerate` ghost button in the header, visible only when `cached === true` and the cursor is over the card. Wired to a future `POST /api/dashboard/narrative/refresh` endpoint — **not** implemented in Step 8; the button calls a noop with a toast `"Regenerate is coming in a later update."`. Keeps the UI affordance present without backend work.

The narrative service in Step 7 already produces the comparative + entity-aware text; the UI does not need to do any extra parsing.

---

## 9) InnerCircleWidget

### 9.1 Anatomy

```
┌────────────────────────────────────────────────┐
│ ◯ Inner Circle                  6 of 14 people │
│ "You connected with 4 people this week — Sam   │
│  most often."                                  │
│                                                │
│ ┌──────────────────────────────────────────┐   │
│ │ │ Sam Chen          friend          ★ 3 │   │
│ │ │ "Lunch at Lula together — easy day."  │   │
│ │ │ POSITIVE • POSITIVE • NEUTRAL         │   │
│ │ └──────────────────────────────────────┘    │
│   ...                                          │
│                                                │
│ ↗ See all (link: /people)                      │
└────────────────────────────────────────────────┘
```

### 9.2 Header

- Icon: small "circle of people" SVG, accent color `var(--chart-3)` (chart palette teal — consistent with the InnerCircle entity-type chip used in inbox).
- Title: `"Inner Circle"` (font-heading, 14px).
- Right-aligned counter pill: `"{inner_circle.length} of {inner_circle_total} people"` (mono, 10px, accent surface). Hidden when `inner_circle_total === 0`.

### 9.3 Insight line

`InsightLine` component renders `inner_circle_insight` (Step 7 server-precomputed copy). Subtle italic, `var(--color-brand-text-dim)`, 12px, with a top margin of 4px and bottom margin of 12px.

### 9.4 Person row

Card style: `rounded-lg bg-[var(--color-brand-bg)] px-3 py-2.5` matching DiningLog rows. Left rule colored by `dominant_sentiment`:

- POSITIVE → `var(--color-brand-accent-green)`
- NEGATIVE → `var(--color-brand-accent-rose)`
- NEUTRAL → `var(--color-brand-muted)`
- MIXED → `var(--chart-5)`
- null → `var(--color-brand-border)`

Top row:
- Canonical name (text-sm, font-medium).
- Relationship chip (`relationship_type`) when present, color `var(--chart-3)`. Hidden when null.
- Right-aligned mono count `★ {mention_count_window}` (★ = saffron star). When `mention_count_previous > 0`, render delta arrow:
  - `↑+N` if window > previous, color green.
  - `↓-N` if window < previous, color amber.
  - `=` if equal.

Body:
- One-line truncated `last_mention_snippet` (italic, 11px, `text-dim`). Hidden when null.

Footer micro-row:
- `SentimentBar` — three filled segments with proportions from `sentiment_distribution`. Tooltip on hover: full counts.
- Right-aligned: `last_mention_date` formatted `Apr 24` (mono, 10px, muted).

Whole row is a `<Link href={\`/people/${person_id}\`}>`. Hover: row background lifts to `bg-[var(--color-brand-bg)]/80` (matches existing DiningLog hover).

### 9.5 Empty state

Use shared `EmptyState` primitive:

```
🌑  Quiet week
No people surfaced from this week's entries yet.
```

Replace the moon emoji with a stroked circle SVG to keep the no-emoji rule (line up with Luminous Codex aesthetic, this is intentional UI affordance, not communication-emoji — so we use SVG). When `inner_circle_total > 0` but `inner_circle.length === 0` (impossible per Step 7 logic, defensive), copy is `"No interactions in this window."`

### 9.6 Footer link

Bottom-aligned ghost link `↗ See all` → `/people` (Step 10 placeholder). Always visible when `inner_circle_total > inner_circle.length`. Style: `text-[var(--color-brand-accent)]/80 hover:text-[var(--color-brand-accent)] text-xs font-mono`.

---

## 10) ActiveProjectsWidget

### 10.1 Anatomy

```
┌──────────────────────────────────────────────────┐
│ ◧ Active Projects                  3 of 5 active │
│ "3 of 5 active projects saw progress this week." │
│                                                  │
│ ┌────────────────────────────────────────────┐   │
│ │ │ Portuguese  fitness  ACTIVE     ★ 4    │   │
│ │ │ ●●○●○●○   ←  daily streak (Mon→Sun)    │   │
│ │ │ "Finished B1 unit on direct pronouns." │   │
│ │ └────────────────────────────────────────┘    │
│ │ │ Urban Garden  creative  ACTIVE  dormant│   │
│ │ │ ○○○○○○○                                │   │
│ │ │ "Last update 18 days ago."             │   │
│ │ └────────────────────────────────────────┘    │
│   ...                                            │
│                                                  │
│ ↗ See all (link: /projects)                      │
└──────────────────────────────────────────────────┘
```

### 10.2 Header / insight line

Mirror Inner Circle. Icon color `var(--chart-4)` (chart palette ochre). Counter pill: `"{active_projects.length} of {active_projects_total} active"`.

### 10.3 Project row

Card style same as Inner Circle. Left rule color by status:

- ACTIVE → `var(--chart-4)`
- PAUSED → `var(--color-brand-muted)`
- (COMPLETED / ABANDONED never appear — Step 7 §6.1 filters them out.)

Top row:
- Project name (font-medium, text-sm).
- Category chip (`category` value, when present), color `var(--chart-4)/70`.
- Status chip `ACTIVE` / `PAUSED` (saffron / muted respectively).
- Right-aligned mono `★ {update_count_window}` plus delta arrow vs `update_count_previous` (same rules as Inner Circle).

Streak row:
- `StreakDots` — 7 dots, oldest left → newest right, mapped from `streak_dot_sequence`. Filled `var(--chart-4)`, empty `var(--color-brand-border)`. 6px radius, 4px gap.

Body:
- `last_event_snippet` (italic, 11px) when present.
- When `is_dormant === true`: replace snippet with copy `"Last update {days_since_last_event} days ago."` and add a small `dormant` chip (color `var(--color-brand-accent-rose)/70`, no fill). Dormant chip lives in the top row alongside status chip.

Footer micro-row:
- Last event type chip (lowercase, monochrome) when present.
- Right-aligned: `last_event_date` (mono, 10px, muted).

Whole row links to `/projects/${project_id}`.

### 10.4 Empty state

```
◇ No active projects
Confirm a project from your inbox to start tracking.
```

When the inbox has pending project proposals, the second line becomes a ghost link to `/inbox?type=project`.

### 10.5 Footer link

`↗ See all` → `/projects` when `active_projects_total > active_projects.length`.

---

## 11) DiningLog (polished)

### 11.1 Visual changes

- **Sentiment**: switch from float-derived helpers to `Sentiment | null`:
  - `POSITIVE` → green
  - `NEGATIVE` → rose
  - `NEUTRAL` / null → muted
- Drop `sentimentColor(score: number)` and `sentimentLabel(score: number)` helpers.
- Header counter pill text: `{dining.length} meals · {repeat_count} repeat` when `repeat_count > 0`, else `{dining.length} meals`. `repeat_count = dining.filter(d => d.is_repeat).length`.

### 11.2 Repeat-visit badge

When `d.is_repeat === true`, append a small chip after the restaurant name:

```
Lula Cafe   • {visit_count_total}× visit
```

Chip: rounded-full, mono, `bg-[var(--color-brand-accent)]/10 text-[var(--color-brand-accent)] px-2 py-0.5 text-[9px]`. The `×` is the multiplication sign U+00D7.

If `visit_count_window > 1` (multiple visits this week to the same place), append `· {visit_count_window} this week` to the chip with a separator dot.

### 11.3 Empty state copy unchanged

`"No dining events this week."` still applies.

---

## 12) ReflectionsPanel (polished)

### 12.1 Visual changes

- Add `recurring` chip next to the topic when `r.is_recurring === true`. Style: `rounded-full bg-[var(--chart-5)]/10 text-[var(--chart-5)] px-2 py-0.5 text-[9px] uppercase`. Copy: `recurring`.
- When `r.follow_up !== null`, render a marginalia footer block:

```
┌───────────────────────────────────────────────┐
│  ↳ followed up by · life event                │
│    "Logged 3 runs this week"                  │
│    Apr 25                                     │
└───────────────────────────────────────────────┘
```

Style: indented 12px, accent left rule (1px, `var(--color-brand-accent)/40`), `text-[10px] text-[var(--color-brand-text-dim)]`. The `↳` glyph leads the line. When `matched_kind === "project_event"` and `project_id !== null`, the snippet wraps in a `<Link href={\`/projects/${project_id}\`}>`.

The follow-up block sits **after** the reflection content, inside the same `<li>`.

### 12.2 Header counter pill

Adds `"X recurring"` mono pill when `recurring_count > 0`, alongside the existing `"X action"` and `"X total"` pills.

### 12.3 Ordering

The server already sorts actionable → recurring → date DESC. The component renders rows as-received without re-sorting.

### 12.4 Topic colors

The hardcoded `TOPIC_COLORS` map stays as a fallback. When `is_recurring === true`, the left rule color is forced to `var(--chart-5)` to visually link the recurring chip to the rule.

---

## 13) LearningProgress (polished)

### 13.1 View toggle

Header right side adds a segmented control:

```
[ Sessions ]  [ By subject ]
```

State: local `viewMode: "sessions" | "subject"`, default `"sessions"`. Toggle is a small ghost-style button pair, saffron underline on active. ARIA: `role="radiogroup"`, each button `role="radio"` `aria-checked`.

### 13.2 Sessions view (default)

Renders `data.learning` in the existing card grid. Sentiment chip is added (was extracted but unrendered in V1):

- Chip placed bottom-right of each card, same style as DiningLog sentiment chip, color by sentiment label.

### 13.3 By-subject view

Renders `data.learning_by_subject` as a vertical list — one row per subject. Each row:

```
Portuguese                            4 sessions this week
●●●○○                                    last: B1 direct pronouns
                                                Apr 25
```

- Left: subject (font-medium, text-sm) + sentiment dot sequence (5 dots, see §13.4).
- Right column: `sessions_window` count, `last_milestone` (when present), `last_session_date`.

Subject color uses the existing `SUBJECT_COLORS` keyword map.

### 13.4 Sentiment dot sequence

Five dots representing `sentiment_distribution`. Filled green for POSITIVE count, muted for NEUTRAL, rose for NEGATIVE, normalized to a 5-slot proportion. Implementation: pick the largest counts first, fill dots in order POSITIVE → NEUTRAL → NEGATIVE. If total < 5, leave trailing dots empty (border only).

### 13.5 Empty state

Sessions view: `"No learning events this week."` (unchanged).
By-subject view: `"No subjects logged this week."`

---

## 14) Reusable widget primitives

### 14.1 `StreakDots`

```typescript
type Props = { sequence: boolean[]; activeColor: string };
```

Renders `sequence.length` circles. Filled with `activeColor` when `sequence[i]` is true, otherwise outlined with `var(--color-brand-border)`. Width auto, gap-1.

### 14.2 `SentimentBar`

```typescript
type Props = { distribution: Record<Sentiment, number>; height?: number };
```

A 3-segment horizontal bar with segment widths proportional to counts. Colors: green / rose / muted for POSITIVE / NEGATIVE / NEUTRAL. Tooltip shows `"3 positive · 1 neutral · 0 negative"`. Falls back to a single muted segment when total is 0.

### 14.3 `InsightLine`

```typescript
type Props = { children: React.ReactNode };
```

Wraps server-rendered insight copy in `text-xs italic text-[var(--color-brand-text-dim)] mt-1 mb-3`. Renders nothing when `children` is null/empty (so it doesn't reserve vertical space on quiet weeks).

### 14.4 `EmptyState`

```typescript
type Props = { icon: React.ReactNode; title: string; subtitle?: React.ReactNode };
```

Centered column layout, 32px icon, 13px heading, 11px subtitle. Reused across new widgets.

---

## 15) TopNav update

Add two new nav items between Inbox and Chat:

```
{ href: "/people", label: "People", icon: <users icon> }
{ href: "/projects", label: "Projects", icon: <kanban icon> }
```

Until Step 10 ships, both routes resolve to a placeholder page `frontend/src/app/people/page.tsx` and `frontend/src/app/projects/page.tsx`:

```
<main className="flex-1 flex items-center justify-center text-sm text-[var(--color-brand-text-dim)]">
  Coming in the next update.
</main>
```

These placeholder pages are Step 8 deliverables so the TopNav and the dashboard widget links never 404. Step 10 replaces them with real surfaces.

---

## 16) Visual conformance (Luminous Codex)

- Cards: `rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] p-5` (matches existing widgets).
- Section header pattern: 8×8 rounded square icon container in tinted accent + 14px Instrument Serif heading + ghost counter pill.
- Per-row cards: `rounded-lg bg-[var(--color-brand-bg)] px-3 py-2.5` with 3px colored left rule.
- All chips: `rounded-full px-2 py-0.5 text-[9px]` mono uppercase or 10px mono lowercase depending on chip type (status vs metadata) — already established by inbox spec.
- Dates: mono 10px muted (`text-[var(--color-brand-muted)]`).
- Numbers: monospace IBM Plex Mono.
- Hover: `bg-[var(--color-brand-bg)]/80` row lift.
- Focus rings: rely on browser defaults plus existing global `*:focus-visible` style. New link rows use `focus-visible:outline-2 focus-visible:outline-[var(--color-brand-accent)]/60` like the existing inbox list items.

---

## 17) State, refetch, and cross-route invalidation

The dashboard remains a **read-only** page that fetches `dashboardData` and `narrative` on mount and on `refDate` change. No mutations from this page.

Cross-route side effects:
- After the user resolves an inbox proposal (Step 5 flow) and navigates to `/`, the dashboard re-fetches because the page mounts fresh. No global cache to invalidate.
- A future improvement is a small `dashboardCache` keyed on `refDate`, but Step 8 ships without caching to keep behavior obvious. Step 13 may revisit.

Effects:
- `mounted` guard kept (prevents Next.js hydration mismatch on date strings).
- `AbortController` cleanup unchanged.
- Narrative fetch failure remains non-fatal (toastless), matching V1 behavior.

---

## 18) Loading & error states

- **Loading:** every widget shows skeleton blocks (already implemented for V1 widgets; Inner Circle and Active Projects mirror the same pattern with 4 placeholder rows of `h-14 animate-pulse rounded-lg bg-[var(--color-brand-border)]/50`).
- **Error:** the page-level error card in `app/page.tsx` handles network/API failure. Per-widget errors are not shown — Step 7's payload either succeeds whole or fails whole.
- **Empty data:** `data.has_data === false` keeps the existing blank-corpus message at the page level. Each widget's individual empty state covers the case where there is data overall but nothing in this widget for the window.

---

## 19) Accessibility

- All widgets in `<section aria-labelledby="...">` with the heading carrying the matching id.
- Person and project rows are `<Link>` so they are keyboard-focusable and Enter-activated; `aria-label` includes the name + count.
- Sentiment chips and dormancy chips include screen-reader-only text (e.g. `<span className="sr-only">positive sentiment</span>`).
- Streak dots: container has `role="img" aria-label="streak: 4 of 7 days"` (computed).
- Color is never the only signal — every chip carries text.
- View toggle in LearningProgress uses `radiogroup` semantics.

---

## 20) Testing plan

The repo has no frontend test harness (Step 13 will introduce Playwright/Vitest). Step 8 testing is **manual + visual**:

### 20.1 Manual smoke (with the synthetic journals seeded, Step 7 backend live)

1. Run ingest → shred → resolve.
2. Resolve a few inbox proposals so Inner Circle / Active Projects have rows.
3. Open `/`. Verify:
   - Window range matches latest entry.
   - All seven widgets render with non-empty data when the corpus supports it.
   - Stat pills include `people` and `projects` counts.
   - Inner Circle row click → `/people/<id>` (placeholder page).
   - Active Projects row click → `/projects/<id>` (placeholder page).
   - Dormant chip appears for a project intentionally aged past 14 days in fixture data.
   - Recurring chip appears on a reflection seeded across two consecutive weeks.
   - Follow-up footer appears on an actionable reflection whose keywords match a current-week event.
   - Repeat-visit badge on Lula Cafe.
4. Use Prev/Next arrows to scroll back through windows; verify all widgets re-render and insight lines update.
5. Toggle Learning By-subject view. Verify timeline rows match expected counts.

### 20.2 Visual regression (manual screenshots)

Capture at 1280px width:
- Full dashboard, populated week.
- Empty corpus.
- Mid-corpus quiet week (some widgets empty, others populated).
- Loading state (throttle network in DevTools).

Save as `docs/journallm-v2/assets/step-08-dashboard-{state}.png` for posterity. (Optional — directory is created lazily.)

### 20.3 Type check

`tsc --noEmit` in `frontend/` must pass after the API client changes. Since the type changes are intentional contract updates, any consumer that still references `DashboardData`, `week_start`, `week_end`, or `sentiment as number` is rewired.

### 20.4 Component tests (deferred)

Step 5 documented this same deferral. Step 8 does not add test infra; Step 13 is the pickup point.

---

## 21) Performance notes

- Total payload size for a full week with 6 inner-circle rows + 8 active-project rows + ~20 dining + ~5 reflections + ~10 learning = **<25KB** gzipped. Fits in one round-trip.
- All rendering is server-component-friendly (no client-side fetching besides the existing pattern). The dashboard remains a `"use client"` page because of state hooks, but the widgets themselves can be pure presentational components.
- No new images or fonts.
- Hover and focus styles use CSS only; no JS state for hover.

---

## 22) Backlog (explicitly deferred)

1. **Configurable layout / hide-show controls** — Locked Q5; ships post-V2 when curated grid is proven.
2. **Inline regenerate button on NarrativeSnapshot** — UI affordance present in §8 but the backend endpoint and client wiring ship later.
3. **In-page entity hover cards** — preview a person/project's last few mentions in a popover without navigating away. Phase 5 polish.
4. **Sparkline arrays** — once Step 7 adds them.
5. **Whoop overlays** — Phase 5 health correlation (§5.4).
6. **People / Projects detail pages** — Step 10.
7. **Frontend test harness** — Step 13.

---

## 23) Definition of done

Step 8 is complete when:

- `/` renders all seven widgets in the Q5 fixed grid against the V2 `DashboardPayload`.
- Inner Circle and Active Projects show server-precomputed insight lines and surface row-level chips per §9 and §10.
- Polished Dining / Reflections / Learning surfaces render the new fields (repeat badge, recurring + follow-up, sentiment dot sequence and timeline view).
- Frontend types in `lib/api.ts` exactly mirror Step 7's response.
- TopNav exposes People and Projects items; both link to placeholder pages so navigation never 404s.
- All pre-existing dashboard interactions (Prev/Next, narrative fetch, error card) still work.
- `tsc --noEmit` passes.
- Manual smoke per §20.1 succeeds with the synthetic journals.
- No console errors on mount or window navigation.

---

## Changelog

- 2026-04-27 — Initial complete Step 8 spec. Defines the V2 Command Center layout (one curated grid per Q5), introduces Inner Circle and Active Projects widgets driven entirely by Step 7's precomputed payload, polishes existing widgets with repeat-visit / recurring / follow-up / per-subject-timeline affordances, ships the type changes for sentiment enums and narrative window-keyed fields, and adds People/Projects TopNav entries with placeholder routes so cross-page navigation works ahead of Step 10.
