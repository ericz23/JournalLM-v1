"use client";

import Link from "next/link";
import type { ReflectionRow } from "@/lib/api";

type Props = {
  items: ReflectionRow[];
  loading: boolean;
};

const TOPIC_COLORS: Record<string, string> = {
  "Design Philosophy": "var(--color-brand-accent)",
  "Design Inspiration": "var(--color-brand-accent)",
  "Human Behavior & Design": "var(--color-brand-accent)",
  "Public Green Space Design": "var(--color-brand-accent-green)",
  "Professional Confidence": "var(--color-brand-accent-amber)",
  "Fitness Recovery": "var(--color-brand-accent-rose)",
  "Cooking Improvement": "var(--color-brand-accent-amber)",
  "Language Learning": "var(--chart-5)",
  "Language Learning Progress": "var(--chart-5)",
};

function getTopicColor(topic: string, isRecurring: boolean): string {
  if (isRecurring) return "var(--chart-5)";
  return TOPIC_COLORS[topic] ?? "var(--color-brand-accent)";
}

function formatDate(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export default function ReflectionsPanel({ items, loading }: Props) {
  const actionableCount = items.filter((r) => r.is_actionable).length;
  const recurringCount = items.filter((r) => r.is_recurring).length;

  return (
    <div className="rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--chart-5)]/15">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--chart-5)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4" />
              <path d="M12 8h.01" />
            </svg>
          </div>
          <h2 className="font-heading text-sm text-[var(--color-brand-text)]">
            Reflections &amp; Insights
          </h2>
        </div>
        {!loading && items.length > 0 && (
          <div className="flex items-center gap-2">
            {actionableCount > 0 && (
              <span className="rounded-full bg-[var(--color-brand-accent-amber)]/10 px-2.5 py-0.5 text-[10px] font-mono font-semibold text-[var(--color-brand-accent-amber)]">
                {actionableCount} action
              </span>
            )}
            {recurringCount > 0 && (
              <span className="rounded-full bg-[var(--chart-5)]/10 px-2.5 py-0.5 text-[10px] font-mono font-semibold text-[var(--chart-5)]">
                {recurringCount} recurring
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
            <div key={i} className="h-16 animate-pulse rounded-lg bg-[var(--color-brand-border)]/50" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="py-8 text-center text-xs text-[var(--color-brand-text-dim)]">
          No reflections this week.
        </p>
      ) : (
        <ul className="max-h-[450px] space-y-2 overflow-y-auto pr-1">
          {items.map((r, i) => {
            const color = getTopicColor(r.topic, r.is_recurring);
            return (
              <li
                key={i}
                className="relative rounded-lg bg-[var(--color-brand-bg)] px-3.5 py-2.5 transition-colors hover:bg-[var(--color-brand-bg)]/80"
              >
                <div
                  className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full"
                  style={{ backgroundColor: color }}
                />
                {/* Topic row */}
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold" style={{ color }}>
                    {r.topic}
                  </span>
                  {r.is_actionable && (
                    <span className="flex items-center gap-1 rounded-full bg-[var(--color-brand-accent-amber)]/15 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-[var(--color-brand-accent-amber)]">
                      <svg
                        width="8"
                        height="8"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="3"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <polyline points="9 11 12 14 22 4" />
                        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                      </svg>
                      actionable
                    </span>
                  )}
                  {r.is_recurring && (
                    <span className="rounded-full bg-[var(--chart-5)]/10 px-2 py-0.5 text-[9px] font-mono uppercase text-[var(--chart-5)]">
                      recurring
                      <span className="sr-only"> topic</span>
                    </span>
                  )}
                  <span className="ml-auto text-[10px] font-mono text-[var(--color-brand-muted)]">
                    {formatDate(r.date)}
                  </span>
                </div>
                {/* Content */}
                <p className="text-[11px] leading-relaxed text-[var(--color-brand-text-dim)]">
                  {r.content}
                </p>
                {/* Follow-up block */}
                {r.follow_up && (
                  <div
                    className="mt-2 pl-3 text-[10px] text-[var(--color-brand-text-dim)]"
                    style={{ borderLeft: "1px solid color-mix(in srgb, var(--color-brand-accent) 40%, transparent)" }}
                  >
                    <p className="font-mono">
                      ↳ followed up by ·{" "}
                      {r.follow_up.matched_kind === "life_event" ? "life event" : "project update"}
                    </p>
                    {r.follow_up.matched_kind === "project_event" && r.follow_up.project_id ? (
                      <Link
                        href={`/projects/${r.follow_up.project_id}`}
                        className="italic underline underline-offset-2 hover:text-[var(--color-brand-text)] transition-colors"
                      >
                        {r.follow_up.sample_description}
                      </Link>
                    ) : (
                      <span className="italic">{r.follow_up.sample_description}</span>
                    )}
                    <span className="ml-2 font-mono text-[var(--color-brand-muted)]">
                      {formatDate(r.follow_up.sample_date)}
                    </span>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
