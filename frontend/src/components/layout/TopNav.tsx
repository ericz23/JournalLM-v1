"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  getCachedInboxSummary,
  type InboxSummary,
} from "@/lib/inbox-api";
import InboxBadge from "@/components/inbox/InboxBadge";

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
    href: "/inbox",
    label: "Inbox",
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
        <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
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
  const [summary, setSummary] = useState<InboxSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    const ctl = new AbortController();
    getCachedInboxSummary(ctl.signal)
      .then((s) => {
        if (!cancelled) setSummary(s);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      ctl.abort();
    };
  }, [pathname]);

  return (
    <nav className="flex items-center gap-1 border-b border-[var(--color-brand-border)] bg-[var(--color-brand-bg)] px-6 py-2.5">
      <Link href="/" className="mr-8 flex items-center gap-2.5">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--color-brand-accent)] text-[var(--color-brand-bg)]">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
            <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
          </svg>
        </div>
        <span className="font-heading text-base tracking-tight text-[var(--color-brand-accent)]">
          JournalLM
        </span>
      </Link>

      <div className="flex items-center gap-4">
        {NAV_ITEMS.map(({ href, label, icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          const showBadge = href === "/inbox" && summary !== null;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-1.5 border-b-[1.5px] px-1 pb-2.5 pt-3 text-xs font-medium transition-colors ${
                active
                  ? "border-[var(--color-brand-accent)] text-[var(--color-brand-text)]"
                  : "border-transparent text-[var(--color-brand-text-dim)] hover:text-[var(--color-brand-text)]"
              }`}
            >
              {icon}
              {label}
              {showBadge && summary && <InboxBadge count={summary.total_pending} />}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
