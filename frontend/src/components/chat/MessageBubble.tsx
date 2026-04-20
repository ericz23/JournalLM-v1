"use client";

import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Props = {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  accentColor?: string;
};

export default function MessageBubble({ role, content, isStreaming, accentColor }: Props) {
  const isUser = role === "user";
  const accent = accentColor ?? "var(--color-brand-accent)";

  return (
    <div className={cn("flex gap-3 py-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div
          className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[var(--color-brand-bg)]"
          style={{
            background: `linear-gradient(to bottom right, ${accent}, ${accent}B3)`,
            boxShadow: `0 0 10px -2px ${accent}4D`,
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
        </div>
      )}
      <div
        className={cn(
          "max-w-[85%] rounded-xl px-4 py-3 text-sm",
          isUser
            ? "text-[var(--color-brand-bg)]"
            : "bg-[var(--color-brand-surface)] text-[var(--color-brand-text)] border border-[var(--color-brand-border)]/60"
        )}
        style={isUser ? {
          backgroundColor: accent,
          boxShadow: `0 2px 12px -4px ${accent}4D`,
        } : undefined}
      >
        {content ? (
          <div className="space-y-1">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => <p className="leading-relaxed">{children}</p>,
                ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
                ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
                li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                h1: ({ children }) => <h1 className="my-2 text-lg font-semibold">{children}</h1>,
                h2: ({ children }) => <h2 className="my-2 text-base font-semibold">{children}</h2>,
                h3: ({ children }) => <h3 className="my-2 text-sm font-semibold">{children}</h3>,
                blockquote: ({ children }) => (
                  <blockquote className="my-2 border-l-2 border-[var(--color-brand-accent)] pl-3 font-heading italic opacity-90">
                    {children}
                  </blockquote>
                ),
                code: ({ className, children }) => {
                  const isBlock = !!className;
                  if (isBlock) {
                    return (
                      <code className="block overflow-x-auto rounded-md bg-[var(--color-brand-bg)] px-3 py-2 font-mono text-xs">
                        {children}
                      </code>
                    );
                  }
                  return (
                    <code className="rounded bg-[var(--color-brand-bg)] px-1.5 py-0.5 font-mono text-[0.85em]">
                      {children}
                    </code>
                  );
                },
                pre: ({ children }) => <pre className="my-2">{children}</pre>,
                a: ({ href, children }) => (
                  <a
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    className="underline underline-offset-2"
                  >
                    {children}
                  </a>
                ),
                table: ({ children }) => (
                  <div className="my-2 overflow-x-auto">
                    <table className="w-full border-collapse text-left text-xs">{children}</table>
                  </div>
                ),
                th: ({ children }) => (
                  <th className="border border-[var(--color-brand-border)] bg-[var(--color-brand-bg)] px-2 py-1 font-semibold">
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td className="border border-[var(--color-brand-border)] px-2 py-1">{children}</td>
                ),
              }}
            >
              {content}
            </ReactMarkdown>
          </div>
        ) : isStreaming ? (
          <span className="inline-block h-4 w-1.5 animate-pulse" style={{ backgroundColor: accent }} />
        ) : null}
      </div>
    </div>
  );
}
