"use client";

import { useEffect, useState } from "react";
import NarrativeSnapshot from "@/components/dashboard/NarrativeSnapshot";
import DiningLog from "@/components/dashboard/DiningLog";
import ReflectionsPanel from "@/components/dashboard/ReflectionsPanel";
import LearningProgress from "@/components/dashboard/LearningProgress";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type DashboardData = {
  has_data: boolean;
  date_range: { start: string; end: string } | null;
  dining: Array<{
    date: string;
    restaurant: string;
    dishes: string[];
    meal_type: string;
    sentiment: number;
    description: string;
  }>;
  reflections: Array<{
    date: string;
    topic: string;
    content: string;
    is_actionable: boolean;
  }>;
  learning: Array<{
    date: string;
    subject: string;
    milestone: string;
    description: string;
    sentiment: number;
  }>;
};

type NarrativeData = {
  content: string;
  week_start: string;
  week_end: string;
  generated_at: string | null;
  cached: boolean;
};

export default function Dashboard() {
  const [mounted, setMounted] = useState(false);
  const [data, setData] = useState<DashboardData | null>(null);
  const [narrative, setNarrative] = useState<NarrativeData | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [loadingNarrative, setLoadingNarrative] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted) return;
    async function fetchDashboard() {
      try {
        const res = await fetch(`${API}/api/dashboard/data`);
        if (!res.ok) throw new Error("Dashboard data unavailable");
        setData(await res.json());
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unknown error");
      } finally {
        setLoadingData(false);
      }
    }

    async function fetchNarrative() {
      try {
        const res = await fetch(`${API}/api/dashboard/narrative`);
        if (!res.ok) throw new Error("Narrative unavailable");
        setNarrative(await res.json());
      } catch {
        // non-critical
      } finally {
        setLoadingNarrative(false);
      }
    }

    fetchDashboard();
    fetchNarrative();
  }, [mounted]);

  if (!mounted) {
    return <div className="flex-1" />;
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="rounded-xl border border-[var(--color-slate-accent-rose)]/20 bg-[var(--color-slate-surface)] p-8 text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[var(--color-slate-accent-rose)]/15">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--color-slate-accent-rose)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <p className="text-sm font-medium text-[var(--color-slate-accent-rose)]">{error}</p>
          <p className="mt-2 text-xs text-[var(--color-slate-text-dim)]">
            Make sure the backend is running on {API}
          </p>
        </div>
      </div>
    );
  }

  const uniqueDates = data ? new Set([
    ...data.dining.map((d) => d.date),
    ...data.reflections.map((r) => r.date),
    ...data.learning.map((l) => l.date),
  ]).size : 0;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl px-6 py-8">
        {/* Header */}
        <div className="mb-8 flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              Command Center
            </h1>
            {data?.date_range && (
              <p className="mt-1.5 text-xs font-mono text-[var(--color-slate-muted)]">
                {formatRange(data.date_range.start, data.date_range.end)}
              </p>
            )}
          </div>

          {/* Quick stats */}
          {!loadingData && data?.has_data && (
            <div className="flex items-center gap-3">
              <StatPill
                value={uniqueDates}
                label="days"
                color="var(--color-slate-accent)"
              />
              <StatPill
                value={data.dining.length}
                label="meals"
                color="var(--color-slate-accent-amber)"
              />
              <StatPill
                value={data.reflections.length}
                label="insights"
                color="var(--chart-5)"
              />
              <StatPill
                value={data.learning.length}
                label="sessions"
                color="var(--color-slate-accent-green)"
              />
            </div>
          )}
        </div>

        {/* Widget grid */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <NarrativeSnapshot
            content={narrative?.content ?? null}
            weekStart={narrative?.week_start ?? null}
            weekEnd={narrative?.week_end ?? null}
            loading={loadingNarrative}
          />

          <DiningLog items={data?.dining ?? []} loading={loadingData} />
          <ReflectionsPanel items={data?.reflections ?? []} loading={loadingData} />

          <div className="lg:col-span-2">
            <LearningProgress items={data?.learning ?? []} loading={loadingData} />
          </div>
        </div>
      </div>
    </div>
  );
}

function StatPill({ value, label, color }: { value: number; label: string; color: string }) {
  return (
    <div
      className="flex items-center gap-1.5 rounded-lg px-3 py-1.5"
      style={{ backgroundColor: `color-mix(in srgb, ${color} 10%, transparent)` }}
    >
      <span className="text-sm font-bold" style={{ color }}>{value}</span>
      <span className="text-[10px] font-mono text-[var(--color-slate-text-dim)]">{label}</span>
    </div>
  );
}

function formatRange(start: string, end: string): string {
  const s = new Date(start + "T00:00:00");
  const e = new Date(end + "T00:00:00");
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  return `${s.toLocaleDateString("en-US", opts)} \u2014 ${e.toLocaleDateString("en-US", { ...opts, year: "numeric" })}`;
}
