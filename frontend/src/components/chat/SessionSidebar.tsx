"use client";

import { cn } from "@/lib/utils";
import type { ChatSessionSummary } from "@/lib/api";

export type Session = ChatSessionSummary;

type Props = {
  sessions: Session[];
  activeId: string | null;
  tempSessionId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onNewTemp: () => void;
  onSaveTemp: () => void;
  onDelete: (id: string) => void;
};

function formatRelative(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 7) return `${diffDay}d ago`;
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

export default function SessionSidebar({
  sessions,
  activeId,
  tempSessionId,
  onSelect,
  onNew,
  onNewTemp,
  onSaveTemp,
  onDelete,
}: Props) {
  return (
    <div className="flex h-full w-[240px] flex-col border-r border-[var(--color-slate-border)] bg-[var(--color-slate-bg)]/80">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--color-slate-border)] px-3 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-slate-text-dim)]">
          Chats
        </h2>
        <div className="flex items-center gap-1.5">
          <button
            onClick={onNewTemp}
            className="flex h-6 w-6 items-center justify-center rounded-lg border border-[var(--color-slate-border)] text-[var(--color-slate-muted)] hover:text-[var(--color-slate-text)] hover:border-[var(--color-slate-text-dim)] transition-all"
            title="Temporary chat"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </button>
          <button
            onClick={onNew}
            className="flex h-6 w-6 items-center justify-center rounded-lg bg-[var(--color-slate-accent)] text-[var(--color-slate-bg)] text-sm font-bold hover:opacity-90 hover:shadow-[0_0_8px_-2px] hover:shadow-[var(--color-slate-accent)]/40 transition-all"
            title="New chat"
          >
            +
          </button>
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto py-1">
        {/* Temporary chat entry */}
        {tempSessionId && (
          <div
            onClick={() => onSelect(tempSessionId)}
            className={cn(
              "group mx-1.5 my-0.5 flex items-start justify-between rounded-lg px-2.5 py-2 cursor-pointer transition-all",
              tempSessionId === activeId
                ? "bg-[var(--color-slate-surface)] shadow-[inset_0_0_0_1px] shadow-[var(--color-slate-muted)]/20"
                : "hover:bg-[var(--color-slate-surface)]/50"
            )}
          >
            <div className="min-w-0 flex-1 opacity-60">
              <p className="truncate text-sm italic text-[var(--color-slate-muted)]">
                Temporary Chat
              </p>
              <p className="mt-0.5 text-[10px] text-[var(--color-slate-muted)]">
                Not saved
              </p>
            </div>
            <div className="ml-1 mt-0.5 flex items-center gap-0.5">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onSaveTemp();
                }}
                className="flex h-5 w-5 shrink-0 items-center justify-center rounded opacity-0 group-hover:opacity-100 text-[var(--color-slate-muted)] hover:text-[var(--color-slate-accent-green)] transition-all"
                title="Save this chat"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
                  <polyline points="17 21 17 13 7 13 7 21" />
                  <polyline points="7 3 7 8 15 8" />
                </svg>
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(tempSessionId);
                }}
                className="flex h-5 w-5 shrink-0 items-center justify-center rounded opacity-0 group-hover:opacity-100 text-[var(--color-slate-muted)] hover:text-[var(--color-slate-accent-rose)] transition-all"
                title="Discard"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          </div>
        )}

        {/* Saved sessions */}
        {sessions.length === 0 && !tempSessionId ? (
          <p className="px-3 py-4 text-xs text-[var(--color-slate-muted)] italic">
            No conversations yet.
          </p>
        ) : (
          sessions.map((s) => (
            <div
              key={s.id}
              onClick={() => onSelect(s.id)}
              className={cn(
                "group mx-1.5 my-0.5 flex items-start justify-between rounded-lg px-2.5 py-2 cursor-pointer transition-all",
                s.id === activeId
                  ? "bg-[var(--color-slate-surface)] shadow-[inset_0_0_0_1px] shadow-[var(--color-slate-accent)]/15"
                  : "hover:bg-[var(--color-slate-surface)]/50"
              )}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-[var(--color-slate-text)]">
                  {s.title || "New chat"}
                </p>
                <p className="mt-0.5 text-[10px] text-[var(--color-slate-muted)]">
                  {s.message_count} msgs &middot; {formatRelative(s.updated_at)}
                </p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(s.id);
                }}
                className="ml-1 mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded opacity-0 group-hover:opacity-100 text-[var(--color-slate-muted)] hover:text-[var(--color-slate-accent-rose)] transition-all"
                title="Delete"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          ))
        )}
      </div>

      <div className="border-t border-[var(--color-slate-border)] px-3 py-2" />
    </div>
  );
}
