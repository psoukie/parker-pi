#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import fcntl
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
USER_DATA_DIR = Path(os.environ.get("USER_DATA", Path.home() / "user_data"))

from sleep_metrics import CSV_FIELDS, _optional_bool, ensure_daily_metrics_csv, parse_clock  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Insert or update one Parker daily metrics row.",
        epilog=(
            "Formats: bedtime and wake use 24-hour HH:MM; drinks use decimal units like 1.5 or 3.5; "
            "boolean flags accept 1/0, yes/no, true/false, or y/n; fitness-other and notes are free text (e.g. `Pilates`). "
            "Canonical storage leaves drinks at 0 and false activity booleans blank rather than writing explicit 0/no. "
            "Only provided fields are updated; all others for that date are preserved. "
            "After a successful write, the dashboard is redrawn automatically."
        ),
    )
    parser.add_argument("--date", default=date.today().isoformat(), help="Date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--bedtime", help="Bedtime in 24-hour HH:MM, for example 22:40 or 00:30.")
    parser.add_argument("--wake", dest="wake_time", help="Wake time in 24-hour HH:MM, for example 06:10 or 08:00.")
    parser.add_argument("--drinks", help="Alcohol units as a number, for example 0, 1.5, 3.5, or 4.")
    parser.add_argument("--morning-routine", help="Boolean: 1/0, yes/no, true/false, or y/n.")
    parser.add_argument("--evening-routine", help="Boolean: 1/0, yes/no, true/false, or y/n.")
    parser.add_argument("--zazen", help="Boolean: 1/0, yes/no, true/false, or y/n.")
    parser.add_argument("--fitness-walk", help="Boolean: 1/0, yes/no, true/false, or y/n.")
    parser.add_argument("--fitness-run", help="Boolean: 1/0, yes/no, true/false, or y/n.")
    parser.add_argument("--fitness-other", help="Free text label for other activity, for example 'Pilates' or 'yard work'.")
    parser.add_argument("--notes", help="Free text note for the date.")
    parser.add_argument(
        "--data",
        default=str(USER_DATA_DIR / "metrics" / "daily-metrics.csv"),
        help="Path to the private daily metrics CSV. Defaults to $USER_DATA/metrics/daily-metrics.csv, or ~/user_data/metrics/daily-metrics.csv if USER_DATA is unset.",
    )
    parser.add_argument(
        "--render-output",
        default=str(USER_DATA_DIR / "artifacts" / "daily-metrics-dashboard.html"),
        help="Dashboard HTML output path to refresh after writing the metrics row. Defaults to $USER_DATA/artifacts/daily-metrics-dashboard.html, or ~/user_data/artifacts/daily-metrics-dashboard.html if USER_DATA is unset.",
    )
    return parser.parse_args()


def _normalized_time(value: str | None) -> str | None:
    if value is None:
        return None
    hour, minute = parse_clock(value)
    return f"{hour:02d}:{minute:02d}"


def _normalized_drinks(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = float(value)
    if parsed == 0:
        return ""
    return format(parsed, "g")


def _normalized_bool(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = _optional_bool(value)
    if parsed is None or parsed is False:
        return ""
    return "yes"


def validate_and_normalize_args(args: argparse.Namespace) -> dict[str, str | None]:
    try:
        normalized_date = date.fromisoformat(args.date).isoformat()
        normalized_updates = {
            "bedtime": _normalized_time(args.bedtime),
            "wake_time": _normalized_time(args.wake_time),
            "drinks": _normalized_drinks(args.drinks),
            "morning_routine": _normalized_bool(args.morning_routine),
            "evening_routine": _normalized_bool(args.evening_routine),
            "zazen": _normalized_bool(args.zazen),
            "fitness_walk": _normalized_bool(args.fitness_walk),
            "fitness_run": _normalized_bool(args.fitness_run),
            "fitness_other": args.fitness_other,
            "notes": args.notes,
        }
    except ValueError as exc:
        raise SystemExit(f"Invalid input: {exc}") from exc

    args.date = normalized_date
    return normalized_updates


@contextmanager
def exclusive_metrics_lock(data_path: Path):
    """Serialize read/modify/write/render cycles for the metrics CSV."""
    data_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = data_path.with_suffix(data_path.suffix + ".lock")
    with lock_path.open("w", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def main() -> None:
    args = parse_args()
    updates = validate_and_normalize_args(args)
    path = Path(args.data)

    with exclusive_metrics_lock(path):
        ensure_daily_metrics_csv(path)

        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        row = next((existing for existing in rows if existing["date"] == args.date), None)
        if row is None:
            row = {field: "" for field in CSV_FIELDS}
            row["date"] = args.date
            rows.append(row)

        if not any(value is not None for value in updates.values()):
            raise SystemExit("No updates provided.")

        for field, value in updates.items():
            if value is not None:
                row[field] = str(value)

        rows.sort(key=lambda item: item["date"])
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "render-sleep-dashboard.py"),
                "--data",
                str(path),
                "--output",
                args.render_output,
            ],
            check=True,
        )

    print(path)


if __name__ == "__main__":
    main()
