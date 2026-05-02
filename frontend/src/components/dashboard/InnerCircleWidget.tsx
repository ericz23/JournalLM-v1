"use client";

import Link from "next/link";
import type { InnerCirclePerson, Sentiment } from "@/lib/api";
import InsightLine from "./widgets/InsightLine";
import SentimentBar from "./widgets/SentimentBar";
import EmptyState from "./widgets/EmptyState";

const SENTIMENT_RULE_COLOR: Record<string, string> = {
  POSITIVE: "var(--color-brand-accent-green)",
  NEGATIVE: "var(--color-brand-accent-rose)",
  NEUTRAL: "var(--color-brand-muted)",
  MIXED: "var(--chart-5)",
};

function ruleColor(dominant: string | null): string {
  return (dominant && SENTIMENT_RULE_COLOR[dominant]) || "var(--color-brand-border)";
}

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
  return (
    <span className="text-[9px] font-mono text-[var(--color-brand-muted)]">=</span>
  );
}

function formatDate(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

type Props = {
  people: InnerCirclePerson[];
  total: number;
  insight: string | null;
  loading: boolean;
};

export default function InnerCircleWidget({ people, total, insight, loading }: Props) {
  return (
    <section
      aria-labelledby="inner-circle-heading"
      className="rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] p-5"
    >
      {/* Header */}
      <div className="mb-1 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div
            className="flex h-8 w-8 items-center justify-center rounded-lg"
            style={{ backgroundColor: "color-mix(in srgb, var(--chart-3) 15%, transparent)" }}
          >
            {/* circle-of-people icon */}
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--chart-3)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
          </div>
          <h2
            id="inner-circle-heading"
            className="font-heading text-sm text-[var(--color-brand-text)]"
          >
            Inner Circle
          </h2>
        </div>
        {!loading && total > 0 && (
          <span className="rounded-full bg-[var(--chart-3)]/10 px-2.5 py-0.5 text-[10px] font-mono font-semibold text-[var(--chart-3)]">
            {people.length} of {total} people
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
      ) : people.length === 0 ? (
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
              <circle cx="12" cy="12" r="10" />
            </svg>
          }
          title="Quiet week"
          subtitle="No people surfaced from this week's entries yet."
        />
      ) : (
        <ul className="space-y-2 max-h-[450px] overflow-y-auto pr-1">
          {people.map((p) => (
            <li key={p.person_id}>
              <Link
                href={`/people/${p.person_id}`}
                aria-label={`${p.canonical_name}, ${p.mention_count_window} mention${p.mention_count_window !== 1 ? "s" : ""}`}
                className="group relative flex flex-col gap-1 rounded-lg bg-[var(--color-brand-bg)] px-3 py-2.5 transition-colors hover:bg-[var(--color-brand-bg)]/80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-brand-accent)]/60"
              >
                {/* Left rule */}
                <div
                  className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full"
                  style={{ backgroundColor: ruleColor(p.dominant_sentiment) }}
                />
                {/* Top row */}
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-[var(--color-brand-text)]">
                    {p.canonical_name}
                  </span>
                  {p.relationship_type && (
                    <span
                      className="rounded-full px-2 py-0.5 text-[9px] font-mono uppercase"
                      style={{
                        backgroundColor: "color-mix(in srgb, var(--chart-3) 12%, transparent)",
                        color: "var(--chart-3)",
                      }}
                    >
                      {p.relationship_type}
                      <span className="sr-only"> relationship</span>
                    </span>
                  )}
                  <span className="ml-auto flex items-center gap-1 text-[10px] font-mono text-[var(--color-brand-accent)]">
                    ★ {p.mention_count_window}
                    {deltaArrow(p.mention_count_window, p.mention_count_previous)}
                  </span>
                </div>
                {/* Snippet */}
                {p.last_mention_snippet && (
                  <p className="truncate text-[11px] italic text-[var(--color-brand-text-dim)]">
                    {p.last_mention_snippet}
                  </p>
                )}
                {/* Footer */}
                <div className="flex items-center gap-2">
                  <div className="flex-1">
                    <SentimentBar distribution={p.sentiment_distribution as Record<Sentiment, number>} height={3} />
                  </div>
                  <span className="shrink-0 text-[10px] font-mono text-[var(--color-brand-muted)]">
                    {formatDate(p.last_mention_date)}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {/* Footer link */}
      {total > people.length && (
        <div className="mt-3">
          <Link
            href="/people"
            className="text-xs font-mono text-[var(--color-brand-accent)]/80 hover:text-[var(--color-brand-accent)] transition-colors"
          >
            ↗ See all
          </Link>
        </div>
      )}
    </section>
  );
}
