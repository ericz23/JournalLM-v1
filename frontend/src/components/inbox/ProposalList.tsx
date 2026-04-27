"use client";

import { useEffect, useRef } from "react";
import type { ProposalSummary } from "@/lib/inbox-api";
import ProposalListItem from "./ProposalListItem";

type Props = {
  items: ProposalSummary[];
  total: number;
  selectedId: number | null;
  onSelect: (id: number) => void;
  onLoadMore: (() => void) | null;
  loading: boolean;
};

export default function ProposalList({
  items,
  total,
  selectedId,
  onSelect,
  onLoadMore,
  loading,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    function handleKey(e: KeyboardEvent) {
      if (items.length === 0) return;
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      if (!el || !el.contains(document.activeElement)) return;
      e.preventDefault();
      const currentIdx = items.findIndex((i) => i.id === selectedId);
      let nextIdx: number;
      if (currentIdx === -1) {
        nextIdx = 0;
      } else if (e.key === "ArrowDown") {
        nextIdx = Math.min(items.length - 1, currentIdx + 1);
      } else {
        nextIdx = Math.max(0, currentIdx - 1);
      }
      onSelect(items[nextIdx].id);
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [items, selectedId, onSelect]);

  return (
    <div
      ref={containerRef}
      role="listbox"
      tabIndex={0}
      className="flex h-full flex-col rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)]"
    >
      <div className="flex items-center justify-between border-b border-[var(--color-brand-border)] px-3 py-2.5">
        <h2 className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--color-brand-muted)]">
          Proposals
        </h2>
        <span className="font-mono text-[10px] text-[var(--color-brand-muted)]">
          {items.length} / {total}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto py-1">
        {loading && items.length === 0 ? (
          <p className="p-4 text-[11px] italic text-[var(--color-brand-muted)]">
            Loading proposals…
          </p>
        ) : items.length === 0 ? (
          <p className="p-4 text-[11px] italic text-[var(--color-brand-muted)]">
            No proposals match the current filters.
          </p>
        ) : (
          items.map((p) => (
            <ProposalListItem
              key={p.id}
              proposal={p}
              selected={p.id === selectedId}
              onSelect={() => onSelect(p.id)}
            />
          ))
        )}
      </div>

      {onLoadMore && items.length < total && (
        <div className="border-t border-[var(--color-brand-border)] p-2">
          <button
            type="button"
            onClick={onLoadMore}
            disabled={loading}
            className="w-full rounded-lg border border-[var(--color-brand-border)] px-3 py-2 text-[11px] font-medium text-[var(--color-brand-text-dim)] hover:bg-[var(--color-brand-bg)] hover:text-[var(--color-brand-text)] disabled:opacity-50"
          >
            {loading ? "Loading…" : "Load more"}
          </button>
        </div>
      )}
    </div>
  );
}
