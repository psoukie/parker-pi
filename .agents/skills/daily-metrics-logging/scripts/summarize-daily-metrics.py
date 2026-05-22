#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path

USER_DATA_DIR = Path(os.environ.get("USER_DATA", Path.home() / "user_data"))

from sleep_metrics import bedtime_axis_hour, fitness_score, read_daily_metrics_csv, routine_score  # noqa: E402


PRESET_CHOICES = ("1w", "pw", "4w", "7w")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize Parker daily metrics for a preset or custom date range.",
        epilog=(
            "Preset ranges mirror the dashboard semantics exactly: 1w=Last 7 days ending yesterday, "
            "pw=Previous 7 days, 4w=Past 4 weeks anchored to the latest data row, 7w=Past 7 weeks anchored to the latest data row. "
            "Custom ranges are inclusive."
        ),
    )
    parser.add_argument(
        "--preset",
        choices=PRESET_CHOICES,
        help="Range preset: 1w, pw, 4w, or 7w.",
    )
    parser.add_argument("--start", help="Custom inclusive start date in YYYY-MM-DD format.")
    parser.add_argument("--end", help="Custom inclusive end date in YYYY-MM-DD format.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a compact text summary.")
    parser.add_argument(
        "--data",
        default=str(USER_DATA_DIR / "metrics" / "daily-metrics.csv"),
        help="Path to daily metrics CSV. Defaults to $USER_DATA/metrics/daily-metrics.csv, or ~/user_data/metrics/daily-metrics.csv if USER_DATA is unset.",
    )
    args = parser.parse_args()

    if args.preset and (args.start or args.end):
        parser.error("Use either --preset or --start/--end, not both.")
    if not args.preset and not (args.start or args.end):
        parser.error("Provide either --preset or a custom --start/--end range.")
    if args.start and not args.end:
        parser.error("Custom ranges require both --start and --end.")
    if args.end and not args.start:
        parser.error("Custom ranges require both --start and --end.")
    return args


def _bool_score(value: bool | None) -> float | None:
    if value is None:
        return None
    return 1.0 if value else 0.0


def _historical_value(value: float | None, index: int, last_index: int) -> float | None:
    if value is None and index < last_index:
        return 0.0
    return value


def _historical_bool_score(value: bool | None, index: int, last_index: int) -> float | None:
    if value is None and index < last_index:
        return 0.0
    return _bool_score(value)


def _historical_routine_score(
    morning_routine: bool | None,
    evening_routine: bool | None,
    index: int,
    last_index: int,
) -> float | None:
    if index < last_index:
        return (0.5 if morning_routine is True else 0.0) + (0.5 if evening_routine is True else 0.0)
    return routine_score(morning_routine, evening_routine)


def _historical_fitness_score(
    fitness_walk: bool | None,
    fitness_run: bool | None,
    fitness_other: str,
    index: int,
    last_index: int,
) -> float | None:
    value = fitness_score(fitness_walk, fitness_run, fitness_other)
    if value is None and index < last_index:
        return 0.0
    return value


def _rows_with_dashboard_values(data_path: Path) -> list[dict]:
    entries = read_daily_metrics_csv(data_path)
    last_index = len(entries) - 1
    rows = []
    for index, entry in enumerate(entries):
        rows.append(
            {
                "date": entry.date,
                "sleep_hours": entry.sleep_hours,
                "bedtime_folded": bedtime_axis_hour(entry.bedtime) if entry.bedtime else None,
                "drinks": _historical_value(entry.drinks, index, last_index),
                "zazen_value": _historical_bool_score(entry.zazen, index, last_index),
                "routine_value": _historical_routine_score(entry.morning_routine, entry.evening_routine, index, last_index),
                "fitness_value": _historical_fitness_score(entry.fitness_walk, entry.fitness_run, entry.fitness_other, index, last_index),
            }
        )
    return rows


def _resolve_range(rows: list[dict], preset: str | None, start_text: str | None, end_text: str | None) -> tuple[date, date]:
    if preset:
        if preset in {"1w", "pw"}:
            today = date.today()
            end = today - timedelta(days=1 if preset == "1w" else 8)
            start = end - timedelta(days=6)
            return start, end
        if not rows:
            raise SystemExit("No daily metrics data available.")
        latest = rows[-1]["date"]
        days = 27 if preset == "4w" else 48
        return latest - timedelta(days=days), latest

    start = date.fromisoformat(start_text or "")
    end = date.fromisoformat(end_text or "")
    if start > end:
        raise SystemExit("Custom range start must be on or before end.")
    return start, end


def _average(values: list[float | None]) -> tuple[float | None, int]:
    present = [value for value in values if value is not None]
    if not present:
        return None, 0
    return sum(present) / len(present), len(present)


def _format_hours(value: float | None) -> str:
    if value is None:
        return "n/a"
    total_minutes = round(value * 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}:{minutes:02d}"


def _format_bedtime(value: float | None) -> str:
    if value is None:
        return "n/a"
    total_minutes = round(((value + 24) if value < 0 else value) * 60) % (24 * 60)
    hours, minutes = divmod(total_minutes, 60)
    hour12 = 12 if hours % 12 == 0 else hours % 12
    suffix = "a" if hours < 12 else "p"
    return f"{hour12}:{minutes:02d}{suffix}"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{round(value * 100)}%"


def summarize(data_path: Path, preset: str | None, start_text: str | None, end_text: str | None) -> dict:
    rows = _rows_with_dashboard_values(data_path)
    start, end = _resolve_range(rows, preset, start_text, end_text)
    in_range = [row for row in rows if start <= row["date"] <= end]

    sleep_avg, sleep_days = _average([row["sleep_hours"] for row in in_range])
    bed_avg, bed_days = _average([row["bedtime_folded"] for row in in_range if row["sleep_hours"] is not None])
    drinks_avg, drinks_days = _average([row["drinks"] for row in in_range])
    zazen_avg, zazen_days = _average([row["zazen_value"] for row in in_range])
    routine_avg, routine_days = _average([row["routine_value"] for row in in_range])
    fitness_avg, fitness_days = _average([row["fitness_value"] for row in in_range])

    return {
        "range": {
            "preset": preset,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "calendar_days": (end - start).days + 1,
            "rows_in_range": len(in_range),
            "anchoring": (
                "today-relative" if preset in {"1w", "pw"} else "latest-data-relative" if preset in {"4w", "7w"} else "custom"
            ),
            "mirrors_dashboard": True,
        },
        "averages": {
            "sleep_hours": sleep_avg,
            "bedtime_folded_hours": bed_avg,
            "drinks": drinks_avg,
            "zazen": zazen_avg,
            "routines": routine_avg,
            "fitness": fitness_avg,
        },
        "display": {
            "avg_sleep": _format_hours(sleep_avg),
            "avg_bedtime": _format_bedtime(bed_avg),
            "avg_drinks": "n/a" if drinks_avg is None else f"{drinks_avg:.1f}".replace(".0", ""),
            "zazen": _format_percent(zazen_avg),
            "routines": _format_percent(routine_avg),
            "fitness": _format_percent(fitness_avg),
        },
        "counts": {
            "sleep_days": sleep_days,
            "bedtime_days": bed_days,
            "drinks_days": drinks_days,
            "zazen_days": zazen_days,
            "routine_days": routine_days,
            "fitness_days": fitness_days,
        },
    }


def _render_text(summary: dict) -> str:
    rng = summary["range"]
    display = summary["display"]
    counts = summary["counts"]
    return "\n".join(
        [
            f"Range: {rng['start']} to {rng['end']} ({rng['calendar_days']} days, {rng['rows_in_range']} rows)",
            f"Avg sleep: {display['avg_sleep']} ({counts['sleep_days']} contributing days)",
            f"Avg bedtime: {display['avg_bedtime']} ({counts['bedtime_days']} contributing days)",
            f"Avg drinks: {display['avg_drinks']} ({counts['drinks_days']} contributing days)",
            f"Zazen: {display['zazen']} ({counts['zazen_days']} contributing days)",
            f"Routines: {display['routines']} ({counts['routine_days']} contributing days)",
            f"Fitness: {display['fitness']} ({counts['fitness_days']} contributing days)",
        ]
    )


def main() -> None:
    args = parse_args()
    summary = summarize(Path(args.data), args.preset, args.start, args.end)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return
    print(_render_text(summary))


if __name__ == "__main__":
    main()
