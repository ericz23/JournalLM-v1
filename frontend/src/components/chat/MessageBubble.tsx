"use client";

import { cn } from "@/lib/utils";

type Props = {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
};

function renderMarkdown(text: string) {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let inList = false;
  let listItems: React.ReactNode[] = [];

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`list-${elements.length}`} className="list-disc pl-5 space-y-1 my-1.5">
          {listItems}
        </ul>
      );
      listItems = [];
      inList = false;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      inList = true;
      listItems.push(
        <li key={`li-${i}`}>
          <InlineFormatted text={trimmed.slice(2)} />
        </li>
      );
      continue;
    }

    flushList();

    if (trimmed === "") {
      elements.push(<div key={`br-${i}`} className="h-2" />);
    } else {
      elements.push(
        <p key={`p-${i}`} className="leading-relaxed">
          <InlineFormatted text={trimmed} />
        </p>
      );
    }
  }
  flushList();

  return elements;
}

function InlineFormatted({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={i} className="font-semibold text-foreground">
            {part.slice(2, -2)}
          </strong>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  );
}

export default function MessageBubble({ role, content, isStreaming }: Props) {
  const isUser = role === "user";

  return (
    <div className={cn("flex gap-3 py-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-[var(--color-slate-accent)] to-[var(--color-slate-accent)]/70 text-[var(--color-slate-bg)] shadow-[0_0_10px_-2px] shadow-[var(--color-slate-accent)]/30">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
        </div>
      )}
      <div
        className={cn(
          "max-w-[85%] rounded-xl px-4 py-3 text-sm",
          isUser
            ? "bg-[var(--color-slate-accent)] text-[var(--color-slate-bg)] shadow-[0_2px_12px_-4px] shadow-[var(--color-slate-accent)]/30"
            : "bg-[var(--color-slate-surface)] text-[var(--color-slate-text)] border border-[var(--color-slate-border)]/60"
        )}
      >
        {content ? (
          <div className="space-y-1">{renderMarkdown(content)}</div>
        ) : isStreaming ? (
          <span className="inline-block h-4 w-1.5 animate-pulse bg-[var(--color-slate-accent)]" />
        ) : null}
      </div>
    </div>
  );
}
