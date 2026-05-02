"use client";

import { useEffect, useState } from "react";
import NarrativeSnapshot from "@/components/dashboard/NarrativeSnapshot";
import DiningLog from "@/components/dashboard/DiningLog";
import ReflectionsPanel from "@/components/dashboard/ReflectionsPanel";
import LearningProgress from "@/components/dashboard/LearningProgress";
import InnerCircleWidget from "@/components/dashboard/InnerCircleWidget";
import ActiveProjectsWidget from "@/components/dashboard/ActiveProjectsWidget";
import {
  API_BASE_URL,
  ApiError,
  type DashboardPayload,
  type NarrativeData,
  getDashboardData,
  getDashboardNarrative,
} from "@/lib/api";

export default function Dashboard() {
  const [mounted, setMounted] = useState(false);
  const [data, setData] = useState<DashboardPayload | null>(null);
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
        if (!refDate && dashboard.window?.end) {
          setLatestRefDate(dashboard.window.end);
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
        // non-critical — narrative is supplementary
      } finally {
        if (!controller.signal.aborted) setLoadingNarrative(false);
      }
    }

    fetchDashboard();
    fetchNarrative();

    return () => controller.abort();
  }, [mounted, refDate]);

  if (!mounted) return <div className="flex-1" />;

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

  // ── Stat counts ────────────────────────────────────────────────────
  const windowEnd = data?.window?.end ?? null;
  const windowStart = data?.window?.start ?? null;

  const uniqueDates = data
    ? new Set([
        ...data.dining.map((d) => d.date),
        ...data.reflections.map((r) => r.date),
        ...data.learning.map((l) => l.date),
        ...data.inner_circle.map((p) => p.last_mention_date),
        ...data.active_projects.map((p) => p.last_event_date),
      ]).size
    : 0;

  // ── Navigation guards ──────────────────────────────────────────────
  const canGoPrev = !!windowEnd && !loadingData;
  const canGoNext =
    !!windowEnd && !!latestRefDate && windowEnd < latestRefDate && !loadingData;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-6xl px-6 py-8">
        {/* Header */}
        <div className="mb-8 flex items-end justify-between">
          <div>
            <h1 className="font-heading text-2xl tracking-tight">Command Center</h1>
            <div className="mt-1.5 flex items-center gap-2">
              {windowStart && windowEnd && (
                <p className="text-xs font-mono text-[var(--color-brand-muted)]">
                  {formatRange(windowStart, windowEnd)}
                </p>
              )}
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  aria-label="Previous week"
                  disabled={!canGoPrev}
                  onClick={() => {
                    if (!windowEnd) return;
                    setRefDate(shiftDate(windowEnd, -7));
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
                    if (!windowEnd || !latestRefDate) return;
                    const next = shiftDate(windowEnd, 7);
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

          {/* Stat pills */}
          {!loadingData && data?.has_data && (
            <div className="flex flex-wrap items-center gap-3">
              <StatPill value={uniqueDates} label="days" color="var(--color-brand-accent)" />
              <StatPill value={data.dining.length} label="meals" color="var(--color-brand-accent-amber)" />
              <StatPill value={data.reflections.length} label="insights" color="var(--chart-5)" />
              <StatPill value={data.learning.length} label="sessions" color="var(--color-brand-accent-green)" />
              <StatPill value={data.inner_circle_total} label="people" color="var(--chart-3)" />
              <StatPill value={data.active_projects_total} label="projects" color="var(--chart-4)" />
            </div>
          )}
        </div>

        {/* ── Widget grid (Q5 fixed layout) ── */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          {/* 1. Narrative — full width */}
          <div className="lg:col-span-2">
            <NarrativeSnapshot
              content={narrative?.content ?? null}
              windowStart={narrative?.window_start ?? null}
              windowEnd={narrative?.window_end ?? null}
              cached={narrative?.cached}
              loading={loadingNarrative}
            />
          </div>

          {/* 2. Inner Circle + Active Projects */}
          <InnerCircleWidget
            people={data?.inner_circle ?? []}
            total={data?.inner_circle_total ?? 0}
            insight={data?.inner_circle_insight ?? null}
            loading={loadingData}
          />
          <ActiveProjectsWidget
            projects={data?.active_projects ?? []}
            total={data?.active_projects_total ?? 0}
            insight={data?.active_projects_insight ?? null}
            loading={loadingData}
          />

          {/* 3. Dining + Reflections */}
          <DiningLog items={data?.dining ?? []} loading={loadingData} />
          <ReflectionsPanel items={data?.reflections ?? []} loading={loadingData} />

          {/* 4. Learning — full width */}
          <div className="lg:col-span-2">
            <LearningProgress
              items={data?.learning ?? []}
              bySubject={data?.learning_by_subject ?? []}
              loading={loadingData}
            />
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
      <span className="text-sm font-bold" style={{ color }}>
        {value}
      </span>
      <span className="text-[10px] font-mono text-[var(--color-brand-text-dim)]">{label}</span>
    </div>
  );
}

function formatRange(start: string, end: string): string {
  const s = new Date(start + "T00:00:00");
  const e = new Date(end + "T00:00:00");
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  return `${s.toLocaleDateString("en-US", opts)} \u2014 ${e.toLocaleDateString("en-US", {
    ...opts,
    year: "numeric",
  })}`;
}

function shiftDate(isoDate: string, deltaDays: number): string {
  const d = new Date(isoDate + "T00:00:00");
  d.setDate(d.getDate() + deltaDays);
  return d.toISOString().slice(0, 10);
}
