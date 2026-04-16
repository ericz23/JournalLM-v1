"""Sync Whoop physiological data into the health_metrics table.

Fetches Recovery, Cycle, and Sleep data for a date range, aggregates
per-day, and upserts into health_metrics on the shared date axis.
"""

from __future__ import annotations

import datetime
import json
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health_metric import HealthMetric
from app.services.whoop_client import fetch_collection

logger = logging.getLogger(__name__)

KJ_TO_KCAL = 0.239006
MS_TO_MINUTES = 1 / 60_000


def _cycle_start_to_date(cycle: dict) -> datetime.date | None:
    """Derive the calendar date from a cycle's start + timezone_offset."""
    raw = cycle.get("start")
    if not raw:
        return None
    try:
        dt = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        offset_str = cycle.get("timezone_offset", "+00:00")
        hours, minutes = int(offset_str[:3]), int(offset_str[0] + offset_str[4:6])
        tz = datetime.timezone(datetime.timedelta(hours=hours, minutes=minutes))
        return dt.astimezone(tz).date()
    except (ValueError, TypeError):
        return None


def _recovery_to_date(recovery: dict, cycle_dates: dict[int, datetime.date]) -> datetime.date | None:
    cycle_id = recovery.get("cycle_id")
    if cycle_id and cycle_id in cycle_dates:
        return cycle_dates[cycle_id]
    return None


def _sleep_to_date(sleep: dict, cycle_dates: dict[int, datetime.date]) -> datetime.date | None:
    cycle_id = sleep.get("cycle_id")
    if cycle_id and cycle_id in cycle_dates:
        return cycle_dates[cycle_id]
    raw = sleep.get("start")
    if raw:
        try:
            dt = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            offset_str = sleep.get("timezone_offset", "+00:00")
            hours, minutes = int(offset_str[:3]), int(offset_str[0] + offset_str[4:6])
            tz = datetime.timezone(datetime.timedelta(hours=hours, minutes=minutes))
            return dt.astimezone(tz).date()
        except (ValueError, TypeError):
            pass
    return None


@dataclass
class DayMetrics:
    recovery_score: float | None = None
    hrv_rmssd: float | None = None
    resting_heart_rate: float | None = None
    sleep_performance_pct: float | None = None
    sleep_duration_minutes: int | None = None
    day_strain: float | None = None
    calories_total: float | None = None
    extra: dict = field(default_factory=dict)


def _build_day_map(
    cycles: list[dict],
    recoveries: list[dict],
    sleeps: list[dict],
) -> dict[datetime.date, DayMetrics]:
    """Merge the three API responses into per-day metric bundles."""

    cycle_dates: dict[int, datetime.date] = {}
    day_map: dict[datetime.date, DayMetrics] = {}

    for c in cycles:
        d = _cycle_start_to_date(c)
        if d is None:
            continue
        cycle_id = c.get("id")
        if cycle_id:
            cycle_dates[cycle_id] = d

        m = day_map.setdefault(d, DayMetrics())
        score = c.get("score")
        if score and c.get("score_state") == "SCORED":
            m.day_strain = score.get("strain")
            kj = score.get("kilojoule")
            if kj is not None:
                m.calories_total = round(kj * KJ_TO_KCAL, 1)

    for r in recoveries:
        d = _recovery_to_date(r, cycle_dates)
        if d is None:
            continue
        m = day_map.setdefault(d, DayMetrics())
        score = r.get("score")
        if score and r.get("score_state") == "SCORED":
            m.recovery_score = score.get("recovery_score")
            m.hrv_rmssd = score.get("hrv_rmssd_milli")
            m.resting_heart_rate = score.get("resting_heart_rate")
            spo2 = score.get("spo2_percentage")
            if spo2 is not None:
                m.extra["spo2_percentage"] = spo2
            skin = score.get("skin_temp_celsius")
            if skin is not None:
                m.extra["skin_temp_celsius"] = skin

    for s in sleeps:
        if s.get("nap", False):
            continue
        d = _sleep_to_date(s, cycle_dates)
        if d is None:
            continue
        m = day_map.setdefault(d, DayMetrics())
        score = s.get("score")
        if score and s.get("score_state") == "SCORED":
            m.sleep_performance_pct = score.get("sleep_performance_percentage")
            stage = score.get("stage_summary", {})
            total_bed = stage.get("total_in_bed_time_milli")
            if total_bed is not None:
                m.sleep_duration_minutes = round(total_bed * MS_TO_MINUTES)
            resp_rate = score.get("respiratory_rate")
            if resp_rate is not None:
                m.extra["respiratory_rate"] = resp_rate
            eff = score.get("sleep_efficiency_percentage")
            if eff is not None:
                m.extra["sleep_efficiency_pct"] = eff
            cons = score.get("sleep_consistency_percentage")
            if cons is not None:
                m.extra["sleep_consistency_pct"] = cons

    return day_map


@dataclass
class SyncResult:
    inserted: int = 0
    updated: int = 0
    days_fetched: int = 0
    errors: list[str] = field(default_factory=list)


async def sync_whoop_data(
    db: AsyncSession,
    *,
    days_back: int = 14,
) -> SyncResult:
    now = datetime.datetime.now(datetime.timezone.utc)
    start_dt = now - datetime.timedelta(days=days_back)
    start_iso = start_dt.strftime("%Y-%m-%dT00:00:00.000Z")
    end_iso = now.strftime("%Y-%m-%dT23:59:59.999Z")

    result = SyncResult()

    try:
        cycles = await fetch_collection(db, "/v2/cycle", start_iso, end_iso)
        recoveries = await fetch_collection(db, "/v2/recovery", start_iso, end_iso)
        sleeps = await fetch_collection(db, "/v2/activity/sleep", start_iso, end_iso)
    except Exception as exc:
        result.errors.append(f"Whoop API fetch failed: {exc}")
        return result

    day_map = _build_day_map(cycles, recoveries, sleeps)
    result.days_fetched = len(day_map)

    if not day_map:
        return result

    dates = list(day_map.keys())
    existing_q = await db.execute(
        select(HealthMetric).where(HealthMetric.entry_date.in_(dates))
    )
    existing: dict[datetime.date, HealthMetric] = {
        row.entry_date: row for row in existing_q.scalars().all()
    }

    for d, metrics in day_map.items():
        extra_json = json.dumps(metrics.extra) if metrics.extra else None

        row = existing.get(d)
        if row is None:
            db.add(HealthMetric(
                entry_date=d,
                source="whoop",
                recovery_score=metrics.recovery_score,
                hrv_rmssd=metrics.hrv_rmssd,
                resting_heart_rate=metrics.resting_heart_rate,
                sleep_performance_pct=metrics.sleep_performance_pct,
                sleep_duration_minutes=metrics.sleep_duration_minutes,
                day_strain=metrics.day_strain,
                calories_total=metrics.calories_total,
                extra_json=extra_json,
            ))
            result.inserted += 1
        else:
            row.source = "whoop"
            row.recovery_score = metrics.recovery_score
            row.hrv_rmssd = metrics.hrv_rmssd
            row.resting_heart_rate = metrics.resting_heart_rate
            row.sleep_performance_pct = metrics.sleep_performance_pct
            row.sleep_duration_minutes = metrics.sleep_duration_minutes
            row.day_strain = metrics.day_strain
            row.calories_total = metrics.calories_total
            row.extra_json = extra_json
            result.updated += 1

    await db.commit()
    return result
