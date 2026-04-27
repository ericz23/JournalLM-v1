"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError } from "@/lib/api";
import {
  blocklistProposal,
  confirmNewPerson,
  confirmNewProject,
  dismissProposal,
  getCachedInboxSummary,
  getInboxSummary,
  getProposal,
  invalidateInboxSummary,
  listProposals,
  mergePerson,
  mergeProject,
  rejectProject,
  type ActionResult,
  type EntityType,
  type InboxSummary,
  type ProposalDetail as ProposalDetailType,
  type ProposalStatus,
  type ProposalSummary,
  type BlocklistBody,
  type ConfirmNewPersonBody,
  type ConfirmNewProjectBody,
  type DismissBody,
  type MergePersonBody,
  type MergeProjectBody,
  type RejectProjectBody,
} from "@/lib/inbox-api";
import ProposalList from "./ProposalList";
import ProposalDetail from "./ProposalDetail";
import ActionPanelPerson from "./ActionPanelPerson";
import ActionPanelProject from "./ActionPanelProject";
import BlocklistDrawer from "./BlocklistDrawer";
import InboxToast, { type ToastInput } from "./InboxToast";

const PAGE_SIZE = 50;
const RESOLVED_STATUSES: ProposalStatus[] = [
  "accepted_new",
  "merged_existing",
  "dismissed",
  "rejected",
  "blocked",
];

type StatusFilter = "pending" | "resolved" | "all";
type TypeFilter = "all" | "person" | "project";

function statusFilterToParams(status: StatusFilter): ProposalStatus[] | undefined {
  if (status === "pending") return ["pending"];
  if (status === "resolved") return RESOLVED_STATUSES;
  return undefined;
}

function parseStatus(raw: string | null): StatusFilter {
  if (raw === "resolved" || raw === "all") return raw;
  return "pending";
}

function parseType(raw: string | null): TypeFilter {
  if (raw === "person" || raw === "project") return raw;
  return "all";
}

function summarizeAction(result: ActionResult): ToastInput {
  const p = result.proposal;
  const surface = p.surface_name;
  const cascade = result.cascaded_proposal_ids.length;
  const cascadeStr = cascade > 0 ? ` ${cascade} cascaded proposal${cascade === 1 ? "" : "s"} resolved.` : "";
  const truncated = result.cascade_truncated
    ? " (cascade truncated — re-run inbox to clean up the rest)"
    : "";

  let title: string;
  let description: string;

  switch (p.status) {
    case "accepted_new":
      title = `Confirmed "${surface}" as new ${p.entity_type}`;
      description =
        p.entity_type === "person"
          ? `${result.mentions_created} mention${result.mentions_created === 1 ? "" : "s"} linked.${cascadeStr}${truncated}`
          : `${result.events_created} event${result.events_created === 1 ? "" : "s"} created. ${result.status_transitions} status transition${result.status_transitions === 1 ? "" : "s"}.${cascadeStr}${truncated}`;
      break;
    case "merged_existing":
      title = `Merged "${surface}" into existing ${p.entity_type}`;
      description =
        p.entity_type === "person"
          ? `${result.mentions_created} mention${result.mentions_created === 1 ? "" : "s"} linked.${cascadeStr}${truncated}`
          : `${result.events_created} event${result.events_created === 1 ? "" : "s"} created. ${result.status_transitions} status transition${result.status_transitions === 1 ? "" : "s"}.${cascadeStr}${truncated}`;
      break;
    case "dismissed":
      title = `Dismissed "${surface}"`;
      description = "Surface may resurface in future shred runs.";
      break;
    case "rejected":
      title = `Rejected "${surface}"`;
      description = `${cascade} cascaded proposal${cascade === 1 ? "" : "s"} silenced.${truncated}`;
      break;
    case "blocked":
      title = `Blocklisted "${surface}"`;
      description = `${cascade} cascaded proposal${cascade === 1 ? "" : "s"} silenced.${truncated}`;
      break;
    default:
      title = `Updated "${surface}"`;
      description = "";
  }

  return {
    variant: "success",
    title,
    description: description.trim() || undefined,
    warnings: result.warnings.length > 0 ? result.warnings : undefined,
  };
}

export default function InboxLayout() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const status: StatusFilter = parseStatus(searchParams.get("status"));
  const typeFilter: TypeFilter = parseType(searchParams.get("type"));
  const search = searchParams.get("search") ?? "";
  const dateFrom = searchParams.get("from") ?? "";
  const dateTo = searchParams.get("to") ?? "";
  const selectedIdParam = searchParams.get("selected");
  const selectedId = selectedIdParam ? Number(selectedIdParam) : null;

  const [items, setItems] = useState<ProposalSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [listLoading, setListLoading] = useState(false);
  const [detail, setDetail] = useState<ProposalDetailType | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [summary, setSummary] = useState<InboxSummary | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmExistingError, setConfirmExistingError] = useState<string | null>(null);
  const [selectedTargetId, setSelectedTargetId] = useState<number | null>(null);
  const [blocklistOpen, setBlocklistOpen] = useState(false);
  const [toasts, setToasts] = useState<Array<{ id: number; toast: ToastInput }>>([]);
  const [searchDraft, setSearchDraft] = useState(search);
  const toastIdRef = useRef(0);

  function pushToast(toast: ToastInput) {
    const id = ++toastIdRef.current;
    setToasts((ts) => [...ts, { id, toast }]);
  }

  function dismissToast(id: number) {
    setToasts((ts) => ts.filter((t) => t.id !== id));
  }

  // Sync searchDraft with URL search param when navigating externally.
  useEffect(() => {
    setSearchDraft(search);
  }, [search]);

  // Build filter params object (memoized).
  const filterParams = useMemo(
    () => ({
      status,
      type: typeFilter,
      search,
      dateFrom,
      dateTo,
    }),
    [status, typeFilter, search, dateFrom, dateTo]
  );

  // Update URL helper (preserves selection unless cleared).
  const updateParams = useCallback(
    (next: Partial<{
      status: StatusFilter;
      type: TypeFilter;
      search: string;
      from: string;
      to: string;
      selected: number | null;
    }>) => {
      const sp = new URLSearchParams(searchParams.toString());
      if (next.status !== undefined) {
        if (next.status === "pending") sp.delete("status");
        else sp.set("status", next.status);
      }
      if (next.type !== undefined) {
        if (next.type === "all") sp.delete("type");
        else sp.set("type", next.type);
      }
      if (next.search !== undefined) {
        if (next.search) sp.set("search", next.search);
        else sp.delete("search");
      }
      if (next.from !== undefined) {
        if (next.from) sp.set("from", next.from);
        else sp.delete("from");
      }
      if (next.to !== undefined) {
        if (next.to) sp.set("to", next.to);
        else sp.delete("to");
      }
      if (next.selected !== undefined) {
        if (next.selected === null) sp.delete("selected");
        else sp.set("selected", String(next.selected));
      }
      router.replace(`/inbox?${sp.toString()}`);
    },
    [router, searchParams]
  );

  // Fetch summary on mount and after action invalidations.
  const refetchSummary = useCallback(async (signal?: AbortSignal) => {
    try {
      const s = await getInboxSummary(signal);
      setSummary(s);
    } catch {
      // soft fail; badge just won't update
    }
  }, []);

  useEffect(() => {
    const ctl = new AbortController();
    getCachedInboxSummary(ctl.signal)
      .then(setSummary)
      .catch(() => undefined);
    return () => ctl.abort();
  }, []);

  // Fetch list when filters change.
  useEffect(() => {
    const ctl = new AbortController();
    setListLoading(true);
    listProposals(
      {
        status: statusFilterToParams(filterParams.status),
        entity_type: filterParams.type === "all" ? undefined : (filterParams.type as EntityType),
        entry_date_from: filterParams.dateFrom || undefined,
        entry_date_to: filterParams.dateTo || undefined,
        search: filterParams.search || undefined,
        limit: PAGE_SIZE,
        offset: 0,
      },
      ctl.signal
    )
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
        setListLoading(false);
      })
      .catch((e: unknown) => {
        if ((e as { name?: string }).name === "AbortError") return;
        setListLoading(false);
        pushToast({
          variant: "error",
          title: "Could not load proposals",
          description: (e as Error).message,
        });
      });
    return () => ctl.abort();
  }, [filterParams]);

  // Fetch detail when selectedId changes.
  useEffect(() => {
    if (selectedId === null) {
      setDetail(null);
      setSelectedTargetId(null);
      setConfirmExistingError(null);
      return;
    }
    const ctl = new AbortController();
    setDetailLoading(true);
    setConfirmExistingError(null);
    getProposal(selectedId, ctl.signal)
      .then((d) => {
        setDetail(d);
        setSelectedTargetId(d.candidate_matches[0]?.entity_id ?? null);
        setDetailLoading(false);
      })
      .catch((e: unknown) => {
        if ((e as { name?: string }).name === "AbortError") return;
        if (e instanceof ApiError && e.status === 404) {
          pushToast({
            variant: "info",
            title: "Proposal no longer pending — refreshing.",
          });
          updateParams({ selected: null });
        } else {
          pushToast({
            variant: "error",
            title: "Could not load proposal",
            description: (e as Error).message,
          });
        }
        setDetailLoading(false);
      });
    return () => ctl.abort();
  }, [selectedId, updateParams]);

  // Auto-select first when none selected and items present (only for pending).
  useEffect(() => {
    if (selectedId === null && items.length > 0 && status === "pending") {
      updateParams({ selected: items[0].id });
    }
  }, [items, selectedId, status, updateParams]);

  // Pagination.
  const loadMore = useCallback(async () => {
    setListLoading(true);
    try {
      const res = await listProposals({
        status: statusFilterToParams(filterParams.status),
        entity_type: filterParams.type === "all" ? undefined : (filterParams.type as EntityType),
        entry_date_from: filterParams.dateFrom || undefined,
        entry_date_to: filterParams.dateTo || undefined,
        search: filterParams.search || undefined,
        limit: PAGE_SIZE,
        offset: items.length,
      });
      setItems((prev) => [...prev, ...res.items]);
      setTotal(res.total);
    } catch (e) {
      pushToast({
        variant: "error",
        title: "Could not load more proposals",
        description: (e as Error).message,
      });
    } finally {
      setListLoading(false);
    }
  }, [filterParams, items.length]);

  // Re-fetch list with current filters; used after actions.
  const refetchList = useCallback(async () => {
    setListLoading(true);
    try {
      const res = await listProposals({
        status: statusFilterToParams(filterParams.status),
        entity_type: filterParams.type === "all" ? undefined : (filterParams.type as EntityType),
        entry_date_from: filterParams.dateFrom || undefined,
        entry_date_to: filterParams.dateTo || undefined,
        search: filterParams.search || undefined,
        limit: PAGE_SIZE,
        offset: 0,
      });
      setItems(res.items);
      setTotal(res.total);
      return res.items;
    } finally {
      setListLoading(false);
    }
  }, [filterParams]);

  // Pending duplicates count for current surface (used by blocklist confirm copy).
  const pendingDuplicateCount = useMemo(() => {
    if (!detail) return 0;
    const surface = detail.surface_name.toLowerCase();
    return items.filter(
      (i) =>
        i.id !== detail.id &&
        i.status === "pending" &&
        i.entity_type === detail.entity_type &&
        i.surface_name.toLowerCase() === surface
    ).length;
  }, [items, detail]);

  // Wraps an action call with submitting flag, error normalization, and post-action refresh.
  async function runAction(
    label: string,
    fn: () => Promise<ActionResult>,
    options?: { onConfirmExisting?: (msg: string) => void }
  ) {
    setSubmitting(true);
    setConfirmExistingError(null);
    try {
      const result = await fn();
      pushToast(summarizeAction(result));
      invalidateInboxSummary();
      const newItems = await refetchList();
      await refetchSummary();
      // Advance selection: pick next pending in the same list, or null.
      const remainingPending = newItems.filter(
        (i) => i.status === "pending" && i.id !== result.proposal.id
      );
      const next = remainingPending[0]?.id ?? null;
      updateParams({ selected: next });
    } catch (e) {
      if (e instanceof ApiError) {
        const body = e.body as Record<string, unknown> | undefined;
        if (e.status === 409 && body && "existing_id" in body) {
          const msg = `${label} failed: ${typeof body.detail === "string" ? body.detail : "Already exists."}`;
          setConfirmExistingError(msg);
          options?.onConfirmExisting?.(msg);
        } else if (e.status === 409) {
          pushToast({
            variant: "info",
            title: `${label} already resolved`,
            description:
              typeof body?.detail === "string" ? body.detail : "Another action resolved this proposal.",
          });
          // Refresh detail to reflect new status.
          if (selectedId !== null) {
            try {
              const d = await getProposal(selectedId);
              setDetail(d);
            } catch {
              updateParams({ selected: null });
            }
          }
        } else if (e.status === 404) {
          pushToast({ variant: "info", title: "Proposal no longer pending — refreshing." });
          await refetchList();
          updateParams({ selected: null });
        } else {
          pushToast({ variant: "error", title: `${label} failed`, description: e.message });
        }
      } else {
        pushToast({
          variant: "error",
          title: `${label} failed`,
          description: (e as Error).message ?? "Unknown error",
        });
      }
    } finally {
      setSubmitting(false);
    }
  }

  // ── Person actions ──────────────────────────────────────────────
  function handleConfirmNewPerson(body: ConfirmNewPersonBody) {
    if (!detail) return;
    runAction("Confirm new person", () => confirmNewPerson(detail.id, body));
  }

  function handleMergePerson(body: MergePersonBody) {
    if (!detail) return;
    runAction("Merge person", () => mergePerson(detail.id, body));
  }

  // ── Project actions ─────────────────────────────────────────────
  function handleConfirmNewProject(body: ConfirmNewProjectBody) {
    if (!detail) return;
    runAction("Confirm new project", () => confirmNewProject(detail.id, body));
  }

  function handleMergeProject(body: MergeProjectBody) {
    if (!detail) return;
    runAction("Merge project", () => mergeProject(detail.id, body));
  }

  function handleRejectProject(body: RejectProjectBody) {
    if (!detail) return;
    runAction("Reject project", () => rejectProject(detail.id, body));
  }

  // ── Shared actions ──────────────────────────────────────────────
  function handleDismiss(body: DismissBody) {
    if (!detail) return;
    runAction("Dismiss proposal", () => dismissProposal(detail.id, body));
  }

  function handleBlocklist(body: BlocklistBody) {
    if (!detail) return;
    runAction("Blocklist proposal", () => blocklistProposal(detail.id, body));
  }

  // ── Render ──────────────────────────────────────────────────────
  const headerSubline = useMemo(() => {
    if (!summary) return null;
    if (summary.total_pending === 0) return "0 pending";
    const oldest = summary.oldest_pending_entry_date
      ? ` · oldest ${summary.oldest_pending_entry_date}`
      : "";
    return `${summary.total_pending} pending${oldest}`;
  }, [summary]);

  const blocklistCount = summary ? summary.total_pending : 0;

  function actionPanel() {
    if (!detail) return null;
    if (detail.entity_type === "person") {
      return (
        <ActionPanelPerson
          key={detail.id}
          proposal={detail}
          selectedTargetId={selectedTargetId}
          onSelectTarget={setSelectedTargetId}
          submitting={submitting}
          confirmExistingError={confirmExistingError}
          pendingDuplicateCount={pendingDuplicateCount}
          onConfirmNew={handleConfirmNewPerson}
          onMerge={handleMergePerson}
          onDismiss={handleDismiss}
          onBlocklist={handleBlocklist}
          onSwitchToMerge={() => setConfirmExistingError(null)}
        />
      );
    }
    return (
      <ActionPanelProject
        key={detail.id}
        proposal={detail}
        selectedTargetId={selectedTargetId}
        onSelectTarget={setSelectedTargetId}
        submitting={submitting}
        confirmExistingError={confirmExistingError}
        pendingDuplicateCount={pendingDuplicateCount}
        onConfirmNew={handleConfirmNewProject}
        onMerge={handleMergeProject}
        onReject={handleRejectProject}
        onDismiss={handleDismiss}
        onBlocklist={handleBlocklist}
        onSwitchToMerge={() => setConfirmExistingError(null)}
      />
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-6 py-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-heading text-2xl tracking-tight text-[var(--color-brand-text)]">
            Entity Inbox
          </h1>
          <p className="mt-1 font-mono text-[11px] text-[var(--color-brand-muted)]">
            {headerSubline ?? "Loading…"}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setBlocklistOpen(true)}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-[var(--color-brand-border)] px-3 py-1.5 text-[11px] font-medium text-[var(--color-brand-text-dim)] hover:bg-[var(--color-brand-bg)] hover:text-[var(--color-brand-text)]"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
          </svg>
          Blocklist
        </button>
      </header>

      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] p-2">
        <div className="flex items-center gap-1">
          {(["pending", "resolved", "all"] as StatusFilter[]).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => updateParams({ status: s, selected: null })}
              className={`rounded-md px-2.5 py-1 text-[11px] font-medium capitalize transition-colors ${
                status === s
                  ? "bg-[var(--color-brand-accent)]/15 text-[var(--color-brand-text)]"
                  : "text-[var(--color-brand-text-dim)] hover:text-[var(--color-brand-text)]"
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        <span className="h-4 w-px bg-[var(--color-brand-border)]" />

        <div className="flex items-center gap-1">
          {(["all", "person", "project"] as TypeFilter[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => updateParams({ type: t, selected: null })}
              className={`rounded-md px-2.5 py-1 text-[11px] font-medium capitalize transition-colors ${
                typeFilter === t
                  ? "bg-[var(--color-brand-accent)]/15 text-[var(--color-brand-text)]"
                  : "text-[var(--color-brand-text-dim)] hover:text-[var(--color-brand-text)]"
              }`}
            >
              {t === "all" ? "All types" : `${t}s`}
            </button>
          ))}
        </div>

        <span className="h-4 w-px bg-[var(--color-brand-border)]" />

        <form
          onSubmit={(e) => {
            e.preventDefault();
            updateParams({ search: searchDraft.trim(), selected: null });
          }}
          className="flex flex-1 items-center"
        >
          <input
            type="search"
            value={searchDraft}
            onChange={(e) => setSearchDraft(e.target.value)}
            placeholder="Search surface name…"
            className="w-full rounded-md border border-transparent bg-[var(--color-brand-bg)] px-2.5 py-1 text-[11px] text-[var(--color-brand-text)] outline-none focus:border-[var(--color-brand-accent)]"
          />
        </form>

        <div className="flex items-center gap-1">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => updateParams({ from: e.target.value, selected: null })}
            className="rounded-md border border-transparent bg-[var(--color-brand-bg)] px-2 py-1 font-mono text-[10px] text-[var(--color-brand-text)] outline-none focus:border-[var(--color-brand-accent)]"
            aria-label="Date from"
          />
          <span className="font-mono text-[10px] text-[var(--color-brand-muted)]">→</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => updateParams({ to: e.target.value, selected: null })}
            className="rounded-md border border-transparent bg-[var(--color-brand-bg)] px-2 py-1 font-mono text-[10px] text-[var(--color-brand-text)] outline-none focus:border-[var(--color-brand-accent)]"
            aria-label="Date to"
          />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <div className="h-[calc(100vh-260px)] min-h-[480px]">
          <ProposalList
            items={items}
            total={total}
            selectedId={selectedId}
            onSelect={(id) => updateParams({ selected: id })}
            onLoadMore={items.length < total ? loadMore : null}
            loading={listLoading}
          />
        </div>
        <div>
          <ProposalDetail
            loading={detailLoading}
            proposal={detail}
            selectedTargetId={selectedTargetId}
            onSelectTarget={setSelectedTargetId}
            actionPanel={actionPanel()}
          />
        </div>
      </div>

      <BlocklistDrawer
        open={blocklistOpen}
        onClose={() => setBlocklistOpen(false)}
        onChanged={() => {
          invalidateInboxSummary();
          refetchSummary();
        }}
      />

      {/* Toast container */}
      <div className="pointer-events-none fixed right-4 top-4 z-[200] flex flex-col gap-2">
        {toasts.map(({ id, toast }) => (
          <InboxToast key={id} {...toast} onClose={() => dismissToast(id)} />
        ))}
      </div>

      {/* Blocklist count hint (consumed by BlocklistDrawer instead) */}
      <span className="hidden">{blocklistCount}</span>
    </div>
  );
}
