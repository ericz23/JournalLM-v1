"use client";

import Link from "next/link";
import type { ActiveProject } from "@/lib/api";
import InsightLine from "./widgets/InsightLine";
import StreakDots from "./widgets/StreakDots";
import EmptyState from "./widgets/EmptyState";

function deltaArrow(current: number, previous: number) {
  if (previous === 0) return null;
  const diff = current - previous;
  if (diff > 0)
    return (
      <span className="text-[9px] font-mono" style={{ color: "var(--color-brand-accent-green)" }}>
        ↑+{diff}
      </span>
    );
  if (diff < 0)
    return (
      <span className="text-[9px] font-mono" style={{ color: "var(--color-brand-accent-amber)" }}>
        ↓{diff}
      </span>
    );
  return <span className="text-[9px] font-mono text-[var(--color-brand-muted)]">=</span>;
}

function formatDate(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

type Props = {
  projects: ActiveProject[];
  total: number;
  insight: string | null;
  loading: boolean;
};

export default function ActiveProjectsWidget({ projects, total, insight, loading }: Props) {
  return (
    <section
      aria-labelledby="active-projects-heading"
      className="rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] p-5"
    >
      {/* Header */}
      <div className="mb-1 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div
            className="flex h-8 w-8 items-center justify-center rounded-lg"
            style={{ backgroundColor: "color-mix(in srgb, var(--chart-4) 15%, transparent)" }}
          >
            {/* kanban icon */}
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--chart-4)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="3" y="3" width="5" height="14" rx="1" />
              <rect x="10" y="3" width="5" height="9" rx="1" />
              <rect x="17" y="3" width="4" height="11" rx="1" />
            </svg>
          </div>
          <h2
            id="active-projects-heading"
            className="font-heading text-sm text-[var(--color-brand-text)]"
          >
            Active Projects
          </h2>
        </div>
        {!loading && total > 0 && (
          <span className="rounded-full bg-[var(--chart-4)]/10 px-2.5 py-0.5 text-[10px] font-mono font-semibold text-[var(--chart-4)]">
            {projects.length} of {total} active
          </span>
        )}
      </div>

      <InsightLine>{!loading ? insight : null}</InsightLine>

      {loading ? (
        <div className="space-y-2.5">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-14 animate-pulse rounded-lg bg-[var(--color-brand-border)]/50"
            />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <EmptyState
          icon={
            <svg
              width="28"
              height="28"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 5l7 7-7 7M5 12h14" />
            </svg>
          }
          title="No active projects"
          subtitle={
            <Link href="/inbox?type=project" className="underline underline-offset-2">
              Confirm a project from your inbox to start tracking.
            </Link>
          }
        />
      ) : (
        <ul className="space-y-2 max-h-[450px] overflow-y-auto pr-1">
          {projects.map((p) => {
            const ruleColor =
              p.status === "ACTIVE" ? "var(--chart-4)" : "var(--color-brand-muted)";
            return (
              <li key={p.project_id}>
                <Link
                  href={`/projects/${p.project_id}`}
                  aria-label={`${p.name}, ${p.update_count_window} update${p.update_count_window !== 1 ? "s" : ""} this week`}
                  className="group relative flex flex-col gap-1 rounded-lg bg-[var(--color-brand-bg)] px-3 py-2.5 transition-colors hover:bg-[var(--color-brand-bg)]/80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-brand-accent)]/60"
                >
                  {/* Left rule */}
                  <div
                    className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full"
                    style={{ backgroundColor: ruleColor }}
                  />
                  {/* Top row */}
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-sm font-medium text-[var(--color-brand-text)]">
                      {p.name}
                    </span>
                    {p.category && (
                      <span
                        className="rounded-full px-2 py-0.5 text-[9px] font-mono uppercase"
                        style={{
                          backgroundColor: "color-mix(in srgb, var(--chart-4) 12%, transparent)",
                          color: "color-mix(in srgb, var(--chart-4) 70%, transparent)",
                        }}
                      >
                        {p.category}
                      </span>
                    )}
                    <span
                      className="rounded-full px-2 py-0.5 text-[9px] font-mono uppercase"
                      style={
                        p.status === "ACTIVE"
                          ? {
                              backgroundColor: "color-mix(in srgb, var(--chart-4) 12%, transparent)",
                              color: "var(--chart-4)",
                            }
                          : {
                              backgroundColor: "color-mix(in srgb, var(--color-brand-muted) 15%, transparent)",
                              color: "var(--color-brand-muted)",
                            }
                      }
                    >
                      {p.status}
                      <span className="sr-only"> status</span>
                    </span>
                    {p.is_dormant && (
                      <span
                        className="rounded-full border px-2 py-0.5 text-[9px] font-mono uppercase"
                        style={{
                          borderColor: "color-mix(in srgb, var(--color-brand-accent-rose) 50%, transparent)",
                          color: "color-mix(in srgb, var(--color-brand-accent-rose) 70%, transparent)",
                        }}
                      >
                        dormant
                        <span className="sr-only"> project</span>
                      </span>
                    )}
                    <span className="ml-auto flex items-center gap-1 text-[10px] font-mono text-[var(--color-brand-accent)]">
                      ★ {p.update_count_window}
                      {deltaArrow(p.update_count_window, p.update_count_previous)}
                    </span>
                  </div>
                  {/* Streak */}
                  <StreakDots
                    sequence={p.streak_dot_sequence}
                    activeColor="var(--chart-4)"
                    label={`streak: ${p.streak_dot_sequence.filter(Boolean).length} of 7 days`}
                  />
                  {/* Body */}
                  {p.is_dormant ? (
                    <p className="text-[11px] italic text-[var(--color-brand-text-dim)]">
                      Last update {p.days_since_last_event} days ago.
                    </p>
                  ) : p.last_event_snippet ? (
                    <p className="text-[11px] italic text-[var(--color-brand-text-dim)] line-clamp-2">
                      {p.last_event_snippet}
                    </p>
                  ) : null}
                  {/* Footer */}
                  <div className="flex items-center gap-2">
                    {p.last_event_type && (
                      <span className="rounded px-1.5 py-0.5 text-[9px] font-mono text-[var(--color-brand-muted)] bg-[var(--color-brand-border)]/50">
                        {p.last_event_type}
                      </span>
                    )}
                    <span className="ml-auto text-[10px] font-mono text-[var(--color-brand-muted)]">
                      {formatDate(p.last_event_date)}
                    </span>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}

      {/* Footer link */}
      {total > projects.length && (
        <div className="mt-3">
          <Link
            href="/projects"
            className="text-xs font-mono text-[var(--color-brand-accent)]/80 hover:text-[var(--color-brand-accent)] transition-colors"
          >
            ↗ See all
          </Link>
        </div>
      )}
    </section>
  );
}
