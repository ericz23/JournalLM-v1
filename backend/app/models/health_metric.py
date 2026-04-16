import datetime

from sqlalchemy import Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class HealthMetric(TimestampMixin, Base):
    """Physiological layer — daily objective data from wearable APIs.

    Uses the same `entry_date` column (unique per day) as journal data
    so that physiological metrics can be joined directly against events
    and reflections on the shared date axis.
    """

    __tablename__ = "health_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[datetime.date] = mapped_column(Date, unique=True, index=True)
    source: Mapped[str] = mapped_column(
        String(50), default="whoop", comment="Origin API identifier"
    )

    # Recovery & readiness
    recovery_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hrv_rmssd: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Heart-rate variability (ms)"
    )
    resting_heart_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Sleep
    sleep_performance_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Activity / strain
    day_strain: Mapped[float | None] = mapped_column(Float, nullable=True)
    calories_total: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Flexible overflow for future metrics
    extra_json: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Catch-all JSON for additional wearable fields"
    )
