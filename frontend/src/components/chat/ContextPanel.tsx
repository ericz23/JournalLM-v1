"use client";

import { cn } from "@/lib/utils";

export type ContextItem = {
  type: "life_event" | "reflection" | "health_metric" | "journal_chunk";
  date: string;
  content: string;
  metadata: Record<string, unknown>;
};

type Props = {
  items: ContextItem[];
  collapsed?: boolean;
  onToggle?: () => void;
};

const TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  life_event: { label: "EVENT", color: "var(--color-slate-accent)" },
  reflection: { label: "REFLECTION", color: "var(--color-slate-accent-amber)" },
  health_metric: { label: "HEALTH", color: "var(--color-slate-accent-green)" },
  journal_chunk: { label: "JOURNAL", color: "var(--color-slate-accent-rose)" },
};

function groupByDate(items: ContextItem[]): Map<string, ContextItem[]> {
  const map = new Map<string, ContextItem[]>();
  for (const item of items) {
    const group = map.get(item.date) ?? [];
    group.push(item);
    map.set(item.date, group);
  }
  return new Map([...map.entries()].sort(([a], [b]) => a.localeCompare(b)));
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

export default function ContextPanel({ items, collapsed, onToggle }: Props) {
  const grouped = groupByDate(items);

  return (
    <div
      className={cn(
        "flex flex-col border-l border-[var(--color-slate-border)] bg-[var(--color-slate-bg)] transition-all",
        collapsed ? "w-10" : "w-[360px]"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--color-slate-border)] px-3 py-3">
        {!collapsed && (
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-slate-text-dim)]">
            Retrieved Context
          </h2>
        )}
        <button
          onClick={onToggle}
          className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-slate-muted)] hover:text-[var(--color-slate-text)] transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            {collapsed ? (
              <polyline points="15 18 9 12 15 6" />
            ) : (
              <polyline points="9 18 15 12 9 6" />
            )}
          </svg>
        </button>
      </div>

      {/* Content */}
      {!collapsed && (
        <div className="flex-1 overflow-y-auto p-3 space-y-4">
          {items.length === 0 ? (
            <p className="text-xs text-[var(--color-slate-muted)] italic text-center mt-8">
              Context will appear here when you ask a question.
            </p>
          ) : (
            [...grouped.entries()].map(([date, dateItems]) => (
              <div key={date}>
                <div className="sticky top-0 bg-[var(--color-slate-bg)] py-1 mb-2">
                  <span className="text-[10px] font-mono font-semibold text-[var(--color-slate-accent)] uppercase tracking-wide">
                    {formatDate(date)}
                  </span>
                </div>
                <div className="space-y-2">
                  {dateItems.map((item, i) => {
                    const cfg = TYPE_CONFIG[item.type] ?? TYPE_CONFIG.life_event;
                    const category =
                      typeof item.metadata?.category === "string"
                        ? item.metadata.category
                        : null;

                    return (
                      <div
                        key={`${date}-${i}`}
                        className="rounded border border-[var(--color-slate-border)] bg-[var(--color-slate-surface)] p-2.5"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span
                            className="inline-block rounded px-1.5 py-0.5 text-[10px] font-mono font-bold"
                            style={{
                              backgroundColor: `color-mix(in srgb, ${cfg.color} 15%, transparent)`,
                              color: cfg.color,
                            }}
                          >
                            {category ?? cfg.label}
                          </span>
                          {typeof item.metadata?.sentiment === "number" && (
                            <span className="text-[10px] text-[var(--color-slate-muted)]">
                              sentiment: {(item.metadata.sentiment as number).toFixed(1)}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-[var(--color-slate-text)] leading-relaxed">
                          {item.content}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
