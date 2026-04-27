"use client";

import { useMemo, useState } from "react";
import type { ProposalDetail, ConfirmNewProjectBody } from "@/lib/inbox-api";
import ChipInput from "./ChipInput";

type Props = {
  proposal: ProposalDetail;
  submitting: boolean;
  errorMessage?: string | null;
  onSubmit: (body: ConfirmNewProjectBody) => void;
};

const STATUS_OPTIONS = ["ACTIVE", "PAUSED", "COMPLETED", "ABANDONED"] as const;

export default function ConfirmNewProjectForm({ proposal, submitting, errorMessage, onSubmit }: Props) {
  const [name, setName] = useState(proposal.surface_name);
  const [aliases, setAliases] = useState<string[]>([]);
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState<typeof STATUS_OPTIONS[number]>("ACTIVE");
  const [description, setDescription] = useState("");
  const [targetDate, setTargetDate] = useState("");

  const hasReplayEvents = useMemo(() => {
    return (proposal.payload?.events?.length ?? 0) > 0;
  }, [proposal.payload]);

  const trimmedName = name.trim();
  const disabled = submitting || trimmedName.length === 0;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (disabled) return;
        onSubmit({
          name: trimmedName,
          aliases,
          category: category.trim() || null,
          status,
          description: description.trim() || null,
          target_date: targetDate || null,
        });
      }}
      className="space-y-3"
    >
      <div>
        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-brand-muted)]">
          Project name
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="w-full rounded-lg border border-[var(--color-brand-border)] bg-[var(--color-brand-bg)] px-3 py-2 text-[12px] text-[var(--color-brand-text)] outline-none focus:border-[var(--color-brand-accent)]"
        />
      </div>

      <div>
        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-brand-muted)]">
          Aliases
        </label>
        <ChipInput
          values={aliases}
          onChange={setAliases}
          placeholder="Other names, press Enter"
          ariaLabel="Project aliases"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-brand-muted)]">
            Category
          </label>
          <input
            type="text"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="optional"
            className="w-full rounded-lg border border-[var(--color-brand-border)] bg-[var(--color-brand-bg)] px-3 py-2 text-[12px] text-[var(--color-brand-text)] outline-none focus:border-[var(--color-brand-accent)]"
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-brand-muted)]">
            Initial status
          </label>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as typeof STATUS_OPTIONS[number])}
            className="w-full rounded-lg border border-[var(--color-brand-border)] bg-[var(--color-brand-bg)] px-3 py-2 text-[12px] text-[var(--color-brand-text)] outline-none focus:border-[var(--color-brand-accent)]"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      </div>

      {hasReplayEvents && (
        <p className="rounded-lg border border-[var(--color-brand-accent-amber)]/40 bg-[var(--color-brand-accent-amber)]/10 px-3 py-2 text-[10px] text-[var(--color-brand-accent-amber)]">
          Replay events will adjust status starting from the value above.
        </p>
      )}

      <div>
        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-brand-muted)]">
          Description
        </label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          placeholder="optional"
          className="w-full resize-y rounded-lg border border-[var(--color-brand-border)] bg-[var(--color-brand-bg)] px-3 py-2 text-[12px] text-[var(--color-brand-text)] outline-none focus:border-[var(--color-brand-accent)]"
        />
      </div>

      <div>
        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-brand-muted)]">
          Target date
        </label>
        <input
          type="date"
          value={targetDate}
          onChange={(e) => setTargetDate(e.target.value)}
          className="w-full rounded-lg border border-[var(--color-brand-border)] bg-[var(--color-brand-bg)] px-3 py-2 text-[12px] text-[var(--color-brand-text)] outline-none focus:border-[var(--color-brand-accent)]"
        />
      </div>

      {errorMessage && (
        <p className="rounded-lg border border-[var(--color-brand-accent-rose)]/40 bg-[var(--color-brand-accent-rose)]/10 px-3 py-2 text-[11px] text-[var(--color-brand-accent-rose)]">
          {errorMessage}
        </p>
      )}

      <div className="flex justify-end pt-1">
        <button
          type="submit"
          disabled={disabled}
          className="rounded-lg bg-[var(--color-brand-accent)] px-4 py-2 text-[12px] font-semibold text-[var(--color-brand-bg)] transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {submitting ? "Confirming…" : "Confirm new project"}
        </button>
      </div>
    </form>
  );
}
