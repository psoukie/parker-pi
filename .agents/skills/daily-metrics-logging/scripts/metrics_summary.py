from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from sleep_metrics import bedtime_axis_hour, fitness_score, read_daily_metrics_csv, routine_score


PRESET_CHOICES = ("1w", "pw", "4w", "7w")


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


def rows_with_dashboard_values(data_path: Path) -> list[dict]:
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


def resolve_range(rows: list[dict], preset: str | None, start_text: str | None, end_text: str | None) -> tuple[date, date]:
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


def average(values: list[float | None]) -> tuple[float | None, int]:
    present = [value for value in values if value is not None]
    if not present:
        return None, 0
    return sum(present) / len(present), len(present)


def format_hours(value: float | None) -> str:
    if value is None:
        return "n/a"
    total_minutes = round(value * 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}:{minutes:02d}"


def format_bedtime(value: float | None) -> str:
    if value is None:
        return "n/a"
    total_minutes = round(((value + 24) if value < 0 else value) * 60) % (24 * 60)
    hours, minutes = divmod(total_minutes, 60)
    hour12 = 12 if hours % 12 == 0 else hours % 12
    suffix = "a" if hours < 12 else "p"
    return f"{hour12}:{minutes:02d}{suffix}"


def format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{round(value * 100)}%"


def format_bedtime_compact(value: float | None) -> str:
    if value is None:
        return "n/a"
    total_minutes = round(((value + 24) if value < 0 else value) * 60) % (24 * 60)
    hours, minutes = divmod(total_minutes, 60)
    hour12 = 12 if hours % 12 == 0 else hours % 12
    return f"{hour12}:{minutes:02d}"


def rounded_sleep_minutes(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value * 60)


def rounded_bedtime_folded_minutes(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value * 60)


def rounded_drinks_tenths(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value * 10)


def rounded_percent_points(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value * 100)


def format_duration_minutes(minutes: int | None) -> str:
    if minutes is None:
        return "n/a"
    signless = abs(minutes)
    hours, mins = divmod(signless, 60)
    return f"{hours}:{mins:02d}"


def format_drinks_tenths(tenths: int | None) -> str:
    if tenths is None:
        return "n/a"
    return f"{tenths / 10:.1f}"


def format_percent_points(points: int | None) -> str:
    if points is None:
        return "n/a"
    return f"{points}%"


def trend_marker(delta: int | None) -> str:
    if delta is None:
        return "="
    if delta > 0:
        return "↑"
    if delta < 0:
        return "↓"
    return "="


def format_change(delta: int | None, kind: str) -> str:
    if delta is None or delta == 0:
        return "="
    marker = trend_marker(delta)
    magnitude = abs(delta)
    if kind in {"bedtime", "sleep"}:
        return f"{marker} {format_duration_minutes(magnitude)}"
    if kind == "drinks":
        return f"{marker} {format_drinks_tenths(magnitude)}"
    if kind == "percent":
        return f"{marker} {magnitude}pt"
    raise ValueError(f"Unknown change kind: {kind}")


def summarize(data_path: Path, preset: str | None, start_text: str | None, end_text: str | None) -> dict:
    rows = rows_with_dashboard_values(data_path)
    start, end = resolve_range(rows, preset, start_text, end_text)
    in_range = [row for row in rows if start <= row["date"] <= end]

    sleep_avg, sleep_days = average([row["sleep_hours"] for row in in_range])
    bed_avg, bed_days = average([row["bedtime_folded"] for row in in_range if row["sleep_hours"] is not None])
    drinks_avg, drinks_days = average([row["drinks"] for row in in_range])
    zazen_avg, zazen_days = average([row["zazen_value"] for row in in_range])
    routine_avg, routine_days = average([row["routine_value"] for row in in_range])
    fitness_avg, fitness_days = average([row["fitness_value"] for row in in_range])

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
            "avg_sleep": format_hours(sleep_avg),
            "avg_bedtime": format_bedtime(bed_avg),
            "avg_drinks": "n/a" if drinks_avg is None else f"{drinks_avg:.1f}".replace(".0", ""),
            "zazen": format_percent(zazen_avg),
            "routines": format_percent(routine_avg),
            "fitness": format_percent(fitness_avg),
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


def render_text(summary: dict) -> str:
    rng = summary["range"]
    display = summary["display"]
    return "\n".join(
        [
            f"Range: {rng['start']} to {rng['end']} ({rng['calendar_days']} days, {rng['rows_in_range']} rows)",
            f"Avg sleep: {display['avg_sleep']}",
            f"Avg bedtime: {display['avg_bedtime']}",
            f"Avg drinks: {display['avg_drinks']}",
            f"Zazen: {display['zazen']}",
            f"Routines: {display['routines']}",
            f"Fitness: {display['fitness']}",
        ]
    )


def weekly_review_summaries(data_path: Path, end_text: str | None = None) -> tuple[dict, dict]:
    if end_text is None:
        return summarize(data_path, "1w", None, None), summarize(data_path, "pw", None, None)

    end = date.fromisoformat(end_text)
    current_start = end - timedelta(days=6)
    previous_end = end - timedelta(days=7)
    previous_start = end - timedelta(days=13)
    return (
        summarize(data_path, None, current_start.isoformat(), end.isoformat()),
        summarize(data_path, None, previous_start.isoformat(), previous_end.isoformat()),
    )


def render_weekly_review_lines(data_path: Path, end_text: str | None = None) -> list[str]:
    current, previous = weekly_review_summaries(data_path, end_text)

    current_avg = current["averages"]
    previous_avg = previous["averages"]

    bedtime_now = rounded_bedtime_folded_minutes(current_avg["bedtime_folded_hours"])
    bedtime_prev = rounded_bedtime_folded_minutes(previous_avg["bedtime_folded_hours"])
    sleep_now = rounded_sleep_minutes(current_avg["sleep_hours"])
    sleep_prev = rounded_sleep_minutes(previous_avg["sleep_hours"])
    drinks_now = rounded_drinks_tenths(current_avg["drinks"])
    drinks_prev = rounded_drinks_tenths(previous_avg["drinks"])
    routines_now = rounded_percent_points(current_avg["routines"])
    routines_prev = rounded_percent_points(previous_avg["routines"])
    zazen_now = rounded_percent_points(current_avg["zazen"])
    zazen_prev = rounded_percent_points(previous_avg["zazen"])
    fitness_now = rounded_percent_points(current_avg["fitness"])
    fitness_prev = rounded_percent_points(previous_avg["fitness"])

    left_label_width = len("Bedtime:")
    right_label_width = len("Routines:")
    left_value_width = max(
        len("11:39"),
        len(format_bedtime_compact(current_avg["bedtime_folded_hours"])),
        len(format_hours(current_avg["sleep_hours"])),
        len(format_drinks_tenths(drinks_now)),
    )
    right_value_width = max(
        len("45%"),
        len(format_percent_points(routines_now)),
        len(format_percent_points(zazen_now)),
        len(format_percent_points(fitness_now)),
    )

    return [
        f"{'Bedtime:':<{left_label_width}} {format_bedtime_compact(current_avg['bedtime_folded_hours']):>{left_value_width}}  {format_change(None if bedtime_now is None or bedtime_prev is None else bedtime_now - bedtime_prev, 'bedtime'):<8}   {'Routines:':<{right_label_width}} {format_percent_points(routines_now):>{right_value_width}} {format_change(None if routines_now is None or routines_prev is None else routines_now - routines_prev, 'percent')}",
        f"{'Sleep:':<{left_label_width}} {format_hours(current_avg['sleep_hours']):>{left_value_width}}  {format_change(None if sleep_now is None or sleep_prev is None else sleep_now - sleep_prev, 'sleep'):<8}   {'Zazen:':<{right_label_width}} {format_percent_points(zazen_now):>{right_value_width}} {format_change(None if zazen_now is None or zazen_prev is None else zazen_now - zazen_prev, 'percent')}",
        f"{'Drinks:':<{left_label_width}} {format_drinks_tenths(drinks_now):>{left_value_width}}  {format_change(None if drinks_now is None or drinks_prev is None else drinks_now - drinks_prev, 'drinks'):<8}   {'Fitness:':<{right_label_width}} {format_percent_points(fitness_now):>{right_value_width}} {format_change(None if fitness_now is None or fitness_prev is None else fitness_now - fitness_prev, 'percent')}",
    ]


def render_weekly_review_markdown(data_path: Path, end_text: str | None = None) -> str:
    return "```text\n" + "\n".join(render_weekly_review_lines(data_path, end_text)) + "\n```"
