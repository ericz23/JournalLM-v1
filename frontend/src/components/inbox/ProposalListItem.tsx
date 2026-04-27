"use client";

import type { ProposalSummary, CandidateMatch } from "@/lib/inbox-api";

type Props = {
  proposal: ProposalSummary;
  selected: boolean;
  topCandidate?: CandidateMatch | null;
  onSelect: () => void;
};

const STATUS_COLORS: Record<string, string> = {
  pending: "var(--color-brand-accent-amber)",
  accepted_new: "var(--color-brand-accent-green)",
  merged_existing: "var(--color-brand-accent-green)",
  dismissed: "var(--color-brand-muted)",
  rejected: "var(--color-brand-accent-rose)",
  blocked: "var(--color-brand-accent-rose)",
};

export default function ProposalListItem({
  proposal,
  selected,
  topCandidate,
  onSelect,
}: Props) {
  const isPerson = proposal.entity_type === "person";
  const typeColor = isPerson
    ? "var(--color-brand-accent)"
    : "var(--chart-3)";
  const statusColor = STATUS_COLORS[proposal.status] ?? "var(--color-brand-muted)";

  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      onClick={onSelect}
      className={`flex w-full flex-col gap-1 border-l-2 px-3 py-2.5 text-left transition-colors ${
        selected
          ? "border-[var(--color-brand-accent)] bg-[var(--color-brand-accent)]/5"
          : "border-transparent hover:bg-[var(--color-brand-bg)]/60"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="truncate text-[13px] font-semibold text-[var(--color-brand-text)]">
          {proposal.surface_name}
        </span>
        <span
          className="ml-auto shrink-0 rounded-full border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider"
          style={{ borderColor: typeColor, color: typeColor }}
        >
          {proposal.entity_type}
        </span>
      </div>

      <div className="flex items-center gap-2 font-mono text-[10px] text-[var(--color-brand-muted)]">
        <span>{proposal.entry_date}</span>
        {proposal.life_event_id !== null && (
          <span title="Linked to life event">
            <svg
              width="11"
              height="11"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </svg>
          </span>
        )}
        {proposal.status !== "pending" && (
          <span
            className="ml-auto rounded-full px-1.5 py-0.5 text-[9px] uppercase"
            style={{ color: statusColor, borderColor: statusColor }}
          >
            {proposal.status.replace("_", " ")}
          </span>
        )}
      </div>

      <div className="text-[10px] text-[var(--color-brand-muted)]">
        {topCandidate ? (
          <>
            top match:{" "}
            <span className="text-[var(--color-brand-text-dim)]">
              {topCandidate.canonical_name}
            </span>{" "}
            ({Math.round(topCandidate.score * 100)}%)
          </>
        ) : (
          <span className="italic">no candidates</span>
        )}
      </div>
    </button>
  );
}
