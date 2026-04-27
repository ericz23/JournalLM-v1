"use client";

import { useEffect, useState } from "react";
import {
  deleteBlocklistEntry,
  listBlocklist,
  type BlocklistEntry,
  type EntityType,
} from "@/lib/inbox-api";

type Props = {
  open: boolean;
  onClose: () => void;
  onChanged: () => void;
};

type Tab = "all" | "person" | "project";

export default function BlocklistDrawer({ open, onClose, onChanged }: Props) {
  const [tab, setTab] = useState<Tab>("all");
  const [entries, setEntries] = useState<BlocklistEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const ctl = new AbortController();
    setLoading(true);
    setError(null);
    const filter: EntityType | undefined =
      tab === "all" ? undefined : (tab as EntityType);
    listBlocklist(filter, ctl.signal)
      .then((data) => {
        setEntries(data);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if ((e as { name?: string }).name === "AbortError") return;
        setError((e as Error).message ?? "Failed to load blocklist");
        setLoading(false);
      });
    return () => ctl.abort();
  }, [open, tab]);

  async function handleRemove(id: number) {
    setRemovingId(id);
    try {
      await deleteBlocklistEntry(id);
      setEntries((es) => es.filter((e) => e.id !== id));
      onChanged();
    } catch (e) {
      setError((e as Error).message ?? "Failed to remove entry");
    } finally {
      setRemovingId(null);
    }
  }

  if (!open) return null;

  return (
    <aside className="fixed inset-0 z-[90]">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="absolute right-0 top-0 flex h-full w-full max-w-[420px] flex-col border-l border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] shadow-2xl shadow-black/40">
        <div className="flex items-center justify-between border-b border-[var(--color-brand-border)] px-4 py-3">
          <h2 className="font-heading text-base text-[var(--color-brand-text)]">Blocklist</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-[var(--color-brand-muted)] hover:text-[var(--color-brand-text)]"
            aria-label="Close"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="flex items-center gap-1 border-b border-[var(--color-brand-border)] px-2 py-1.5">
          {(["all", "person", "project"] as Tab[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`rounded-md px-2.5 py-1 text-[11px] font-medium capitalize transition-colors ${
                tab === t
                  ? "bg-[var(--color-brand-accent)]/15 text-[var(--color-brand-text)]"
                  : "text-[var(--color-brand-text-dim)] hover:text-[var(--color-brand-text)]"
              }`}
            >
              {t === "all" ? "All" : `${t}s`}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          {error && (
            <p className="mb-2 rounded-lg border border-[var(--color-brand-accent-rose)]/40 bg-[var(--color-brand-accent-rose)]/10 px-3 py-2 text-[11px] text-[var(--color-brand-accent-rose)]">
              {error}
            </p>
          )}
          {loading ? (
            <p className="p-2 text-[11px] italic text-[var(--color-brand-muted)]">Loading…</p>
          ) : entries.length === 0 ? (
            <p className="p-2 text-[11px] italic text-[var(--color-brand-muted)]">
              No blocklist entries.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {entries.map((e) => {
                const typeColor =
                  e.entity_type === "person"
                    ? "var(--color-brand-accent)"
                    : "var(--chart-3)";
                return (
                  <li
                    key={e.id}
                    className="flex items-center gap-2 rounded-lg border border-[var(--color-brand-border)] px-3 py-2"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-[12px] font-semibold text-[var(--color-brand-text)]">
                          {e.surface_name}
                        </span>
                        <span
                          className="shrink-0 rounded-full border px-1.5 py-0.5 font-mono text-[9px] uppercase"
                          style={{ borderColor: typeColor, color: typeColor }}
                        >
                          {e.entity_type}
                        </span>
                      </div>
                      <div className="mt-0.5 flex items-center gap-2 font-mono text-[10px] text-[var(--color-brand-muted)]">
                        {e.reason && <span>{e.reason}</span>}
                        <span>{e.created_at.slice(0, 10)}</span>
                      </div>
                    </div>
                    <button
                      type="button"
                      disabled={removingId === e.id}
                      onClick={() => handleRemove(e.id)}
                      className="shrink-0 rounded-md border border-[var(--color-brand-border)] px-2 py-1 text-[11px] font-medium text-[var(--color-brand-text-dim)] hover:bg-[var(--color-brand-bg)] hover:text-[var(--color-brand-accent-rose)] disabled:opacity-50"
                    >
                      {removingId === e.id ? "…" : "Remove"}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </aside>
  );
}
