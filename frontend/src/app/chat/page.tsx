"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ChatInput from "@/components/chat/ChatInput";
import ConfirmDialog from "@/components/chat/ConfirmDialog";
import ContextPanel, { type ContextItem } from "@/components/chat/ContextPanel";
import MessageBubble from "@/components/chat/MessageBubble";
import SessionSidebar, { type Session } from "@/components/chat/SessionSidebar";
import {
  createChatSession,
  deleteChatSession,
  getChatSession,
  listChatSessions,
  postChatMessageStream,
  saveTempSession as apiSaveTempSession,
} from "@/lib/api";
import { getModeById } from "@/lib/chat-modes";

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
  const [contextCollapsed, setContextCollapsed] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [mode, setMode] = useState("default");
  const [tempSessionId, setTempSessionId] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const tempIdRef = useRef<string | null>(null);

  useEffect(() => {
    tempIdRef.current = tempSessionId;
  }, [tempSessionId]);

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

  const clearChat = useCallback(() => {
    setActiveId(null);
    setMessages([]);
    setContextItems([]);
  }, []);

  const discardTempSession = useCallback(async () => {
    const tid = tempIdRef.current;
    if (!tid) return;
    setTempSessionId(null);
    try {
      await deleteChatSession(tid);
    } catch { /* best effort */ }
  }, []);

  // Guard: if a temp session with messages exists, show confirm before proceeding
  const withTempGuard = useCallback(
    (action: () => void) => {
      if (tempSessionId && activeId === tempSessionId && messages.length > 0) {
        setPendingAction(() => action);
      } else {
        if (tempSessionId && activeId !== tempSessionId) {
          discardTempSession();
        }
        action();
      }
    },
    [tempSessionId, activeId, messages.length, discardTempSession]
  );

  const handleConfirm = useCallback(async () => {
    const action = pendingAction;
    setPendingAction(null);
    await discardTempSession();
    if (action) action();
  }, [pendingAction, discardTempSession]);

  const handleCancelConfirm = useCallback(() => {
    setPendingAction(null);
  }, []);

  const loadSession = useCallback(
    (id: string) => {
      if (id === tempSessionId) {
        setActiveId(id);
        return;
      }
      withTempGuard(async () => {
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
      });
    },
    [withTempGuard, tempSessionId]
  );

  const createSession = useCallback(() => {
    withTempGuard(async () => {
      try {
        const session = await createChatSession();
        setActiveId(session.id);
        setMessages([]);
        setContextItems([]);
        await loadSessions();
      } catch { /* ignore */ }
    });
  }, [withTempGuard, loadSessions]);

  const createTempSession = useCallback(() => {
    withTempGuard(async () => {
      try {
        const session = await createChatSession(null, true);
        setTempSessionId(session.id);
        setActiveId(session.id);
        setMessages([]);
        setContextItems([]);
      } catch { /* ignore */ }
    });
  }, [withTempGuard]);

  const saveTempChat = useCallback(async () => {
    if (!tempSessionId) return;
    try {
      await apiSaveTempSession(tempSessionId);
      setTempSessionId(null);
      await loadSessions();
    } catch { /* ignore */ }
  }, [tempSessionId, loadSessions]);

  const deleteSession = useCallback(
    async (id: string) => {
      try {
        await deleteChatSession(id);
        if (id === tempSessionId) {
          setTempSessionId(null);
        }
        if (activeId === id) {
          clearChat();
        }
        await loadSessions();
      } catch { /* ignore */ }
    },
    [activeId, tempSessionId, loadSessions, clearChat]
  );

  // Cleanup temp session on page unload
  useEffect(() => {
    const handleBeforeUnload = () => {
      const tid = tempIdRef.current;
      if (tid) {
        navigator.sendBeacon(`/api/chat/sessions/${tid}`, "");
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, []);

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
        const reader = await postChatMessageStream(sessionId, content, mode);
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
        if (!tempIdRef.current || activeId !== tempIdRef.current) {
          await loadSessions();
        }
      }
    },
    [activeId, loadSessions, mode]
  );

  // ── Render ────────────────────────────────────────────────────

  if (!mounted) {
    return <div className="flex flex-1" />;
  }

  const activeMode = getModeById(mode);

  return (
    <div
      className="flex flex-1 overflow-hidden bg-[var(--color-brand-bg)]"
      style={{ "--color-brand-accent": activeMode.accentColor } as React.CSSProperties}
    >
      <SessionSidebar
        sessions={sessions}
        activeId={activeId}
        tempSessionId={tempSessionId}
        onSelect={loadSession}
        onNew={createSession}
        onNewTemp={createTempSession}
        onSaveTemp={saveTempChat}
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
                <div
                  className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-64 w-64 rounded-full blur-3xl transition-colors"
                  style={{ backgroundColor: `${activeMode.accentColor}10` }}
                />

                <div
                  className="relative mb-2 inline-flex h-14 w-14 items-center justify-center rounded-2xl ring-1 transition-colors"
                  style={{
                    background: `linear-gradient(to bottom right, ${activeMode.accentColor}33, ${activeMode.accentColor}0D)`,
                    outlineColor: `${activeMode.accentColor}33`,
                    ["--tw-ring-color" as string]: `${activeMode.accentColor}33`,
                  }}
                >
                  <span className="text-2xl leading-none">{activeMode.icon}</span>
                </div>

                <p className="relative font-heading text-2xl tracking-tight">
                  Journal<span style={{ color: activeMode.accentColor }}>LM</span>
                  <span className="ml-1.5 font-sans text-xs font-normal text-[var(--color-brand-muted)] align-middle">{activeMode.label}</span>
                </p>
                <p className="relative mt-2 text-sm text-[var(--color-brand-text-dim)] max-w-md mx-auto leading-relaxed">
                  {activeMode.description}
                </p>
                <div className="relative mt-8 grid grid-cols-2 gap-2.5 max-w-lg mx-auto">
                  {activeMode.starterPrompts.map(({ query, icon, label }) => (
                    <button
                      key={query}
                      onClick={() => sendMessage(query)}
                      disabled={streaming}
                      className="group flex items-start gap-3 rounded-xl border border-[var(--color-brand-border)] bg-[var(--color-brand-surface)] p-3.5 text-left transition-all hover:bg-opacity-[0.04] hover:shadow-[0_0_20px_-4px] disabled:opacity-50"
                      style={{
                        ["--hover-accent" as string]: activeMode.accentColor,
                      }}
                    >
                      <span className="mt-0.5 text-lg leading-none">{icon}</span>
                      <div className="min-w-0 flex-1">
                        <span
                          className="block text-[10px] font-semibold uppercase tracking-wider mb-0.5"
                          style={{ color: activeMode.accentColor }}
                        >
                          {label}
                        </span>
                        <span className="block text-xs text-[var(--color-brand-text-dim)] group-hover:text-[var(--color-brand-text)] transition-colors leading-relaxed">
                          {query}
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
                  accentColor={activeMode.accentColor}
                />
              ))}
            </div>
          )}
        </div>

        <ChatInput
          onSend={sendMessage}
          disabled={streaming}
          mode={mode}
          onModeChange={setMode}
        />
      </div>

      <ContextPanel
        items={contextItems}
        collapsed={contextCollapsed}
        onToggle={() => setContextCollapsed(!contextCollapsed)}
      />

      <ConfirmDialog
        open={pendingAction !== null}
        title="Discard temporary chat?"
        message="Your temporary chat will be lost. This action cannot be undone."
        confirmLabel="Discard"
        onConfirm={handleConfirm}
        onCancel={handleCancelConfirm}
      />
    </div>
  );
}
