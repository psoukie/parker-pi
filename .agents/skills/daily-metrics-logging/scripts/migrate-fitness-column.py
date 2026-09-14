#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

NEW_FIELDS = [
    "date",
    "bedtime",
    "wake_time",
    "drinks",
    "morning_routine",
    "evening_routine",
    "zazen",
    "fitness",
    "notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collapse legacy fitness_walk, fitness_run, and fitness_other columns into one fitness column. "
            "By default writes a sibling *.fitness-migrated.csv file; use --in-place to overwrite."
        )
    )
    parser.add_argument("csv_path", help="Path to daily-metrics.csv")
    parser.add_argument("--in-place", action="store_true", help="Overwrite the input file instead of writing a sibling file.")
    return parser.parse_args()


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def collapse_fitness(row: dict[str, str]) -> str:
    current = (row.get("fitness") or "").strip()
    if current:
        return current

    parts: list[str] = []
    if parse_bool(row.get("fitness_walk", "")):
        parts.append("walk")
    if parse_bool(row.get("fitness_run", "")):
        parts.append("run")
    other = (row.get("fitness_other") or "").strip()
    if other:
        parts.append(other)

    seen: set[str] = set()
    deduped: list[str] = []
    for part in parts:
        key = part.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(part)
    return "; ".join(deduped)


def migrate_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    migrated: list[dict[str, str]] = []
    for row in rows:
        migrated.append(
            {
                "date": row.get("date", ""),
                "bedtime": row.get("bedtime", ""),
                "wake_time": row.get("wake_time", ""),
                "drinks": row.get("drinks", ""),
                "morning_routine": row.get("morning_routine", ""),
                "evening_routine": row.get("evening_routine", ""),
                "zazen": row.get("zazen", ""),
                "fitness": collapse_fitness(row),
                "notes": row.get("notes", ""),
            }
        )
    return migrated


def main() -> None:
    args = parse_args()
    path = Path(args.csv_path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise SystemExit("CSV has no header.")
        rows = list(reader)

    output_path = path if args.in_place else path.with_suffix(".fitness-migrated.csv")
    migrated = migrate_rows(rows)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=NEW_FIELDS)
        writer.writeheader()
        writer.writerows(migrated)

    print(output_path)


if __name__ == "__main__":
    main()
