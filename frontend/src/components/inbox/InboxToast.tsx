"use client";

import { useEffect, useState } from "react";

export type ToastVariant = "success" | "error" | "info";

export type ToastInput = {
  variant: ToastVariant;
  title: string;
  description?: string;
  warnings?: string[];
};

type Props = ToastInput & {
  onClose: () => void;
};

const VARIANT_STYLES: Record<ToastVariant, { border: string; iconBg: string; iconColor: string; iconPath: React.ReactNode }> = {
  success: {
    border: "var(--color-brand-accent-green)",
    iconBg: "rgba(74, 222, 128, 0.15)",
    iconColor: "var(--color-brand-accent-green)",
    iconPath: <polyline points="20 6 9 17 4 12" />,
  },
  error: {
    border: "var(--color-brand-accent-rose)",
    iconBg: "rgba(248, 113, 113, 0.15)",
    iconColor: "var(--color-brand-accent-rose)",
    iconPath: (
      <>
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </>
    ),
  },
  info: {
    border: "var(--color-brand-accent)",
    iconBg: "rgba(240, 180, 41, 0.15)",
    iconColor: "var(--color-brand-accent)",
    iconPath: (
      <>
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </>
    ),
  },
};

export default function InboxToast({ variant, title, description, warnings, onClose }: Props) {
  const [showWarnings, setShowWarnings] = useState(false);
  const style = VARIANT_STYLES[variant];

  useEffect(() => {
    const t = setTimeout(onClose, 5000);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <div
      role="status"
      className="pointer-events-auto w-[360px] rounded-xl border bg-[var(--color-brand-surface)] p-4 shadow-2xl shadow-black/40"
      style={{ borderColor: style.border }}
    >
      <div className="flex items-start gap-3">
        <div
          className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
          style={{ backgroundColor: style.iconBg }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={style.iconColor} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            {style.iconPath}
          </svg>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-[var(--color-brand-text)]">{title}</p>
          {description && (
            <p className="mt-1 text-[11px] leading-relaxed text-[var(--color-brand-text-dim)]">
              {description}
            </p>
          )}
          {warnings && warnings.length > 0 && (
            <button
              type="button"
              onClick={() => setShowWarnings((v) => !v)}
              className="mt-2 text-[10px] font-medium text-[var(--color-brand-accent)] hover:underline"
            >
              {showWarnings ? "Hide warnings" : `Show ${warnings.length} warning${warnings.length === 1 ? "" : "s"}`}
            </button>
          )}
          {showWarnings && warnings && (
            <ul className="mt-1.5 list-disc space-y-1 pl-4 text-[10px] text-[var(--color-brand-muted)]">
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 rounded p-1 text-[var(--color-brand-muted)] hover:text-[var(--color-brand-text)]"
          aria-label="Dismiss"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
    </div>
  );
}
