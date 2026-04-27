"use client";

import type { ProposalDetail } from "@/lib/inbox-api";

type Props = {
  proposal: ProposalDetail;
};

const SENTIMENT_COLORS: Record<string, string> = {
  POSITIVE: "var(--color-brand-accent-green)",
  NEGATIVE: "var(--color-brand-accent-rose)",
  NEUTRAL: "var(--color-brand-muted)",
};

function sentimentColor(label: string | null): string {
  if (!label) return "var(--color-brand-muted)";
  return SENTIMENT_COLORS[label.toUpperCase()] ?? "var(--color-brand-muted)";
}

function Chip({ label, color }: { label: string; color?: string }) {
  return (
    <span
      className="inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider"
      style={{
        borderColor: color ?? "var(--color-brand-border)",
        color: color ?? "var(--color-brand-muted)",
      }}
    >
      {label}
    </span>
  );
}

export default function PayloadPreview({ proposal }: Props) {
  const isPerson = proposal.entity_type === "person";
  const mentions = proposal.payload?.mentions ?? [];
  const events = proposal.payload?.events ?? [];
  const items = isPerson ? mentions : events;

  return (
    <div className="rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--color-brand-muted)]">
          {isPerson ? "Person mention" : "Project event"}
          {items.length !== 1 ? "s" : ""}
        </h3>
        <span className="font-mono text-[10px] text-[var(--color-brand-muted)]">
          {items.length} occurrence{items.length === 1 ? "" : "s"}
        </span>
      </div>

      {items.length === 0 ? (
        <p className="rounded-lg border border-dashed border-[var(--color-brand-border)] bg-[var(--color-brand-bg)]/40 p-3 text-[11px] italic text-[var(--color-brand-muted)]">
          Payload empty — accept will create a no-mention/no-event entity row.
        </p>
      ) : (
        <ul className="space-y-3">
          {isPerson
            ? mentions.map((m, i) => (
                <li
                  key={i}
                  className="border-l-2 border-[var(--color-brand-accent)]/40 pl-3"
                >
                  {m.interaction_context && (
                    <p className="text-[12px] leading-relaxed text-[var(--color-brand-text)]">
                      &ldquo;{m.interaction_context}&rdquo;
                    </p>
                  )}
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {m.relationship_hint && <Chip label={m.relationship_hint} />}
                    {m.sentiment && (
                      <Chip label={m.sentiment} color={sentimentColor(m.sentiment)} />
                    )}
                  </div>
                  {m.linked_event_hint && (
                    <p className="mt-1.5 text-[10px] text-[var(--color-brand-muted)]">
                      Linked event: <span className="italic">{m.linked_event_hint}</span>
                    </p>
                  )}
                </li>
              ))
            : events.map((e, i) => (
                <li
                  key={i}
                  className="border-l-2 border-[var(--color-brand-accent)]/40 pl-3"
                >
                  <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                    <Chip label={e.event_type} color="var(--color-brand-accent)" />
                    {e.suggested_project_status && (
                      <Chip
                        label={`status: ${e.suggested_project_status}`}
                        color="var(--color-brand-accent-amber)"
                      />
                    )}
                  </div>
                  <p className="text-[12px] leading-relaxed text-[var(--color-brand-text)]">
                    {e.description}
                  </p>
                  {e.linked_event_hint && (
                    <p className="mt-1.5 text-[10px] text-[var(--color-brand-muted)]">
                      Linked event: <span className="italic">{e.linked_event_hint}</span>
                    </p>
                  )}
                </li>
              ))}
        </ul>
      )}
    </div>
  );
}
