"use client";

type LearningEntry = {
  date: string;
  subject: string;
  milestone: string;
  description: string;
  sentiment: number;
};

type Props = {
  items: LearningEntry[];
  loading: boolean;
};

const SUBJECT_COLORS: Record<string, string> = {
  Portuguese: "var(--color-brand-accent-green)",
  "Biophilic Urbanism": "var(--color-brand-accent)",
  "sustainable urban runoff management": "var(--color-brand-accent)",
  "construction vocabulary": "var(--color-brand-accent-amber)",
};

function getSubjectColor(subject: string): string {
  for (const [key, val] of Object.entries(SUBJECT_COLORS)) {
    if (subject.toLowerCase().includes(key.toLowerCase())) return val;
  }
  return "var(--chart-5)";
}

export default function LearningProgress({ items, loading }: Props) {
  const milestoneCount = items.filter((l) => l.milestone).length;

  return (
    <div className="rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-brand-accent-green)]/15">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-brand-accent-green)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
              <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
            </svg>
          </div>
          <h2 className="font-heading text-sm text-[var(--color-brand-text)]">
            Learning Progress
          </h2>
        </div>
        {!loading && items.length > 0 && (
          <div className="flex items-center gap-2">
            {milestoneCount > 0 && (
              <span className="rounded-full bg-[var(--color-brand-accent-green)]/10 px-2.5 py-0.5 text-[10px] font-mono font-semibold text-[var(--color-brand-accent-green)]">
                {milestoneCount} milestone{milestoneCount > 1 ? "s" : ""}
              </span>
            )}
            <span className="rounded-full bg-[var(--color-brand-accent-green)]/10 px-2.5 py-0.5 text-[10px] font-mono font-semibold text-[var(--color-brand-accent-green)]">
              {items.length} sessions
            </span>
          </div>
        )}
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-[var(--color-brand-border)]/50" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="py-8 text-center text-xs text-[var(--color-brand-text-dim)]">No learning events this week.</p>
      ) : (
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((l, i) => {
            const color = getSubjectColor(l.subject);
            return (
              <div
                key={i}
                className="relative overflow-hidden rounded-lg bg-[var(--color-brand-bg)] px-3.5 py-3 transition-colors hover:bg-[var(--color-brand-bg)]/80"
              >
                <div
                  className="absolute left-0 top-0 bottom-0 w-[3px]"
                  style={{ backgroundColor: color }}
                />
                <div className="flex items-center gap-2 mb-1.5">
                  {l.subject && (
                    <span
                      className="rounded px-1.5 py-0.5 text-[10px] font-mono font-semibold"
                      style={{
                        backgroundColor: `color-mix(in srgb, ${color} 15%, transparent)`,
                        color: color,
                      }}
                    >
                      {l.subject}
                    </span>
                  )}
                  {l.milestone && (
                    <span className="flex items-center gap-1 rounded-full bg-[var(--color-brand-accent-green)]/15 px-2 py-0.5 text-[9px] font-semibold text-[var(--color-brand-accent-green)]">
                      <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                        <polyline points="22 4 12 14.01 9 11.01" />
                      </svg>
                      {l.milestone}
                    </span>
                  )}
                </div>
                <p className="text-[11px] leading-relaxed text-[var(--color-brand-text-dim)]">
                  {l.description}
                </p>
                <span className="mt-1.5 block text-[10px] font-mono text-[var(--color-brand-muted)]">
                  {new Date(l.date + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
