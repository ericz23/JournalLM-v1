"use client";

import { useEffect, useRef, useState } from "react";
import { CHAT_MODES, getModeById } from "@/lib/chat-modes";

type Props = {
  mode: string;
  onModeChange: (modeId: string) => void;
};

export default function ModeSelector({ mode, onModeChange }: Props) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const active = getModeById(mode);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors hover:bg-[var(--color-slate-surface)]"
        style={{ color: active.accentColor }}
      >
        <span className="text-sm leading-none">{active.icon}</span>
        <span>{active.label}</span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`transition-transform ${open ? "rotate-180" : ""}`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <div className="absolute bottom-full left-0 mb-1 w-56 rounded-xl border border-[var(--color-slate-border)] bg-[var(--color-slate-surface)] p-1.5 shadow-xl shadow-black/30 z-50">
          {CHAT_MODES.map((m) => {
            const isActive = m.id === mode;
            return (
              <button
                key={m.id}
                type="button"
                onClick={() => {
                  onModeChange(m.id);
                  setOpen(false);
                }}
                className={`flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
                  isActive
                    ? "bg-[var(--color-slate-bg)]"
                    : "hover:bg-[var(--color-slate-bg)]/60"
                }`}
              >
                <span className="mt-0.5 text-base leading-none">{m.icon}</span>
                <div className="min-w-0 flex-1">
                  <span
                    className="block text-sm font-semibold"
                    style={{ color: isActive ? m.accentColor : "var(--color-slate-text)" }}
                  >
                    {m.label}
                  </span>
                  <span className="block text-[11px] text-[var(--color-slate-text-dim)] leading-snug">
                    {m.description}
                  </span>
                </div>
                {isActive && (
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke={m.accentColor}
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="mt-1 shrink-0"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
