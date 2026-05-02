"use client";

import { useState } from "react";
import type { LearningRow, LearningSubjectTimeline as TimelineData, Sentiment } from "@/lib/api";
import LearningSubjectTimeline from "./LearningSubjectTimeline";

type Props = {
  items: LearningRow[];
  bySubject: TimelineData[];
  loading: boolean;
};

const SUBJECT_COLORS: Record<string, string> = {
  portuguese: "var(--color-brand-accent-green)",
  "biophilic urbanism": "var(--color-brand-accent)",
  "sustainable urban runoff management": "var(--color-brand-accent)",
  "construction vocabulary": "var(--color-brand-accent-amber)",
};

function getSubjectColor(subject: string): string {
  const lower = subject.toLowerCase();
  for (const [key, val] of Object.entries(SUBJECT_COLORS)) {
    if (lower.includes(key)) return val;
  }
  return "var(--chart-5)";
}

const SENTIMENT_CHIP_COLORS: Record<Sentiment, string> = {
  POSITIVE: "var(--color-brand-accent-green)",
  NEGATIVE: "var(--color-brand-accent-rose)",
  NEUTRAL: "var(--color-brand-muted)",
};

function formatDate(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export default function LearningProgress({ items, bySubject, loading }: Props) {
  const [viewMode, setViewMode] = useState<"sessions" | "subject">("sessions");
  const milestoneCount = items.filter((l) => l.milestone).length;

  return (
    <div className="rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-brand-accent-green)]/15">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--color-brand-accent-green)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
              <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
            </svg>
          </div>
          <h2 className="font-heading text-sm text-[var(--color-brand-text)]">Learning Progress</h2>
        </div>

        <div className="flex items-center gap-3">
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

          {/* View toggle */}
          {!loading && (
            <div role="radiogroup" aria-label="Learning view" className="flex items-center rounded border border-[var(--color-brand-border)] overflow-hidden">
              {(["sessions", "subject"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  role="radio"
                  aria-checked={viewMode === mode}
                  onClick={() => setViewMode(mode)}
                  className={`px-3 py-1 text-[10px] font-mono transition-colors ${
                    viewMode === mode
                      ? "bg-[var(--color-brand-accent)]/10 text-[var(--color-brand-accent)] border-b-2 border-[var(--color-brand-accent)]"
                      : "text-[var(--color-brand-text-dim)] hover:text-[var(--color-brand-text)]"
                  }`}
                >
                  {mode === "sessions" ? "Sessions" : "By subject"}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-[var(--color-brand-border)]/50" />
          ))}
        </div>
      ) : viewMode === "sessions" ? (
        items.length === 0 ? (
          <p className="py-8 text-center text-xs text-[var(--color-brand-text-dim)]">
            No learning events this week.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((l, i) => {
              const color = getSubjectColor(l.subject);
              const sentimentColor = l.sentiment ? SENTIMENT_CHIP_COLORS[l.sentiment] : null;
              return (
                <div
                  key={i}
                  className="relative overflow-hidden rounded-lg bg-[var(--color-brand-bg)] px-3.5 py-3 transition-colors hover:bg-[var(--color-brand-bg)]/80"
                >
                  <div
                    className="absolute left-0 top-0 bottom-0 w-[3px]"
                    style={{ backgroundColor: color }}
                  />
                  <div className="mb-1.5 flex items-center gap-2">
                    {l.subject && (
                      <span
                        className="rounded px-1.5 py-0.5 text-[10px] font-mono font-semibold"
                        style={{
                          backgroundColor: `color-mix(in srgb, ${color} 15%, transparent)`,
                          color,
                        }}
                      >
                        {l.subject}
                      </span>
                    )}
                    {l.milestone && (
                      <span className="flex items-center gap-1 rounded-full bg-[var(--color-brand-accent-green)]/15 px-2 py-0.5 text-[9px] font-semibold text-[var(--color-brand-accent-green)]">
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
                  <div className="mt-1.5 flex items-center justify-between">
                    <span className="text-[10px] font-mono text-[var(--color-brand-muted)]">
                      {formatDate(l.date)}
                    </span>
                    {sentimentColor && (
                      <span
                        className="rounded-full px-2 py-0.5 text-[9px] font-mono uppercase"
                        style={{
                          backgroundColor: `color-mix(in srgb, ${sentimentColor} 15%, transparent)`,
                          color: sentimentColor,
                        }}
                      >
                        {l.sentiment?.toLowerCase()}
                        <span className="sr-only"> sentiment</span>
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )
      ) : (
        <LearningSubjectTimeline items={bySubject} />
      )}
    </div>
  );
}
