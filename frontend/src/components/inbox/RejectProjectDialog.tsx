"use client";

import { useEffect, useRef, useState } from "react";
import type { RejectProjectBody } from "@/lib/inbox-api";

type Props = {
  open: boolean;
  surfaceName: string;
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (body: RejectProjectBody) => void;
};

export default function RejectProjectDialog({
  open,
  surfaceName,
  submitting,
  onCancel,
  onSubmit,
}: Props) {
  if (!open) return null;
  return (
    <RejectProjectDialogInner
      surfaceName={surfaceName}
      submitting={submitting}
      onCancel={onCancel}
      onSubmit={onSubmit}
    />
  );
}

function RejectProjectDialogInner({
  surfaceName,
  submitting,
  onCancel,
  onSubmit,
}: Omit<Props, "open">) {
  const [mode, setMode] = useState<"dismiss" | "blocklist">("dismiss");
  const [note, setNote] = useState("");
  const submitRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    submitRef.current?.focus();
  }, []);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onCancel]);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative w-full max-w-md rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] p-5 shadow-2xl shadow-black/40">
        <h3 className="font-heading text-base text-[var(--color-brand-text)]">
          Reject project &ldquo;{surfaceName}&rdquo;
        </h3>
        <p className="mt-1.5 text-[11px] text-[var(--color-brand-text-dim)]">
          Choose how to silence this proposal.
        </p>

        <div className="mt-4 space-y-2">
          <label
            className={`flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 text-[12px] transition-colors ${
              mode === "dismiss"
                ? "border-[var(--color-brand-accent)] bg-[var(--color-brand-accent)]/5"
                : "border-[var(--color-brand-border)] hover:bg-[var(--color-brand-bg)]/60"
            }`}
          >
            <input
              type="radio"
              name="reject-mode"
              value="dismiss"
              checked={mode === "dismiss"}
              onChange={() => setMode("dismiss")}
              className="mt-0.5 accent-[var(--color-brand-accent)]"
            />
            <div>
              <div className="font-semibold text-[var(--color-brand-text)]">
                Dismiss this time only
              </div>
              <div className="mt-0.5 text-[11px] text-[var(--color-brand-text-dim)]">
                The same surface may resurface in future shred runs.
              </div>
            </div>
          </label>

          <label
            className={`flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 text-[12px] transition-colors ${
              mode === "blocklist"
                ? "border-[var(--color-brand-accent-rose)] bg-[var(--color-brand-accent-rose)]/5"
                : "border-[var(--color-brand-border)] hover:bg-[var(--color-brand-bg)]/60"
            }`}
          >
            <input
              type="radio"
              name="reject-mode"
              value="blocklist"
              checked={mode === "blocklist"}
              onChange={() => setMode("blocklist")}
              className="mt-0.5 accent-[var(--color-brand-accent-rose)]"
            />
            <div>
              <div className="font-semibold text-[var(--color-brand-text)]">
                Blocklist this name
              </div>
              <div className="mt-0.5 text-[11px] text-[var(--color-brand-text-dim)]">
                Silences current pending duplicates and prevents future proposal creation.
                Removable later from the Blocklist drawer.
              </div>
            </div>
          </label>
        </div>

        <div className="mt-4">
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-brand-muted)]">
            Note
          </label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            placeholder="optional"
            className="w-full resize-y rounded-lg border border-[var(--color-brand-border)] bg-[var(--color-brand-bg)] px-3 py-2 text-[12px] text-[var(--color-brand-text)] outline-none focus:border-[var(--color-brand-accent)]"
          />
        </div>

        <div className="mt-5 flex justify-end gap-2.5">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-[var(--color-brand-border)] px-3.5 py-1.5 text-xs font-medium text-[var(--color-brand-text-dim)] hover:bg-[var(--color-brand-bg)] hover:text-[var(--color-brand-text)]"
          >
            Cancel
          </button>
          <button
            ref={submitRef}
            type="button"
            disabled={submitting}
            onClick={() =>
              onSubmit({ mode, note: note.trim() || null })
            }
            className={`rounded-lg px-3.5 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50 ${
              mode === "blocklist"
                ? "bg-[var(--color-brand-accent-rose)]"
                : "bg-[var(--color-brand-text-dim)]"
            }`}
          >
            {submitting ? "Submitting…" : mode === "blocklist" ? "Reject & blocklist" : "Reject"}
          </button>
        </div>
      </div>
    </div>
  );
}
