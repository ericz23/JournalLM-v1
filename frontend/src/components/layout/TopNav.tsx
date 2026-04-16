"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  {
    href: "/",
    label: "Dashboard",
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </svg>
    ),
  },
  {
    href: "/chat",
    label: "Chat",
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
] as const;

export default function TopNav() {
  const pathname = usePathname();

  return (
    <nav className="relative flex items-center gap-1 border-b border-[var(--color-slate-border)] bg-[var(--color-slate-bg)] px-6 py-3">
      {/* Subtle bottom glow */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-[var(--color-slate-accent)]/30 to-transparent" />

      <Link href="/" className="mr-8 flex items-center gap-2.5">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--color-slate-accent)] text-[var(--color-slate-bg)]">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
            <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
          </svg>
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-base font-bold tracking-tight">
            Journal<span className="text-[var(--color-slate-accent)]">LM</span>
          </span>
          <span className="hidden sm:inline text-[10px] font-mono uppercase tracking-widest text-[var(--color-slate-muted)]">
            Slate Intelligence
          </span>
        </div>
      </Link>

      <div className="flex items-center gap-0.5">
        {NAV_ITEMS.map(({ href, label, icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-xs font-medium transition-all ${
                active
                  ? "bg-[var(--color-slate-accent)]/10 text-[var(--color-slate-accent)] shadow-[inset_0_0_0_1px] shadow-[var(--color-slate-accent)]/20"
                  : "text-[var(--color-slate-text-dim)] hover:text-[var(--color-slate-text)] hover:bg-[var(--color-slate-surface)]"
              }`}
            >
              {icon}
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
