"use client";

import { useState } from "react";
import type {
  ProposalDetail,
  ConfirmNewProjectBody,
  MergeProjectBody,
  DismissBody,
  BlocklistBody,
  RejectProjectBody,
} from "@/lib/inbox-api";
import ConfirmNewProjectForm from "./ConfirmNewProjectForm";
import MergeForm, { type MergeSubmitBody } from "./MergeForm";
import RejectProjectDialog from "./RejectProjectDialog";
import ActionTabs from "./ActionTabs";
import ConfirmDialog from "@/components/chat/ConfirmDialog";

type ProjectTab = "confirm" | "merge" | "reject" | "dismiss" | "blocklist";

export type ActionPanelProjectProps = {
  proposal: ProposalDetail;
  selectedTargetId: number | null;
  onSelectTarget: (id: number) => void;
  submitting: boolean;
  confirmExistingError: string | null;
  pendingDuplicateCount: number;
  onConfirmNew: (body: ConfirmNewProjectBody) => void;
  onMerge: (body: MergeProjectBody) => void;
  onReject: (body: RejectProjectBody) => void;
  onDismiss: (body: DismissBody) => void;
  onBlocklist: (body: BlocklistBody) => void;
  onSwitchToMerge: () => void;
};

export default function ActionPanelProject({
  proposal,
  selectedTargetId,
  onSelectTarget,
  submitting,
  confirmExistingError,
  pendingDuplicateCount,
  onConfirmNew,
  onMerge,
  onReject,
  onDismiss,
  onBlocklist,
  onSwitchToMerge,
}: ActionPanelProjectProps) {
  const candidates = proposal.candidate_matches;
  const [tab, setTab] = useState<ProjectTab>(() =>
    candidates.length > 0 ? "merge" : "confirm"
  );

  const [dismissNote, setDismissNote] = useState("");
  const [showDismissConfirm, setShowDismissConfirm] = useState(false);
  const [showRejectDialog, setShowRejectDialog] = useState(false);

  const [blockReason, setBlockReason] = useState<"manual_block" | "system_noise">("manual_block");
  const [blockNote, setBlockNote] = useState("");
  const [blockCascade, setBlockCascade] = useState(true);
  const [showBlockConfirm, setShowBlockConfirm] = useState(false);

  function handleMergeSubmit(body: MergeSubmitBody) {
    onMerge(body);
  }

  return (
    <div className="rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] p-5">
      <h3 className="mb-3 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--color-brand-muted)]">
        Action
      </h3>

      <ActionTabs<ProjectTab>
        active={tab}
        onChange={(id) => {
          if (id === "reject") {
            setShowRejectDialog(true);
            return;
          }
          setTab(id);
        }}
        tabs={[
          { id: "confirm", label: "Confirm new" },
          { id: "merge", label: "Merge existing" },
          { id: "reject", label: "Reject", destructive: true },
          { id: "dismiss", label: "Dismiss", destructive: true },
          { id: "blocklist", label: "Blocklist", destructive: true },
        ]}
      />

      <div className="pt-4">
        {tab === "confirm" && (
          <>
            {confirmExistingError && (
              <div className="mb-3 rounded-lg border border-[var(--color-brand-accent-amber)]/40 bg-[var(--color-brand-accent-amber)]/10 px-3 py-2 text-[11px] text-[var(--color-brand-accent-amber)]">
                <p className="font-semibold">{confirmExistingError}</p>
                <button
                  type="button"
                  onClick={() => {
                    onSwitchToMerge();
                    setTab("merge");
                  }}
                  className="mt-1.5 underline hover:opacity-90"
                >
                  Switch to merge instead →
                </button>
              </div>
            )}
            <ConfirmNewProjectForm
              proposal={proposal}
              submitting={submitting}
              onSubmit={onConfirmNew}
            />
          </>
        )}

        {tab === "merge" && (
          <MergeForm
            proposal={proposal}
            candidates={candidates}
            selectedTargetId={selectedTargetId}
            onSelectTarget={onSelectTarget}
            submitting={submitting}
            onSubmit={handleMergeSubmit}
          />
        )}

        {tab === "dismiss" && (
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-brand-muted)]">
                Note
              </label>
              <textarea
                value={dismissNote}
                onChange={(e) => setDismissNote(e.target.value)}
                rows={2}
                placeholder="optional"
                className="w-full resize-y rounded-lg border border-[var(--color-brand-border)] bg-[var(--color-brand-bg)] px-3 py-2 text-[12px] text-[var(--color-brand-text)] outline-none focus:border-[var(--color-brand-accent)]"
              />
            </div>
            <div className="flex justify-end">
              <button
                type="button"
                disabled={submitting}
                onClick={() => setShowDismissConfirm(true)}
                className="rounded-lg border border-[var(--color-brand-border)] px-4 py-2 text-[12px] font-medium text-[var(--color-brand-text-dim)] hover:bg-[var(--color-brand-bg)] hover:text-[var(--color-brand-text)] disabled:opacity-50"
              >
                Dismiss proposal
              </button>
            </div>
          </div>
        )}

        {tab === "blocklist" && (
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-brand-muted)]">
                Reason
              </label>
              <select
                value={blockReason}
                onChange={(e) => setBlockReason(e.target.value as "manual_block" | "system_noise")}
                className="w-full rounded-lg border border-[var(--color-brand-border)] bg-[var(--color-brand-bg)] px-3 py-2 text-[12px] text-[var(--color-brand-text)] outline-none focus:border-[var(--color-brand-accent)]"
              >
                <option value="manual_block">Manual block</option>
                <option value="system_noise">System noise</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-brand-muted)]">
                Note
              </label>
              <textarea
                value={blockNote}
                onChange={(e) => setBlockNote(e.target.value)}
                rows={2}
                placeholder="optional"
                className="w-full resize-y rounded-lg border border-[var(--color-brand-border)] bg-[var(--color-brand-bg)] px-3 py-2 text-[12px] text-[var(--color-brand-text)] outline-none focus:border-[var(--color-brand-accent)]"
              />
            </div>
            <label className="flex items-center gap-2 text-[12px] text-[var(--color-brand-text-dim)]">
              <input
                type="checkbox"
                checked={blockCascade}
                onChange={(e) => setBlockCascade(e.target.checked)}
                className="accent-[var(--color-brand-accent-rose)]"
              />
              Cascade pending duplicates
              {pendingDuplicateCount > 0 && (
                <span className="font-mono text-[10px] text-[var(--color-brand-muted)]">
                  ({pendingDuplicateCount} other pending)
                </span>
              )}
            </label>
            <div className="flex justify-end">
              <button
                type="button"
                disabled={submitting}
                onClick={() => setShowBlockConfirm(true)}
                className="rounded-lg bg-[var(--color-brand-accent-rose)] px-4 py-2 text-[12px] font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                Blocklist
              </button>
            </div>
          </div>
        )}
      </div>

      <RejectProjectDialog
        open={showRejectDialog}
        surfaceName={proposal.surface_name}
        submitting={submitting}
        onCancel={() => setShowRejectDialog(false)}
        onSubmit={(body) => {
          setShowRejectDialog(false);
          onReject(body);
        }}
      />

      <ConfirmDialog
        open={showDismissConfirm}
        title="Dismiss proposal?"
        message='The same surface may re-appear in future shred runs. Use "Blocklist" or "Reject → blocklist" to silence it permanently.'
        confirmLabel="Dismiss"
        onConfirm={() => {
          setShowDismissConfirm(false);
          onDismiss({ note: dismissNote.trim() || null });
        }}
        onCancel={() => setShowDismissConfirm(false)}
      />

      <ConfirmDialog
        open={showBlockConfirm}
        title={`Blocklist "${proposal.surface_name}"?`}
        message={`The surface will be blocked from future proposal creation${
          blockCascade && pendingDuplicateCount > 0
            ? ` and ${pendingDuplicateCount} other pending proposal${
                pendingDuplicateCount === 1 ? "" : "s"
              } will be silenced`
            : ""
        }.`}
        confirmLabel="Blocklist"
        onConfirm={() => {
          setShowBlockConfirm(false);
          onBlocklist({
            reason: blockReason,
            note: blockNote.trim() || null,
            cascade_pending: blockCascade,
          });
        }}
        onCancel={() => setShowBlockConfirm(false)}
      />
    </div>
  );
}
