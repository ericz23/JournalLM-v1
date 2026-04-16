"use client";

import { cn } from "@/lib/utils";

export type Session = {
  id: string;
  title: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
};

type Props = {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
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
  onSelect,
  onNew,
  onDelete,
}: Props) {
  return (
    <div className="flex h-full w-[240px] flex-col border-r border-[var(--color-slate-border)] bg-[var(--color-slate-bg)]/80">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--color-slate-border)] px-3 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-slate-text-dim)]">
          Chats
        </h2>
        <button
          onClick={onNew}
          className="flex h-6 w-6 items-center justify-center rounded-lg bg-[var(--color-slate-accent)] text-[var(--color-slate-bg)] text-sm font-bold hover:opacity-90 hover:shadow-[0_0_8px_-2px] hover:shadow-[var(--color-slate-accent)]/40 transition-all"
          title="New chat"
        >
          +
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto py-1">
        {sessions.length === 0 ? (
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
