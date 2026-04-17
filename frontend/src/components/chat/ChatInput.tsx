"use client";

import { useRef, useState } from "react";
import ModeSelector from "@/components/chat/ModeSelector";
import { getModeById } from "@/lib/chat-modes";

type Props = {
  onSend: (message: string) => void;
  disabled?: boolean;
  mode: string;
  onModeChange: (modeId: string) => void;
};

export default function ChatInput({ onSend, disabled, mode, onModeChange }: Props) {
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const activeMode = getModeById(mode);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
    }
  };

  return (
    <div className="border-t border-[var(--color-slate-border)] bg-[var(--color-slate-bg)] px-4 py-4">
      <div
        className={`relative flex flex-col rounded-xl border bg-[var(--color-slate-surface)] px-4 py-3 transition-all ${
          focused
            ? "border-[var(--color-slate-accent)]/40 shadow-[0_0_16px_-4px] shadow-[var(--color-slate-accent)]/20"
            : "border-[var(--color-slate-border)]"
        }`}
      >
        <div className="flex items-end gap-3">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onInput={handleInput}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder="Ask about your journal..."
            disabled={disabled}
            rows={1}
            className="flex-1 resize-none bg-transparent text-sm text-[var(--color-slate-text)] placeholder:text-[var(--color-slate-muted)] focus:outline-none disabled:opacity-50"
          />
          <button
            onClick={handleSubmit}
            disabled={disabled || !value.trim()}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[var(--color-slate-bg)] transition-all hover:opacity-90 hover:shadow-[0_0_12px_-2px] disabled:opacity-20 disabled:shadow-none"
            style={{ backgroundColor: activeMode.accentColor }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
        <div className="mt-2 border-t border-[var(--color-slate-border)]/50 pt-2">
          <ModeSelector mode={mode} onModeChange={onModeChange} />
        </div>
      </div>
      <p className="mt-2 text-center text-[10px] text-[var(--color-slate-muted)]">
        {activeMode.disclaimer ?? "Grounded in your journal data."}{" "}
        Shift+Enter for new line.
      </p>
    </div>
  );
}
