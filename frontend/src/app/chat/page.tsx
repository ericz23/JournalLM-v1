"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ChatInput from "@/components/chat/ChatInput";
import ContextPanel, { type ContextItem } from "@/components/chat/ContextPanel";
import MessageBubble from "@/components/chat/MessageBubble";
import SessionSidebar, { type Session } from "@/components/chat/SessionSidebar";
import {
  createChatSession,
  deleteChatSession,
  getChatSession,
  listChatSessions,
  postChatMessageStream,
} from "@/lib/api";

type Message = {
  id?: number;
  role: "user" | "assistant";
  content: string;
  context?: ContextItem[];
};

export default function ChatPage() {
  const [mounted, setMounted] = useState(false);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [contextItems, setContextItems] = useState<ContextItem[]>([]);
  const [contextCollapsed, setContextCollapsed] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => setMounted(true), []);

  const scrollToBottom = () => {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth",
      });
    });
  };

  // ── Session management ──────────────────────────────────────────

  const loadSessions = useCallback(async () => {
    try {
      const sessions = await listChatSessions();
      setSessions(sessions);
    } catch { /* backend may be offline */ }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const loadSession = useCallback(async (id: string) => {
    try {
      const data = await getChatSession(id);
      setActiveId(id);
      const msgs: Message[] = data.messages.map((m) => ({
        id: m.id,
        role: m.role as "user" | "assistant",
        content: m.content,
        context: m.retrieved_context as ContextItem[] | undefined,
      }));
      setMessages(msgs);

      const lastAssistant = [...msgs].reverse().find((m) => m.role === "assistant");
      setContextItems(lastAssistant?.context ?? []);
    } catch { /* ignore */ }
  }, []);

  const createSession = useCallback(async () => {
    try {
      const session = await createChatSession();
      setActiveId(session.id);
      setMessages([]);
      setContextItems([]);
      await loadSessions();
    } catch { /* ignore */ }
  }, [loadSessions]);

  const deleteSession = useCallback(
    async (id: string) => {
      try {
        await deleteChatSession(id);
        if (activeId === id) {
          setActiveId(null);
          setMessages([]);
          setContextItems([]);
        }
        await loadSessions();
      } catch { /* ignore */ }
    },
    [activeId, loadSessions]
  );

  // ── Send message (SSE) ────────────────────────────────────────

  const sendMessage = useCallback(
    async (content: string) => {
      let sessionId = activeId;

      if (!sessionId) {
        try {
          const session = await createChatSession();
          sessionId = session.id;
          setActiveId(sessionId);
        } catch {
          return;
        }
      }

      const userMsg: Message = { role: "user", content };
      setMessages((prev) => [...prev, userMsg]);
      scrollToBottom();

      setStreaming(true);
      const assistantMsg: Message = { role: "assistant", content: "" };
      setMessages((prev) => [...prev, assistantMsg]);

      try {
        const reader = await postChatMessageStream(sessionId, content);
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";

          for (const part of parts) {
            const lines = part.trim().split("\n");
            let eventType = "";
            let data = "";

            for (const line of lines) {
              if (line.startsWith("event: ")) eventType = line.slice(7);
              else if (line.startsWith("data: ")) data = line.slice(6);
            }

            if (eventType === "token" && data) {
              try {
                const { text } = JSON.parse(data);
                setMessages((prev) => {
                  const copy = [...prev];
                  const last = copy[copy.length - 1];
                  copy[copy.length - 1] = {
                    ...last,
                    content: last.content + text,
                  };
                  return copy;
                });
                scrollToBottom();
              } catch { /* skip malformed */ }
            } else if (eventType === "context" && data) {
              try {
                const { items } = JSON.parse(data);
                setContextItems(items);
                setMessages((prev) => {
                  const copy = [...prev];
                  copy[copy.length - 1] = {
                    ...copy[copy.length - 1],
                    context: items,
                  };
                  return copy;
                });
              } catch { /* skip */ }
            } else if (eventType === "done" && data) {
              try {
                const { message_id } = JSON.parse(data);
                setMessages((prev) => {
                  const copy = [...prev];
                  copy[copy.length - 1] = {
                    ...copy[copy.length - 1],
                    id: message_id,
                  };
                  return copy;
                });
              } catch { /* skip */ }
            }
          }
        }
      } catch {
        setMessages((prev) => {
          const copy = [...prev];
          copy[copy.length - 1] = {
            ...copy[copy.length - 1],
            content:
              copy[copy.length - 1].content ||
              "Connection lost. Please try again.",
          };
          return copy;
        });
      } finally {
        setStreaming(false);
        await loadSessions();
      }
    },
    [activeId, loadSessions]
  );

  // ── Render ────────────────────────────────────────────────────

  if (!mounted) {
    return <div className="flex flex-1" />;
  }

  return (
    <div className="flex flex-1 overflow-hidden bg-[var(--color-slate-bg)]">
      <SessionSidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={loadSession}
        onNew={createSession}
        onDelete={deleteSession}
      />

      {/* Chat thread */}
      <div className="flex flex-1 flex-col min-w-0">

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-5">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center">
              <div className="relative text-center">
                {/* Radial glow */}
                <div className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-64 w-64 rounded-full bg-[var(--color-slate-accent)]/[0.06] blur-3xl" />

                <div className="relative mb-2 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[var(--color-slate-accent)]/20 to-[var(--color-slate-accent)]/5 ring-1 ring-[var(--color-slate-accent)]/20">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--color-slate-accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    <path d="M8 10h.01" />
                    <path d="M12 10h.01" />
                    <path d="M16 10h.01" />
                  </svg>
                </div>

                <p className="relative text-2xl font-bold tracking-tight">
                  Journal<span className="text-[var(--color-slate-accent)]">LM</span>
                  <span className="ml-1.5 text-xs font-normal text-[var(--color-slate-muted)] align-middle">Assistant</span>
                </p>
                <p className="relative mt-2 text-sm text-[var(--color-slate-text-dim)] max-w-md mx-auto leading-relaxed">
                  Ask me anything about your journal entries. I can recall events,
                  summarize weeks, find restaurants, and surface reflections &mdash;
                  all grounded in your actual data.
                </p>
                <div className="relative mt-8 grid grid-cols-2 gap-2.5 max-w-lg mx-auto">
                  {[
                    { q: "What did I do on October 3rd?", icon: "\uD83D\uDCC5", label: "Recall a day" },
                    { q: "Which restaurants have I visited?", icon: "\uD83C\uDF7D\uFE0F", label: "Find restaurants" },
                    { q: "Summarize my week of Oct 1-7", icon: "\uD83D\uDCCA", label: "Weekly summary" },
                    { q: "How was I feeling about work?", icon: "\uD83D\uDCAD", label: "Explore feelings" },
                  ].map(({ q, icon, label }) => (
                    <button
                      key={q}
                      onClick={() => sendMessage(q)}
                      disabled={streaming}
                      className="group flex items-start gap-3 rounded-xl border border-[var(--color-slate-border)] bg-[var(--color-slate-surface)] p-3.5 text-left transition-all hover:border-[var(--color-slate-accent)]/40 hover:bg-[var(--color-slate-accent)]/[0.04] hover:shadow-[0_0_20px_-4px] hover:shadow-[var(--color-slate-accent)]/10 disabled:opacity-50"
                    >
                      <span className="mt-0.5 text-lg leading-none">{icon}</span>
                      <div className="min-w-0 flex-1">
                        <span className="block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-slate-accent)] mb-0.5">
                          {label}
                        </span>
                        <span className="block text-xs text-[var(--color-slate-text-dim)] group-hover:text-[var(--color-slate-text)] transition-colors leading-relaxed">
                          {q}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto py-4">
              {messages.map((msg, i) => (
                <MessageBubble
                  key={i}
                  role={msg.role}
                  content={msg.content}
                  isStreaming={streaming && i === messages.length - 1 && msg.role === "assistant"}
                />
              ))}
            </div>
          )}
        </div>

        <ChatInput onSend={sendMessage} disabled={streaming} />
      </div>

      <ContextPanel
        items={contextItems}
        collapsed={contextCollapsed}
        onToggle={() => setContextCollapsed(!contextCollapsed)}
      />
    </div>
  );
}
