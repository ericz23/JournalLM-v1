"use client";

type Props = {
  content: string | null;
  weekStart: string | null;
  weekEnd: string | null;
  loading: boolean;
};

function formatDateRange(start: string | null, end: string | null): string {
  if (!start || !end) return "";
  const s = new Date(start + "T00:00:00");
  const e = new Date(end + "T00:00:00");
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  return `${s.toLocaleDateString("en-US", opts)} — ${e.toLocaleDateString("en-US", { ...opts, year: "numeric" })}`;
}

export default function NarrativeSnapshot({ content, weekStart, weekEnd, loading }: Props) {
  return (
    <div className="col-span-full relative overflow-hidden rounded-xl border border-[var(--color-slate-accent)]/20 bg-gradient-to-br from-[var(--color-slate-accent)]/[0.08] via-[var(--color-slate-surface)] to-[var(--color-slate-surface)] p-6">
      {/* Decorative corner glow */}
      <div className="pointer-events-none absolute -top-20 -right-20 h-40 w-40 rounded-full bg-[var(--color-slate-accent)]/[0.06] blur-3xl" />
      <div className="pointer-events-none absolute -bottom-16 -left-16 h-32 w-32 rounded-full bg-[var(--color-slate-accent)]/[0.04] blur-2xl" />

      <div className="relative mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-slate-accent)]/15">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-slate-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
          </div>
          <div>
            <h2 className="text-sm font-semibold text-[var(--color-slate-text)]">
              Weekly Narrative
            </h2>
            <span className="text-[10px] font-mono text-[var(--color-slate-accent)]/70">
              AI-Generated Summary
            </span>
          </div>
        </div>
        {weekStart && weekEnd && (
          <span className="rounded-full bg-[var(--color-slate-accent)]/10 px-3 py-1 text-[10px] font-mono text-[var(--color-slate-accent)]">
            {formatDateRange(weekStart, weekEnd)}
          </span>
        )}
      </div>

      {loading ? (
        <div className="relative space-y-2.5">
          <div className="h-4 w-4/5 animate-pulse rounded bg-[var(--color-slate-accent)]/10" />
          <div className="h-4 w-3/5 animate-pulse rounded bg-[var(--color-slate-accent)]/10" />
          <div className="h-4 w-2/5 animate-pulse rounded bg-[var(--color-slate-accent)]/10" />
        </div>
      ) : (
        <p className="relative text-[15px] leading-[1.7] text-[var(--color-slate-text)]">
          {content || "No narrative available for this week."}
        </p>
      )}
    </div>
  );
}
