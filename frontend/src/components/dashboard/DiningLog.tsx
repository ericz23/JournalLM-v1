"use client";

import type { DiningRow, Sentiment } from "@/lib/api";

type Props = {
  items: DiningRow[];
  loading: boolean;
};

const SENTIMENT_COLORS: Record<Sentiment, string> = {
  POSITIVE: "var(--color-brand-accent-green)",
  NEGATIVE: "var(--color-brand-accent-rose)",
  NEUTRAL: "var(--color-brand-muted)",
};

function sentimentColor(s: Sentiment | null): string {
  return s ? SENTIMENT_COLORS[s] : "var(--color-brand-muted)";
}

function sentimentLabel(s: Sentiment | null): string {
  return s ? s.toLowerCase() : "neutral";
}

function mealIcon(type: string) {
  switch (type) {
    case "dinner":
      return "🍽️";
    case "lunch":
      return "☕";
    case "snack":
      return "🍵";
    default:
      return "🍴";
  }
}

function formatDate(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export default function DiningLog({ items, loading }: Props) {
  const repeatCount = items.filter((d) => d.is_repeat).length;

  const counterText =
    items.length > 0
      ? repeatCount > 0
        ? `${items.length} meals · ${repeatCount} repeat`
        : `${items.length} meals`
      : "";

  return (
    <div className="rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-brand-accent-amber)]/15">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--color-brand-accent-amber)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M18 8h1a4 4 0 0 1 0 8h-1" />
              <path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z" />
              <line x1="6" y1="1" x2="6" y2="4" />
              <line x1="10" y1="1" x2="10" y2="4" />
              <line x1="14" y1="1" x2="14" y2="4" />
            </svg>
          </div>
          <h2 className="font-heading text-sm text-[var(--color-brand-text)]">Dining Log</h2>
        </div>
        {!loading && counterText && (
          <span className="rounded-full bg-[var(--color-brand-accent-amber)]/10 px-2.5 py-0.5 text-[10px] font-mono font-semibold text-[var(--color-brand-accent-amber)]">
            {counterText}
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-2.5">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-14 animate-pulse rounded-lg bg-[var(--color-brand-border)]/50" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="py-8 text-center text-xs text-[var(--color-brand-text-dim)]">
          No dining events this week.
        </p>
      ) : (
        <ul className="max-h-[450px] space-y-2 overflow-y-auto pr-1">
          {items.map((d, i) => {
            const color = sentimentColor(d.sentiment);
            return (
              <li
                key={i}
                className="group relative flex items-start gap-3 rounded-lg bg-[var(--color-brand-bg)] px-3 py-2.5 transition-colors hover:bg-[var(--color-brand-bg)]/80"
              >
                <div
                  className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="mt-0.5 text-base leading-none">{mealIcon(d.meal_type)}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-[var(--color-brand-text)]">
                      {d.restaurant}
                    </span>
                    {/* Sentiment chip */}
                    <span
                      className="rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide"
                      style={{
                        backgroundColor: `color-mix(in srgb, ${color} 15%, transparent)`,
                        color: color,
                      }}
                    >
                      {sentimentLabel(d.sentiment)}
                      <span className="sr-only"> sentiment</span>
                    </span>
                    {/* Repeat-visit badge */}
                    {d.is_repeat && (
                      <span className="rounded-full bg-[var(--color-brand-accent)]/10 px-2 py-0.5 font-mono text-[9px] text-[var(--color-brand-accent)]">
                        {d.visit_count_total}× visit
                        {d.visit_count_window > 1 && (
                          <> · {d.visit_count_window} this week</>
                        )}
                      </span>
                    )}
                  </div>
                  {d.dishes.length > 0 && (
                    <p className="mt-0.5 truncate text-[11px] text-[var(--color-brand-text-dim)]">
                      {d.dishes.join(" · ")}
                    </p>
                  )}
                </div>
                <span className="ml-2 mt-0.5 shrink-0 text-[10px] font-mono text-[var(--color-brand-muted)]">
                  {formatDate(d.date)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
