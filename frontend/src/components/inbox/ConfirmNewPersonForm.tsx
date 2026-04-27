"use client";

import { useState } from "react";
import type { ProposalDetail, ConfirmNewPersonBody } from "@/lib/inbox-api";
import ChipInput from "./ChipInput";

type Props = {
  proposal: ProposalDetail;
  submitting: boolean;
  errorMessage?: string | null;
  onSubmit: (body: ConfirmNewPersonBody) => void;
};

const RELATIONSHIP_SUGGESTIONS = ["friend", "colleague", "family", "client", "partner"];

export default function ConfirmNewPersonForm({ proposal, submitting, errorMessage, onSubmit }: Props) {
  const [canonicalName, setCanonicalName] = useState(proposal.surface_name);
  const [aliases, setAliases] = useState<string[]>([]);
  const [relationship, setRelationship] = useState("");
  const [notes, setNotes] = useState("");

  const trimmedName = canonicalName.trim();
  const disabled = submitting || trimmedName.length === 0;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (disabled) return;
        onSubmit({
          canonical_name: trimmedName,
          aliases,
          relationship_type: relationship.trim() || null,
          notes: notes.trim() || null,
        });
      }}
      className="space-y-3"
    >
      <div>
        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-brand-muted)]">
          Canonical name
        </label>
        <input
          type="text"
          value={canonicalName}
          onChange={(e) => setCanonicalName(e.target.value)}
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
          placeholder="Add nickname or other spelling, press Enter"
          ariaLabel="Aliases"
        />
      </div>

      <div>
        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-brand-muted)]">
          Relationship
        </label>
        <input
          type="text"
          list="relationship-suggestions"
          value={relationship}
          onChange={(e) => setRelationship(e.target.value)}
          placeholder="optional"
          className="w-full rounded-lg border border-[var(--color-brand-border)] bg-[var(--color-brand-bg)] px-3 py-2 text-[12px] text-[var(--color-brand-text)] outline-none focus:border-[var(--color-brand-accent)]"
        />
        <datalist id="relationship-suggestions">
          {RELATIONSHIP_SUGGESTIONS.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      </div>

      <div>
        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-brand-muted)]">
          Notes
        </label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder="optional"
          className="w-full resize-y rounded-lg border border-[var(--color-brand-border)] bg-[var(--color-brand-bg)] px-3 py-2 text-[12px] text-[var(--color-brand-text)] outline-none focus:border-[var(--color-brand-accent)]"
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
          {submitting ? "Confirming…" : "Confirm new person"}
        </button>
      </div>
    </form>
  );
}
