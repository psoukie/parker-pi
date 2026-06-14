#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

USER_DATA_DIR = Path(os.environ.get("USER_DATA", Path.home() / "user_data"))

from metrics_summary import PRESET_CHOICES, render_text, render_weekly_review_markdown, summarize  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize Parker daily metrics for a preset or custom date range.",
        epilog=(
            "Preset ranges mirror the dashboard semantics exactly: 1w=Last 7 days ending yesterday, "
            "pw=Previous 7 days, 4w=Past 4 weeks anchored to the latest data row, 7w=Past 7 weeks anchored to the latest data row. "
            "Custom ranges are inclusive."
        ),
    )
    parser.add_argument("--preset", choices=PRESET_CHOICES, help="Range preset: 1w, pw, 4w, or 7w.")
    parser.add_argument("--start", help="Custom inclusive start date in YYYY-MM-DD format.")
    parser.add_argument("--end", help="Custom inclusive end date in YYYY-MM-DD format.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a compact text summary.")
    parser.add_argument(
        "--weekly-review-markdown",
        action="store_true",
        help="Emit the habits weekly-review heartbeat block as a Markdown fenced text block. By default this compares 1w against pw; with --end YYYY-MM-DD it compares the 7-day window ending on that date against the preceding 7 days.",
    )
    parser.add_argument(
        "--data",
        default=str(USER_DATA_DIR / "metrics" / "daily-metrics.csv"),
        help="Path to daily metrics CSV. Defaults to $USER_DATA/metrics/daily-metrics.csv, or ~/user_data/metrics/daily-metrics.csv if USER_DATA is unset.",
    )
    args = parser.parse_args()

    if args.weekly_review_markdown:
        if args.preset or args.start:
            parser.error("--weekly-review-markdown cannot be combined with --preset or custom --start ranges.")
        if args.json:
            parser.error("--weekly-review-markdown cannot be combined with --json.")
        return args

    if args.preset and (args.start or args.end):
        parser.error("Use either --preset or --start/--end, not both.")
    if not args.preset and not (args.start or args.end):
        parser.error("Provide either --preset or a custom --start/--end range, or use --weekly-review-markdown.")
    if args.start and not args.end:
        parser.error("Custom ranges require both --start and --end.")
    if args.end and not args.start:
        parser.error("Custom ranges require both --start and --end.")
    return args


def main() -> None:
    args = parse_args()
    data_path = Path(args.data)
    if args.weekly_review_markdown:
        print(render_weekly_review_markdown(data_path, args.end))
        return
    summary = summarize(data_path, args.preset, args.start, args.end)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return
    print(render_text(summary))


if __name__ == "__main__":
    main()
