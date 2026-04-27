# Step 5 — Entity inbox UI (frontend)

**Index:** [README.md](./README.md)  
**Plan reference:** [JOURNALLM_V2_IMPLEMENTATION_PLAN.md](../../JOURNALLM_V2_IMPLEMENTATION_PLAN.md)  
**Status:** Complete (spec baseline ready for implementation)  
**Ideation refs:** §1.5, Locked Q1, Q2.

---

## 1) Scope

### In scope

- New top-level Next.js route `/inbox` for reviewing pending entity proposals.
- TopNav badge surfacing pending count from `/api/entity-inbox/proposals/summary`.
- Two-pane inbox layout (list + detail) with filters, actions, and inline feedback.
- Action forms wired to all Step 4 endpoints: confirm-new, merge, dismiss, blocklist (person & project), reject (project).
- Blocklist management drawer (read + delete, no manual create — matches Step 4 §8.2).
- Empty / loading / error states styled in Luminous Codex tokens.
- Keyboard accessibility: ESC closes modals, action buttons focusable, list rows arrow-navigable.
- Toast-style outcome feedback summarizing `mentions_created` / `events_created` / `cascaded_proposal_ids` from `ActionResult`.

### Out of scope

- Second-pass LLM "Likely same as X" hint badge — deferred to backlog (§1.5 mentions it only as UI assist; not part of Step 4 API).
- People / Projects detail pages (Step 10).
- Bulk actions across multiple proposals at once — single-proposal flows only.
- Manual blocklist creation form — only delete is supported (Step 4 §8.2).
- Mobile-first layout. The inbox targets ≥1024px desktop; below that, the list collapses above the detail (single column).

---

## 2) Dependencies

- **Reads normative detail from:**
  - Step 4 — endpoint contracts, request/response shapes, error semantics.
  - Step 0 — design system tokens, naming conventions.
- **Feeds:**
  - Step 6 — backfill operations may surface progress against the same inbox; must coexist.
  - Step 8 — once entities are confirmed, dashboard widgets (Inner Circle, Active Projects) populate; the inbox unblocks them.
- **Reuses existing frontend modules:**
  - `frontend/src/lib/api.ts` — extended with inbox client functions.
  - `frontend/src/components/layout/TopNav.tsx` — extended with inbox link + badge.
  - `frontend/src/components/chat/ConfirmDialog.tsx` — pattern reused for blocklist/dismiss confirmations.

---

## 3) Routes & files

New files:

```
frontend/src/app/inbox/page.tsx
frontend/src/components/inbox/InboxLayout.tsx
frontend/src/components/inbox/ProposalList.tsx
frontend/src/components/inbox/ProposalListItem.tsx
frontend/src/components/inbox/ProposalDetail.tsx
frontend/src/components/inbox/PayloadPreview.tsx
frontend/src/components/inbox/CandidateList.tsx
frontend/src/components/inbox/ActionPanelPerson.tsx
frontend/src/components/inbox/ActionPanelProject.tsx
frontend/src/components/inbox/ConfirmNewPersonForm.tsx
frontend/src/components/inbox/ConfirmNewProjectForm.tsx
frontend/src/components/inbox/MergeForm.tsx
frontend/src/components/inbox/RejectProjectDialog.tsx
frontend/src/components/inbox/BlocklistDrawer.tsx
frontend/src/components/inbox/InboxToast.tsx
frontend/src/components/inbox/InboxBadge.tsx
frontend/src/lib/inbox-api.ts
```

Route registration: App Router auto-discovers `app/inbox/page.tsx`. The TopNav already pattern-matches by `pathname.startsWith(href)` so `/inbox` lights up correctly once added.

---

## 4) API client extensions

New module `frontend/src/lib/inbox-api.ts` (separate from `api.ts` to keep that file lean):

### Types (mirror Step 4 Pydantic schemas)

```typescript
export type ProposalStatus =
  | "pending"
  | "accepted_new"
  | "merged_existing"
  | "dismissed"
  | "rejected"
  | "blocked";

export type EntityType = "person" | "project";

export type CandidateMatch = {
  entity_id: number;
  canonical_name: string;
  score: number;
  signals: {
    exact_prefix: boolean;
    token_overlap: number;
    edit_distance_ratio: number;
  };
};

export type ProposalSummary = {
  id: number;
  entity_type: EntityType;
  status: ProposalStatus;
  surface_name: string;
  entry_date: string;
  life_event_id: number | null;
  created_at: string;
  resolved_at: string | null;
};

export type PersonMentionPayload = {
  name: string;
  relationship_hint: string | null;
  interaction_context: string | null;
  linked_event_hint: string | null;
  sentiment: string | null;
};

export type ProjectEventPayload = {
  project_name: string;
  event_type: string;
  description: string;
  linked_event_hint: string | null;
  suggested_project_status: string | null;
};

export type ProposalDetail = ProposalSummary & {
  payload: { mentions?: PersonMentionPayload[]; events?: ProjectEventPayload[] };
  candidate_matches: CandidateMatch[];
  resolution_entity_id: number | null;
  resolution_note: string | null;
};

export type ActionResult = {
  proposal: ProposalDetail;
  entity_id: number | null;
  mentions_created: number;
  events_created: number;
  status_transitions: number;
  cascaded_proposal_ids: number[];
  cascade_truncated: boolean;
  warnings: string[];
};

export type InboxSummary = {
  pending_person: number;
  pending_project: number;
  total_pending: number;
  oldest_pending_entry_date: string | null;
};

export type BlocklistEntry = {
  id: number;
  entity_type: EntityType;
  surface_name: string;
  reason: "manual_block" | "system_noise" | null;
  created_at: string;
};
```

### Functions

```typescript
listProposals(params: {
  status?: ProposalStatus[];        // default ['pending']
  entity_type?: EntityType;
  entry_date_from?: string;
  entry_date_to?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<{ total: number; items: ProposalSummary[] }>;

getProposal(id: number): Promise<ProposalDetail>;
getInboxSummary(): Promise<InboxSummary>;

confirmNewPerson(id: number, body: ConfirmNewPersonBody): Promise<ActionResult>;
mergePerson(id: number, body: MergePersonBody): Promise<ActionResult>;
confirmNewProject(id: number, body: ConfirmNewProjectBody): Promise<ActionResult>;
mergeProject(id: number, body: MergeProjectBody): Promise<ActionResult>;
rejectProject(id: number, body: RejectProjectBody): Promise<ActionResult>;
dismissProposal(id: number, body: DismissBody): Promise<ActionResult>;
blocklistProposal(id: number, body: BlocklistBody): Promise<ActionResult>;

listBlocklist(entity_type?: EntityType): Promise<BlocklistEntry[]>;
deleteBlocklistEntry(id: number): Promise<void>;
```

All functions use the existing `requestJson` helper from `lib/api.ts`. List/summary calls accept an optional `AbortSignal` for the standard cleanup pattern.

Errors: `ApiError` already maps `409` body shape (`{detail, current_status, resolved_at}` or `{detail, existing_id}`). UI surfaces both via toast (`current_status` triggers refetch; `existing_id` triggers an inline "merge instead?" affordance).

---

## 5) Page layout (`/inbox`)

```
┌──────────────────────────────────────────────────────────────────────┐
│  TopNav (existing)                                                   │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Inbox Header                                                        │
│   "Entity Inbox" · "X pending"  [Filters bar]  [Blocklist (n)]       │
│                                                                      │
│  ┌──────────────────┐  ┌─────────────────────────────────────────┐   │
│  │ Proposal List    │  │ Selected Proposal Detail                │   │
│  │  (left, ~360px)  │  │  surface · type · entry_date            │   │
│  │                  │  │                                         │   │
│  │  - Sam      …    │  │  Payload preview                        │   │
│  │  - Alex Y   …    │  │  Candidate matches (ranked)             │   │
│  │  - Lula's   …    │  │  Action panel (Confirm/Merge/Dismiss…)  │   │
│  │  - Portuguese    │  │                                         │   │
│  │   …              │  │                                         │   │
│  └──────────────────┘  └─────────────────────────────────────────┘   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

Container: `max-w-6xl mx-auto px-6 py-8`, `flex gap-6 lg:flex-row flex-col`.

### Header

- Title: `font-heading text-2xl tracking-tight` "Entity Inbox".
- Subline: monospace count `<n> pending · oldest <date>` from `getInboxSummary`.
- Filter bar (right side): status tabs (`Pending` default · `Resolved` · `All`), entity-type pill toggle (`All` / `People` / `Projects`), text input for search, date range optional (collapsed under a button).
- Blocklist drawer trigger: small ghost button "Blocklist (n)" — opens drawer.

### List pane (`ProposalList` + `ProposalListItem`)

- Each item card shows:
  - Top row: surface name (heading-weight), entity-type chip (`person` saffron / `project` chart-3 color).
  - Second row: `entry_date` mono, life-event link icon if present.
  - Third row: smallest text: top candidate's canonical name + score, or "no candidates".
- Selected item: saffron left border + accent background wash (matches existing sidebar style).
- Keyboard: ↑ / ↓ change selection, `Enter` opens detail (already opened — Enter does nothing if same), `1`-`9` jumps action buttons within detail (advanced; document but optional in MVP).
- Pagination: simple `Load more` button when `total > items.length`. Default page size 50.

### Detail pane (`ProposalDetail`)

When no proposal selected: empty hero illustration + copy `"Select a proposal to review"`.

When selected:
- Header strip: surface name big, entity-type chip, status pill, copy-to-clipboard for the surface string.
- `PayloadPreview` (§7) renders mentions/events list verbatim, including `interaction_context` snippets and `linked_event_hint`.
- `CandidateList` (§8) renders ranked merge candidates.
- `ActionPanelPerson` or `ActionPanelProject` (§9) renders the action UI.
- Right-side meta column when ≥1280px width: created_at, resolved_at if applicable, resolution_note.

---

## 6) Filter behavior

URL query params govern state so a refresh keeps context:

```
/inbox?status=pending&type=person&from=2026-01-01&to=2026-04-30&search=Sam
```

Filters drive `listProposals` calls. Default URL when no params: `?status=pending`.

When the user opens a proposal, route updates to:

```
/inbox/<id>?<filters preserved>
```

The page uses Next.js dynamic segment? **Decision:** stay on a single `/inbox` page and track the selected id in `?selected=<id>` to keep the list and detail in one route, simpler state. The dynamic `/inbox/[id]/page.tsx` is *not* introduced in Step 5.

---

## 7) Payload preview component

`PayloadPreview` accepts `ProposalDetail`.

For `entity_type === "person"`:

```
Person mention(s) — N occurrence(s)
┌─────────────────────────────────────────────┐
│ "interaction_context …"                     │
│ relationship_hint · sentiment chip          │
│ linked event: "<description>" (if present)  │
└─────────────────────────────────────────────┘
```

For `entity_type === "project"`:

```
Project event(s) — N occurrence(s)
┌─────────────────────────────────────────────┐
│ event_type chip · description               │
│ suggested_project_status chip (if present)  │
│ linked event: "<description>" (if present)  │
└─────────────────────────────────────────────┘
```

Rendered with marginalia treatment per Luminous Codex (left rule, indent, dim secondary text). Sentiment chips use `--color-brand-accent-green` (POSITIVE), `--color-brand-accent-rose` (NEGATIVE), `--color-brand-muted` (NEUTRAL).

If `payload` arrays are missing/empty (legacy data), show `"Payload empty — accept will create a no-mention/no-event entity row."` so the user is not surprised.

---

## 8) Candidate list component

`CandidateList` shows up to 5 ranked candidates from `proposal.candidate_matches`. Each row:

- Canonical name (heading), small score percentage `(72%)` mono.
- Signal badges: `exact prefix`, `token overlap N%`, `edit Δ N%`.
- Primary action button: `"Merge into <name>"`. Clicking pre-fills `MergeForm` and scrolls action panel into focus.

Empty state: `"No similar entities found. You can confirm as new or dismiss."`

The component never auto-merges (Q2). Score badges are presentational only.

---

## 9) Action panels

### 9.1 `ActionPanelPerson`

Tabs / segmented control: **Confirm new** · **Merge existing** · **Dismiss** · **Blocklist**.

Default tab when there are candidates: **Merge existing** (pre-selecting top candidate). Default tab otherwise: **Confirm new**.

#### Confirm new tab — `ConfirmNewPersonForm`

Fields:
- `canonical_name` text — defaults to `proposal.surface_name`. Trimmed before submit.
- `aliases` chips input — initially empty. ENTER adds; X removes.
- `relationship_type` text — optional, autocomplete suggestions: friend, colleague, family, client, partner.
- `notes` textarea — optional.

Submit: `confirmNewPerson(id, {...})`. Disabled until `canonical_name` is non-empty after trim.

On `409 existing_id`: show inline alert *"A person with that name already exists."* + button to switch to **Merge existing** tab pre-pointed at the existing entity.

#### Merge existing tab — `MergeForm`

- Target selector: list of all `people` (fetched once on detail open via a new minimal `GET /people` shim — **not** introduced here; instead, target selection is restricted to candidates already shown in `CandidateList`. If user wants to merge into someone not in the candidate list, they must add an alias by visiting the People page in Step 10. Documented limitation for MVP).

  **Decision:** Step 5 supports merging only into one of the displayed candidates. This avoids needing a Step 10-shaped people fetcher prematurely. Add a small note in the empty candidate state: *"No candidate to merge into. Use 'Confirm new' to create the entity, then add aliases later."*
- Toggle: `Add "<surface_name>" as alias` (default ON).
- Optional extra aliases chip input.

Submit: `mergePerson(id, {...})`.

#### Dismiss tab

- Note textarea (optional).
- Confirm button: secondary style.
- Confirmation `ConfirmDialog` warning that the same surface may re-appear in future runs.

#### Blocklist tab

- Reason dropdown: `manual_block` (default) / `system_noise`.
- Note textarea (optional).
- Toggle: `Cascade pending duplicates` (default ON).
- Confirmation `ConfirmDialog` warning that the surface will be blocked from future proposal creation, and showing how many other pending proposals will be silenced (computed client-side from cached list filtering by surface_name).

### 9.2 `ActionPanelProject`

Tabs: **Confirm new** · **Merge existing** · **Reject** · **Dismiss** · **Blocklist**.

#### Confirm new — `ConfirmNewProjectForm`

Fields beyond person form:
- `category` text input.
- `status` select: ACTIVE (default) · PAUSED · COMPLETED · ABANDONED.
- `description` textarea.
- `target_date` date input.

Same `409 existing_id` handling as person.

UI hint when `payload.events` includes `start`/`milestone`/`pause` etc.: small note: *"Replay events will adjust status starting from the value above."* — communicates Step 4 §9.2 contract.

#### Merge existing

Same as person merge (candidates only). After merge, surface a chip showing predicted final status if any events would transition it.

#### Reject — `RejectProjectDialog`

Modal with two radio options:
- **Dismiss this time only.**
- **Blocklist** name. Cascade explanation copy.

Plus optional note.

Submit: `rejectProject(id, { mode, note })`.

#### Dismiss / Blocklist

Same as person tabs. (The shared `dismiss` and `blocklist` endpoints work for both entity types — Step 4 routed them as such.)

---

## 10) Outcome feedback

After every action returns an `ActionResult`, the page surfaces an `InboxToast` for ~5 seconds in the top-right:

- **Success copy template:**
  > Confirmed `<surface_name>` as new person.
  > 3 mentions linked. 2 cascaded proposals resolved.
- For project: `events_created`, `status_transitions`, `cascaded_proposal_ids.length`.
- If `cascade_truncated`: append `"(cascade truncated — re-run inbox to clean up the rest)"`.
- If `warnings.length > 0`: append a "Show warnings" link that expands the inline list.

After action:
1. Refetch `getInboxSummary` to update the TopNav badge.
2. Refetch the proposal list with current filters.
3. Auto-select the next pending proposal in the list (or empty state if none).

---

## 11) Blocklist drawer

`BlocklistDrawer` opens from header button. It is a right-side slide-in panel (≈420px) showing:
- Tabs: All · People · Projects.
- List of `BlocklistEntry` rows: surface_name, type chip, reason chip, created_at mono.
- Each row has a `Remove` ghost button that calls `deleteBlocklistEntry(id)` then re-fetches.

ESC closes drawer. Click outside closes drawer.

---

## 12) TopNav badge

Add a third nav item between Dashboard and Chat:

```
{ href: "/inbox", label: "Inbox", icon: <inbox icon> }
```

Behavior:
- On every page mount and after every inbox action, fetch `getInboxSummary` (cached for 30 seconds in a tiny module-level cache to avoid hammering the API on every nav re-render).
- Render `<InboxBadge count={summary.total_pending} />` next to the label when count > 0. Saffron pill, mono digits.
- Badge becomes a subtle dot only (no number) when count > 99 to avoid layout shifts.

The cache lives in `frontend/src/lib/inbox-api.ts` as `let _summaryCache = { value, fetchedAt }`. Invalidate by calling `invalidateInboxSummary()` after any action, then re-fetch on next access.

---

## 13) Visual conformance (Luminous Codex)

- Cards: `rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] p-5` (matches dashboard widgets).
- Active list item: `border-l-2 border-[var(--color-brand-accent)] bg-[var(--color-brand-accent)]/5`.
- Action tab strip: ghost buttons with saffron underline on active, matching chat ModeSelector style.
- Submit buttons: primary saffron fill `bg-[var(--color-brand-accent)] text-[var(--color-brand-bg)]`.
- Destructive buttons (Dismiss/Reject/Blocklist confirm): rose `bg-[var(--color-brand-accent-rose)] text-white`.
- Mono for dates, scores, ids: `font-mono text-[10px] text-[var(--color-brand-muted)]`.
- Headings: Instrument Serif via existing `font-heading` class.

---

## 14) State and refetch model

Local component state, no global store. Hierarchy:

```
InboxLayout (page-level state)
├── filters (URL-driven)
├── selectedId
├── proposals: ProposalSummary[] + total
├── detail: ProposalDetail | null
├── summary: InboxSummary
└── blocklistOpen: boolean
```

Effects:

- On filter change → refetch `listProposals`.
- On `selectedId` change → refetch `getProposal(selectedId)`.
- On any action success → invalidate summary cache, refetch summary + list, advance selection.

All fetches use `AbortController` for cleanup, mirroring the pattern in `app/page.tsx`.

---

## 15) Error handling

- `404` on detail fetch → list re-fetch (proposal probably resolved by another tab) + toast: *"Proposal no longer pending — refreshing."*
- `409 already_resolved` → toast with `current_status`; refresh detail.
- `409 existing_id` (confirm-new) → inline alert with merge affordance (§9.1).
- Network/timeout errors → toast with retry button.
- Pre-action validation (empty canonical_name, no candidate selected for merge) → button disabled + helper text. Never invoke the API for known invalid states.

---

## 16) Accessibility

- Semantic landmarks: `<main>` for inbox, `<aside>` for blocklist drawer.
- Tab order: filters → list → detail → action panel.
- ARIA: list pane uses `role="listbox"`; items `role="option"` with `aria-selected`; status pills include screen-reader-only labels.
- Buttons have explicit `type="button"` (no implicit form submits except in forms).
- Color is never the only signal — sentiment/status chips include text labels.
- ConfirmDialog already handles focus trap & ESC.

---

## 17) Testing plan

### 17.1 Manual smoke (with the synthetic journals seeded)

1. Run shredder + resolution; some proposals will land.
2. Open `/inbox`. Verify TopNav badge matches `summary.total_pending`.
3. Confirm a person as new → mentions count surfaces in toast; cascade list shown if duplicates.
4. Merge a person via candidate selection → alias persisted (verify by refreshing list and checking the existing person's resolved related rows).
5. Reject a project via blocklist mode → re-shred the same date and verify Step 3 no longer creates a proposal for that surface.
6. Open Blocklist drawer, remove the entry, verify a future shred re-creates the proposal.
7. Verify URL ?status=resolved&type=project filter renders only resolved project rows.

### 17.2 Visual regression (manual)

Screenshot baselines under three states:
- Inbox empty (no pending).
- Pending with mixed types and candidates.
- Resolved view (audit history of past decisions).

### 17.3 Component tests (deferred)

The repo currently has no frontend test harness. Document this limitation in Step 13 (release/hardening) and add Playwright/Vitest later. **No new test infra is added in Step 5.**

---

## 18) Definition of done

Step 5 is complete when:

- `/inbox` loads, lists pending proposals, filters work, and detail view renders payload + candidates.
- All seven Step 4 actions are reachable from the UI and complete the round-trip (action → toast → refetched list).
- TopNav shows pending count badge and updates after actions.
- Blocklist drawer lists and removes entries.
- 409 / 404 / network errors surface user-friendly toasts without crashing the page.
- Visual styling conforms to Luminous Codex tokens; matches the dashboard / chat aesthetic.
- No console errors on mount or during the standard action flows.

---

## Changelog

- 2026-04-22 — Initial complete Step 5 spec. Defines route, file layout, API client extensions, two-pane layout with filters and detail/action panels, blocklist drawer, TopNav badge with cached summary, error/feedback patterns, accessibility checklist, and manual testing plan.
