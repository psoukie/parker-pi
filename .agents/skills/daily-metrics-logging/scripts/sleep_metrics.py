from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path


CSV_FIELDS = [
    "date",
    "bedtime",
    "wake_time",
    "drinks",
    "morning_routine",
    "evening_routine",
    "zazen",
    "fitness_walk",
    "fitness_run",
    "fitness_other",
    "notes",
]


@dataclass(frozen=True)
class DailyMetricsEntry:
    date: date
    bedtime: str | None = None
    wake_time: str | None = None
    sleep_hours: float | None = None
    drinks: float | None = None
    morning_routine: bool | None = None
    evening_routine: bool | None = None
    zazen: bool | None = None
    fitness_walk: bool | None = None
    fitness_run: bool | None = None
    fitness_other: str = ""
    notes: str = ""

    @property
    def has_sleep(self) -> bool:
        return self.bedtime is not None and self.wake_time is not None and self.sleep_hours is not None


def parse_clock(value: str) -> tuple[int, int]:
    value = value.strip().lower().replace(".", "")
    suffix = None
    if value.endswith("am") or value.endswith("pm"):
        suffix = value[-2:]
        value = value[:-2].strip()

    if ":" in value:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    else:
        hour = int(value)
        minute = 0

    if suffix == "pm" and hour != 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"Invalid clock time: {value!r}")

    return hour, minute


def clock_to_decimal_hour(value: str) -> float:
    hour, minute = parse_clock(value)
    return hour + minute / 60


def bedtime_axis_hour(value: str) -> float:
    hour = clock_to_decimal_hour(value)
    return hour - 24 if hour >= 18 else hour


def wake_axis_hour(value: str) -> float:
    return clock_to_decimal_hour(value) - 6


def sleep_duration_hours(bedtime: str, wake_time: str) -> float:
    bed_hour, bed_minute = parse_clock(bedtime)
    wake_hour, wake_minute = parse_clock(wake_time)
    start = datetime(2000, 1, 1, bed_hour, bed_minute)
    end = datetime(2000, 1, 1, wake_hour, wake_minute)
    if end <= start:
        end += timedelta(days=1)
    return round((end - start).total_seconds() / 3600, 2)


def ema(values: list[float], alpha: float) -> list[float]:
    if not values:
        return []
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in the range (0, 1]")

    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def ema_sparse(values: list[float | None], alpha: float) -> list[float | None]:
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in the range (0, 1]")

    result: list[float | None] = []
    previous: float | None = None
    for value in values:
        if value is None:
            result.append(None)
            continue
        previous = value if previous is None else alpha * value + (1 - alpha) * previous
        result.append(previous)
    return result


def routine_score(morning_routine: bool | None, evening_routine: bool | None) -> float | None:
    if morning_routine is None and evening_routine is None:
        return None

    total = 0.0
    if morning_routine is True:
        total += 0.5
    if evening_routine is True:
        total += 0.5
    return total


def fitness_score(
    fitness_walk: bool | None,
    fitness_run: bool | None,
    fitness_other: str,
) -> float | None:
    other = fitness_other.strip()
    if fitness_walk is None and fitness_run is None and not other:
        return None
    if fitness_walk or fitness_run or other:
        return 1.0
    return 0.0


def _optional_float(value: str) -> float | None:
    value = value.strip()
    return float(value) if value else None


def _optional_bool(value: str) -> bool | None:
    value = value.strip().lower()
    if not value:
        return None
    if value in {"1", "true", "yes", "y"}:
        return True
    if value in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def _optional_text(value: str | None) -> str:
    return (value or "").strip()


def read_daily_metrics_csv(path: Path) -> list[DailyMetricsEntry]:
    if not path.exists():
        return []

    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        entries = []
        for row in rows:
            bedtime = _optional_text(row.get("bedtime"))
            wake_time = _optional_text(row.get("wake_time"))
            if bedtime and wake_time:
                sleep_hours = sleep_duration_hours(bedtime, wake_time)
            else:
                bedtime = None
                wake_time = None
                sleep_hours = None

            entries.append(
                DailyMetricsEntry(
                    date=date.fromisoformat(row["date"]),
                    bedtime=bedtime,
                    wake_time=wake_time,
                    sleep_hours=sleep_hours,
                    drinks=_optional_float(row.get("drinks", "")),
                    morning_routine=_optional_bool(row.get("morning_routine", "")),
                    evening_routine=_optional_bool(row.get("evening_routine", "")),
                    zazen=_optional_bool(row.get("zazen", "")),
                    fitness_walk=_optional_bool(row.get("fitness_walk", "")),
                    fitness_run=_optional_bool(row.get("fitness_run", "")),
                    fitness_other=_optional_text(row.get("fitness_other", "")),
                    notes=row.get("notes", ""),
                )
            )
    return sorted(entries, key=lambda item: item.date)


def ensure_daily_metrics_csv(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_FIELDS)


def read_sleep_csv(path: Path) -> list[DailyMetricsEntry]:
    return read_daily_metrics_csv(path)


def ensure_sleep_csv(path: Path) -> None:
    ensure_daily_metrics_csv(path)
