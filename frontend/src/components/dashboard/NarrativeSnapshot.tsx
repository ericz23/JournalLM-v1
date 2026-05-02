"use client";

import { useState } from "react";

type Props = {
  content: string | null;
  windowStart: string | null;
  windowEnd: string | null;
  cached?: boolean;
  loading: boolean;
};

function formatDateRange(start: string | null, end: string | null): string {
  if (!start || !end) return "";
  const s = new Date(start + "T00:00:00");
  const e = new Date(end + "T00:00:00");
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  return `${s.toLocaleDateString("en-US", opts)} — ${e.toLocaleDateString("en-US", { ...opts, year: "numeric" })}`;
}

export default function NarrativeSnapshot({
  content,
  windowStart,
  windowEnd,
  cached,
  loading,
}: Props) {
  const [regenToast, setRegenToast] = useState(false);

  function handleRegenerate() {
    setRegenToast(true);
    setTimeout(() => setRegenToast(false), 3000);
  }

  const subLabel = loading
    ? "Loading…"
    : cached === false
    ? "Comparative summary"
    : "Cached summary";

  return (
    <div className="col-span-full group relative overflow-hidden rounded-xl border border-[var(--color-brand-accent)]/20 bg-gradient-to-br from-[var(--color-brand-accent)]/[0.08] via-[var(--color-brand-surface)] to-[var(--color-brand-surface)] p-6">
      {/* Decorative corner glow */}
      <div className="pointer-events-none absolute -top-20 -right-20 h-40 w-40 rounded-full bg-[var(--color-brand-accent)]/[0.06] blur-3xl" />
      <div className="pointer-events-none absolute -bottom-16 -left-16 h-32 w-32 rounded-full bg-[var(--color-brand-accent)]/[0.04] blur-2xl" />

      {/* Header */}
      <div className="relative mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-brand-accent)]/15">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--color-brand-accent)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
          </div>
          <div>
            <h2 className="font-heading text-sm text-[var(--color-brand-text)]">
              Weekly Narrative
            </h2>
            <span className="text-[10px] font-mono text-[var(--color-brand-accent)]/70">
              {subLabel}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Regenerate ghost button — noop until backend endpoint ships */}
          {cached && !loading && (
            <button
              type="button"
              onClick={handleRegenerate}
              className="hidden group-hover:flex items-center gap-1 rounded border border-[var(--color-brand-border)] px-2 py-0.5 text-[10px] font-mono text-[var(--color-brand-text-dim)] hover:text-[var(--color-brand-text)] transition-colors"
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
              Regenerate
            </button>
          )}
          {windowStart && windowEnd && (
            <span className="rounded-full bg-[var(--color-brand-accent)]/10 px-3 py-1 text-[10px] font-mono text-[var(--color-brand-accent)]">
              {formatDateRange(windowStart, windowEnd)}
            </span>
          )}
        </div>
      </div>

      {/* Toast */}
      {regenToast && (
        <div className="relative mb-3 rounded-lg bg-[var(--color-brand-surface)] border border-[var(--color-brand-border)] px-3 py-2 text-[11px] text-[var(--color-brand-text-dim)]">
          Regenerate is coming in a later update.
        </div>
      )}

      {loading ? (
        <div className="relative space-y-2.5">
          <div className="h-4 w-4/5 animate-pulse rounded bg-[var(--color-brand-accent)]/10" />
          <div className="h-4 w-3/5 animate-pulse rounded bg-[var(--color-brand-accent)]/10" />
          <div className="h-4 w-2/5 animate-pulse rounded bg-[var(--color-brand-accent)]/10" />
        </div>
      ) : (
        <p className="relative font-heading text-[15px] leading-[1.8] text-[var(--color-brand-text)]">
          {content || "No journal data available for this week yet."}
        </p>
      )}
    </div>
  );
}
