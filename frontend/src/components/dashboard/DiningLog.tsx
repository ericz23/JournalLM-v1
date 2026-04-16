"use client";

type DiningEntry = {
  date: string;
  restaurant: string;
  dishes: string[];
  meal_type: string;
  sentiment: number;
  description: string;
};

type Props = {
  items: DiningEntry[];
  loading: boolean;
};

function sentimentColor(score: number) {
  if (score >= 0.3) return "var(--color-slate-accent-green)";
  if (score <= -0.3) return "var(--color-slate-accent-rose)";
  return "var(--color-slate-muted)";
}

function sentimentLabel(score: number) {
  if (score >= 0.3) return "positive";
  if (score <= -0.3) return "negative";
  return "neutral";
}

function mealIcon(type: string) {
  switch (type) {
    case "dinner":
      return "\u{1F37D}\uFE0F";
    case "lunch":
      return "\u2615";
    case "snack":
      return "\u{1F375}";
    default:
      return "\u{1F374}";
  }
}

export default function DiningLog({ items, loading }: Props) {
  return (
    <div className="rounded-xl border border-[var(--color-slate-border)] bg-[var(--color-slate-surface)] p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-slate-accent-amber)]/15">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-slate-accent-amber)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 8h1a4 4 0 0 1 0 8h-1" />
              <path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z" />
              <line x1="6" y1="1" x2="6" y2="4" />
              <line x1="10" y1="1" x2="10" y2="4" />
              <line x1="14" y1="1" x2="14" y2="4" />
            </svg>
          </div>
          <h2 className="text-sm font-semibold text-[var(--color-slate-text)]">
            Dining Log
          </h2>
        </div>
        {!loading && items.length > 0 && (
          <span className="rounded-full bg-[var(--color-slate-accent-amber)]/10 px-2.5 py-0.5 text-[10px] font-mono font-semibold text-[var(--color-slate-accent-amber)]">
            {items.length} meals
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-2.5">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-14 animate-pulse rounded-lg bg-[var(--color-slate-border)]/50" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="py-8 text-center text-xs text-[var(--color-slate-text-dim)]">No dining events this week.</p>
      ) : (
        <ul className="space-y-2 max-h-[450px] overflow-y-auto pr-1">
          {items.map((d, i) => {
            const color = sentimentColor(d.sentiment);
            return (
              <li
                key={i}
                className="group relative flex items-start gap-3 rounded-lg bg-[var(--color-slate-bg)] px-3 py-2.5 transition-colors hover:bg-[var(--color-slate-bg)]/80"
              >
                <div
                  className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="mt-0.5 text-base leading-none">{mealIcon(d.meal_type)}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-[var(--color-slate-text)]">
                      {d.restaurant}
                    </span>
                    <span
                      className="rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide"
                      style={{
                        backgroundColor: `color-mix(in srgb, ${color} 15%, transparent)`,
                        color: color,
                      }}
                    >
                      {sentimentLabel(d.sentiment)}
                    </span>
                  </div>
                  {d.dishes.length > 0 && (
                    <p className="mt-0.5 text-[11px] text-[var(--color-slate-text-dim)] truncate">
                      {d.dishes.join(" \u00B7 ")}
                    </p>
                  )}
                </div>
                <span className="ml-2 mt-0.5 shrink-0 text-[10px] font-mono text-[var(--color-slate-muted)]">
                  {new Date(d.date + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
