"use client";

import type { CandidateMatch } from "@/lib/inbox-api";

type Props = {
  candidates: CandidateMatch[];
  onSelect: (candidate: CandidateMatch) => void;
  selectedEntityId?: number | null;
};

function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

export default function CandidateList({ candidates, onSelect, selectedEntityId }: Props) {
  const top = candidates.slice(0, 5);

  return (
    <div className="rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--color-brand-muted)]">
          Candidate matches
        </h3>
        <span className="font-mono text-[10px] text-[var(--color-brand-muted)]">
          {candidates.length} ranked
        </span>
      </div>

      {top.length === 0 ? (
        <p className="rounded-lg border border-dashed border-[var(--color-brand-border)] bg-[var(--color-brand-bg)]/40 p-3 text-[11px] italic text-[var(--color-brand-muted)]">
          No similar entities found. You can confirm as new or dismiss.
        </p>
      ) : (
        <ul className="space-y-2">
          {top.map((c) => {
            const selected = c.entity_id === selectedEntityId;
            return (
              <li key={c.entity_id}>
                <button
                  type="button"
                  onClick={() => onSelect(c)}
                  className={`flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors ${
                    selected
                      ? "border-[var(--color-brand-accent)] bg-[var(--color-brand-accent)]/5"
                      : "border-[var(--color-brand-border)] hover:bg-[var(--color-brand-bg)]/60"
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-[13px] font-semibold text-[var(--color-brand-text)]">
                        {c.canonical_name}
                      </span>
                      <span className="font-mono text-[10px] text-[var(--color-brand-muted)]">
                        ({pct(c.score)})
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {c.signals.exact_prefix && (
                        <span className="rounded border border-[var(--color-brand-border)] px-1.5 py-0.5 font-mono text-[9px] text-[var(--color-brand-muted)]">
                          exact prefix
                        </span>
                      )}
                      <span className="rounded border border-[var(--color-brand-border)] px-1.5 py-0.5 font-mono text-[9px] text-[var(--color-brand-muted)]">
                        token {pct(c.signals.token_overlap)}
                      </span>
                      <span className="rounded border border-[var(--color-brand-border)] px-1.5 py-0.5 font-mono text-[9px] text-[var(--color-brand-muted)]">
                        edit Δ {pct(c.signals.edit_distance_ratio)}
                      </span>
                    </div>
                  </div>
                  <span className="shrink-0 rounded-md bg-[var(--color-brand-bg)] px-2.5 py-1 text-[10px] font-medium text-[var(--color-brand-text)]">
                    Merge into…
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
