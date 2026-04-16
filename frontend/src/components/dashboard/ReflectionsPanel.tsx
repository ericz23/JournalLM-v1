"use client";

type Reflection = {
  date: string;
  topic: string;
  content: string;
  is_actionable: boolean;
};

type Props = {
  items: Reflection[];
  loading: boolean;
};

const TOPIC_COLORS: Record<string, string> = {
  "Design Philosophy": "var(--color-slate-accent)",
  "Design Inspiration": "var(--color-slate-accent)",
  "Human Behavior & Design": "var(--color-slate-accent)",
  "Public Green Space Design": "var(--color-slate-accent-green)",
  "Professional Confidence": "var(--color-slate-accent-amber)",
  "Fitness Recovery": "var(--color-slate-accent-rose)",
  "Cooking Improvement": "var(--color-slate-accent-amber)",
  "Language Learning": "var(--chart-5)",
  "Language Learning Progress": "var(--chart-5)",
};

function getTopicColor(topic: string): string {
  return TOPIC_COLORS[topic] ?? "var(--color-slate-accent)";
}

export default function ReflectionsPanel({ items, loading }: Props) {
  const actionableCount = items.filter((r) => r.is_actionable).length;

  return (
    <div className="rounded-xl border border-[var(--color-slate-border)] bg-[var(--color-slate-surface)] p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--chart-5)]/15">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--chart-5)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4" />
              <path d="M12 8h.01" />
            </svg>
          </div>
          <h2 className="text-sm font-semibold text-[var(--color-slate-text)]">
            Reflections &amp; Insights
          </h2>
        </div>
        {!loading && items.length > 0 && (
          <div className="flex items-center gap-2">
            {actionableCount > 0 && (
              <span className="rounded-full bg-[var(--color-slate-accent-amber)]/10 px-2.5 py-0.5 text-[10px] font-mono font-semibold text-[var(--color-slate-accent-amber)]">
                {actionableCount} action
              </span>
            )}
            <span className="rounded-full bg-[var(--chart-5)]/10 px-2.5 py-0.5 text-[10px] font-mono font-semibold text-[var(--chart-5)]">
              {items.length} total
            </span>
          </div>
        )}
      </div>

      {loading ? (
        <div className="space-y-2.5">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg bg-[var(--color-slate-border)]/50" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="py-8 text-center text-xs text-[var(--color-slate-text-dim)]">No reflections this week.</p>
      ) : (
        <ul className="space-y-2 max-h-[450px] overflow-y-auto pr-1">
          {items.map((r, i) => {
            const color = getTopicColor(r.topic);
            return (
              <li
                key={i}
                className="relative rounded-lg bg-[var(--color-slate-bg)] px-3.5 py-2.5 transition-colors hover:bg-[var(--color-slate-bg)]/80"
              >
                <div
                  className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full"
                  style={{ backgroundColor: color }}
                />
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className="text-xs font-semibold"
                    style={{ color }}
                  >
                    {r.topic}
                  </span>
                  {r.is_actionable && (
                    <span className="flex items-center gap-1 rounded-full bg-[var(--color-slate-accent-amber)]/15 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-[var(--color-slate-accent-amber)]">
                      <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="9 11 12 14 22 4" />
                        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                      </svg>
                      actionable
                    </span>
                  )}
                  <span className="ml-auto text-[10px] font-mono text-[var(--color-slate-muted)]">
                    {new Date(r.date + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                  </span>
                </div>
                <p className="text-[11px] leading-relaxed text-[var(--color-slate-text-dim)]">
                  {r.content}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
