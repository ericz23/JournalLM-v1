"use client";

import type { ProposalDetail as ProposalDetailType } from "@/lib/inbox-api";
import PayloadPreview from "./PayloadPreview";
import CandidateList from "./CandidateList";

type Props = {
  loading: boolean;
  proposal: ProposalDetailType | null;
  selectedTargetId: number | null;
  onSelectTarget: (id: number) => void;
  actionPanel: React.ReactNode;
};

const STATUS_COLORS: Record<string, string> = {
  pending: "var(--color-brand-accent-amber)",
  accepted_new: "var(--color-brand-accent-green)",
  merged_existing: "var(--color-brand-accent-green)",
  dismissed: "var(--color-brand-muted)",
  rejected: "var(--color-brand-accent-rose)",
  blocked: "var(--color-brand-accent-rose)",
};

function copy(text: string) {
  void navigator.clipboard?.writeText(text);
}

export default function ProposalDetail({
  loading,
  proposal,
  selectedTargetId,
  onSelectTarget,
  actionPanel,
}: Props) {
  if (loading && !proposal) {
    return (
      <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-[var(--color-brand-border)] p-12">
        <p className="text-[12px] italic text-[var(--color-brand-muted)]">
          Loading proposal…
        </p>
      </div>
    );
  }

  if (!proposal) {
    return (
      <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-[var(--color-brand-border)] p-12">
        <div className="text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-brand-bg)] text-[var(--color-brand-muted)]">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
              <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
            </svg>
          </div>
          <p className="font-heading text-base text-[var(--color-brand-text)]">
            Select a proposal to review
          </p>
          <p className="mt-1 text-[11px] text-[var(--color-brand-muted)]">
            The list on the left shows everything pending your decision.
          </p>
        </div>
      </div>
    );
  }

  const isPerson = proposal.entity_type === "person";
  const typeColor = isPerson ? "var(--color-brand-accent)" : "var(--chart-3)";
  const statusColor = STATUS_COLORS[proposal.status] ?? "var(--color-brand-muted)";

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h1 className="font-heading text-2xl tracking-tight text-[var(--color-brand-text)]">
                {proposal.surface_name}
              </h1>
              <button
                type="button"
                onClick={() => copy(proposal.surface_name)}
                title="Copy surface name"
                className="rounded p-1 text-[var(--color-brand-muted)] hover:text-[var(--color-brand-text)]"
                aria-label="Copy surface name"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
              </button>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span
                className="rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider"
                style={{ borderColor: typeColor, color: typeColor }}
              >
                {proposal.entity_type}
              </span>
              <span
                className="rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider"
                style={{ borderColor: statusColor, color: statusColor }}
              >
                {proposal.status.replace("_", " ")}
              </span>
              <span className="font-mono text-[10px] text-[var(--color-brand-muted)]">
                entry {proposal.entry_date}
              </span>
              {proposal.life_event_id !== null && (
                <span className="font-mono text-[10px] text-[var(--color-brand-muted)]">
                  · life_event #{proposal.life_event_id}
                </span>
              )}
            </div>
            {proposal.resolution_note && (
              <p className="mt-2 text-[11px] italic text-[var(--color-brand-muted)]">
                Resolution note: {proposal.resolution_note}
              </p>
            )}
          </div>
          <div className="hidden shrink-0 text-right font-mono text-[10px] text-[var(--color-brand-muted)] xl:block">
            <div>created {proposal.created_at.slice(0, 10)}</div>
            {proposal.resolved_at && <div>resolved {proposal.resolved_at.slice(0, 10)}</div>}
          </div>
        </div>
      </div>

      <PayloadPreview proposal={proposal} />

      <CandidateList
        candidates={proposal.candidate_matches}
        onSelect={(c) => onSelectTarget(c.entity_id)}
        selectedEntityId={selectedTargetId}
      />

      {actionPanel}
    </div>
  );
}
