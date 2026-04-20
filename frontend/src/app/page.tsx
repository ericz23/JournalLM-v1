"use client";

import { useEffect, useState } from "react";
import NarrativeSnapshot from "@/components/dashboard/NarrativeSnapshot";
import DiningLog from "@/components/dashboard/DiningLog";
import ReflectionsPanel from "@/components/dashboard/ReflectionsPanel";
import LearningProgress from "@/components/dashboard/LearningProgress";
import {
  API_BASE_URL,
  ApiError,
  type DashboardData,
  type NarrativeData,
  getDashboardData,
  getDashboardNarrative,
} from "@/lib/api";

export default function Dashboard() {
  const [mounted, setMounted] = useState(false);
  const [data, setData] = useState<DashboardData | null>(null);
  const [narrative, setNarrative] = useState<NarrativeData | null>(null);
  const [refDate, setRefDate] = useState<string | null>(null);
  const [latestRefDate, setLatestRefDate] = useState<string | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [loadingNarrative, setLoadingNarrative] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted) return;
    const controller = new AbortController();
    setLoadingData(true);
    setLoadingNarrative(true);
    setError(null);

    async function fetchDashboard() {
      try {
        const dashboard = await getDashboardData(controller.signal, refDate ?? undefined);
        setData(dashboard);
        if (!refDate && dashboard.date_range?.end) {
          setLatestRefDate(dashboard.date_range.end);
        }
      } catch (e) {
        if (controller.signal.aborted) return;
        if (e instanceof ApiError) {
          setError(e.message);
          return;
        }
        setError(e instanceof Error ? e.message : "Unknown error");
      } finally {
        if (!controller.signal.aborted) setLoadingData(false);
      }
    }

    async function fetchNarrative() {
      try {
        setNarrative(await getDashboardNarrative(controller.signal, refDate ?? undefined));
      } catch {
        // non-critical
      } finally {
        if (!controller.signal.aborted) setLoadingNarrative(false);
      }
    }

    fetchDashboard();
    fetchNarrative();

    return () => controller.abort();
  }, [mounted, refDate]);

  if (!mounted) {
    return <div className="flex-1" />;
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="rounded-xl border border-[var(--color-brand-accent-rose)]/20 bg-[var(--color-brand-surface)] p-8 text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[var(--color-brand-accent-rose)]/15">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--color-brand-accent-rose)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <p className="text-sm font-medium text-[var(--color-brand-accent-rose)]">{error}</p>
          <p className="mt-2 text-xs text-[var(--color-brand-text-dim)]">
            Make sure the backend is running on {API_BASE_URL}
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
  const canGoPrev = !!data?.date_range && !loadingData;
  const canGoNext = !!data?.date_range && !!latestRefDate && data.date_range.end < latestRefDate && !loadingData;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl px-6 py-8">
        {/* Header */}
        <div className="mb-8 flex items-end justify-between">
          <div>
            <h1 className="font-heading text-2xl tracking-tight">
              Command Center
            </h1>
            <div className="mt-1.5 flex items-center gap-2">
              {data?.date_range && (
                <p className="text-xs font-mono text-[var(--color-brand-muted)]">
                  {formatRange(data.date_range.start, data.date_range.end)}
                </p>
              )}
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  aria-label="Previous week"
                  disabled={!canGoPrev}
                  onClick={() => {
                    if (!data?.date_range?.end) return;
                    setRefDate(shiftDate(data.date_range.end, -7));
                  }}
                  className="flex h-6 w-6 items-center justify-center rounded border border-[var(--color-brand-border)] text-[var(--color-brand-text-dim)] transition-colors hover:text-[var(--color-brand-text)] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="15 18 9 12 15 6" />
                  </svg>
                </button>
                <button
                  type="button"
                  aria-label="Next week"
                  disabled={!canGoNext}
                  onClick={() => {
                    if (!data?.date_range?.end || !latestRefDate) return;
                    const next = shiftDate(data.date_range.end, 7);
                    setRefDate(next > latestRefDate ? latestRefDate : next);
                  }}
                  className="flex h-6 w-6 items-center justify-center rounded border border-[var(--color-brand-border)] text-[var(--color-brand-text-dim)] transition-colors hover:text-[var(--color-brand-text)] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          {/* Quick stats */}
          {!loadingData && data?.has_data && (
            <div className="flex items-center gap-3">
              <StatPill
                value={uniqueDates}
                label="days"
                color="var(--color-brand-accent)"
              />
              <StatPill
                value={data.dining.length}
                label="meals"
                color="var(--color-brand-accent-amber)"
              />
              <StatPill
                value={data.reflections.length}
                label="insights"
                color="var(--chart-5)"
              />
              <StatPill
                value={data.learning.length}
                label="sessions"
                color="var(--color-brand-accent-green)"
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
      <span className="text-[10px] font-mono text-[var(--color-brand-text-dim)]">{label}</span>
    </div>
  );
}

function formatRange(start: string, end: string): string {
  const s = new Date(start + "T00:00:00");
  const e = new Date(end + "T00:00:00");
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  return `${s.toLocaleDateString("en-US", opts)} \u2014 ${e.toLocaleDateString("en-US", { ...opts, year: "numeric" })}`;
}

function shiftDate(isoDate: string, deltaDays: number): string {
  const d = new Date(isoDate + "T00:00:00");
  d.setDate(d.getDate() + deltaDays);
  return d.toISOString().slice(0, 10);
}
