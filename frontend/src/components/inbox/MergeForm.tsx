"use client";

import { useState } from "react";
import type { CandidateMatch, ProposalDetail } from "@/lib/inbox-api";
import ChipInput from "./ChipInput";

export type MergeSubmitBody = {
  target_entity_id: number;
  add_alias: boolean;
  extra_aliases: string[];
};

type Props = {
  proposal: ProposalDetail;
  candidates: CandidateMatch[];
  selectedTargetId: number | null;
  onSelectTarget: (id: number) => void;
  submitting: boolean;
  onSubmit: (body: MergeSubmitBody) => void;
};

export default function MergeForm({
  proposal,
  candidates,
  selectedTargetId,
  onSelectTarget,
  submitting,
  onSubmit,
}: Props) {
  const [addAlias, setAddAlias] = useState(true);
  const [extras, setExtras] = useState<string[]>([]);

  if (candidates.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-[var(--color-brand-border)] bg-[var(--color-brand-bg)]/40 p-3 text-[11px] italic text-[var(--color-brand-muted)]">
        No candidate to merge into. Use &ldquo;Confirm new&rdquo; to create the entity, then add aliases later.
      </p>
    );
  }

  const target = candidates.find((c) => c.entity_id === selectedTargetId) ?? null;
  const disabled = submitting || target === null;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (disabled || !target) return;
        onSubmit({
          target_entity_id: target.entity_id,
          add_alias: addAlias,
          extra_aliases: extras,
        });
      }}
      className="space-y-3"
    >
      <div>
        <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-brand-muted)]">
          Merge target
        </label>
        <div className="space-y-1.5">
          {candidates.slice(0, 5).map((c) => {
            const selected = c.entity_id === selectedTargetId;
            return (
              <label
                key={c.entity_id}
                className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-[12px] transition-colors ${
                  selected
                    ? "border-[var(--color-brand-accent)] bg-[var(--color-brand-accent)]/5"
                    : "border-[var(--color-brand-border)] hover:bg-[var(--color-brand-bg)]/60"
                }`}
              >
                <input
                  type="radio"
                  name="merge-target"
                  checked={selected}
                  onChange={() => onSelectTarget(c.entity_id)}
                  className="accent-[var(--color-brand-accent)]"
                />
                <span className="flex-1 font-semibold text-[var(--color-brand-text)]">
                  {c.canonical_name}
                </span>
                <span className="font-mono text-[10px] text-[var(--color-brand-muted)]">
                  {Math.round(c.score * 100)}%
                </span>
              </label>
            );
          })}
        </div>
      </div>

      <label className="flex items-center gap-2 text-[12px] text-[var(--color-brand-text-dim)]">
        <input
          type="checkbox"
          checked={addAlias}
          onChange={(e) => setAddAlias(e.target.checked)}
          className="accent-[var(--color-brand-accent)]"
        />
        Add &ldquo;{proposal.surface_name}&rdquo; as an alias
      </label>

      <div>
        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-brand-muted)]">
          Extra aliases
        </label>
        <ChipInput
          values={extras}
          onChange={setExtras}
          placeholder="Optional, press Enter"
          ariaLabel="Extra aliases"
        />
      </div>

      <div className="flex justify-end pt-1">
        <button
          type="submit"
          disabled={disabled}
          className="rounded-lg bg-[var(--color-brand-accent)] px-4 py-2 text-[12px] font-semibold text-[var(--color-brand-bg)] transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {submitting
            ? "Merging…"
            : target
            ? `Merge into ${target.canonical_name}`
            : "Select a target"}
        </button>
      </div>
    </form>
  );
}
