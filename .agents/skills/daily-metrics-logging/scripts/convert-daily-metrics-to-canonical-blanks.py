#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

BOOLEAN_FIELDS = [
    "morning_routine",
    "evening_routine",
    "zazen",
    "fitness_walk",
    "fitness_run",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "One-off migration: rewrite existing daily metrics CSV rows so false activity booleans "
            "and zero drinks are stored as blank canonical values."
        )
    )
    parser.add_argument("csv_path", help="Path to daily-metrics.csv")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite the input file. Without this flag, writes a sibling *.canonicalized.csv file.",
    )
    return parser.parse_args()


def canonical_bool(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"", "0", "false", "no", "n"}:
        return ""
    return value.strip()


def canonical_drinks(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    try:
        parsed = float(normalized)
    except ValueError:
        return normalized
    if parsed == 0:
        return ""
    return format(parsed, "g")


def main() -> None:
    args = parse_args()
    path = Path(args.csv_path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise SystemExit("CSV has no header.")
        rows = list(reader)

    for row in rows:
        row["drinks"] = canonical_drinks(row.get("drinks", ""))
        for field in BOOLEAN_FIELDS:
            row[field] = canonical_bool(row.get(field, ""))

    output_path = path if args.in_place else path.with_suffix(".canonicalized.csv")
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(output_path)


if __name__ == "__main__":
    main()
