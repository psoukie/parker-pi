#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sleep_metrics import bedtime_axis_hour, ema_sparse, fitness_score, parse_clock, read_daily_metrics_csv, routine_score


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render Parker's local daily metrics dashboard.")
    parser.add_argument(
        "--data",
        default="data/metrics/daily-metrics.csv",
        help="Path to daily metrics CSV. Defaults to ignored Parker local data.",
    )
    parser.add_argument(
        "--output",
        default="data/artifacts/daily-metrics-dashboard.html",
        help="Dashboard HTML output path.",
    )
    parser.add_argument("--fast-alpha", type=float, default=1 / 7)
    parser.add_argument("--slow-alpha", type=float, default=1 / 42)
    return parser.parse_args()


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


def _clock_minutes(value: str | None) -> int | None:
    if not value:
        return None
    hour, minute = parse_clock(value)
    return hour * 60 + minute


def _minutes_from_hours(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value * 60)


def _clock_minutes_from_folded_hours(value: float | None) -> int | None:
    if value is None:
        return None
    rounded_minutes = round(value * 60)
    return rounded_minutes % (24 * 60)


def _bool_flag(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _percent_value(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value * 100)


def _tenths_value(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value * 10)


def dashboard_payload(data_path: Path, fast_alpha: float, slow_alpha: float) -> dict:
    entries = read_daily_metrics_csv(data_path)
    if not entries:
        return {"s": "", "o": [], "bt": [], "wk": [], "sl": [], "as": [], "cs": [], "ab": [], "cb": [], "dr": [], "ad": [], "cd": [], "mr": [], "er": [], "rv": [], "ar": [], "cr": [], "zz": [], "zv": [], "az": [], "cz": [], "fw": [], "fr": [], "fo": [], "fv": [], "af": [], "cf": []}

    last_index = len(entries) - 1
    sleep_values = [entry.sleep_hours for entry in entries]
    bedtimes = [bedtime_axis_hour(entry.bedtime) if entry.bedtime else None for entry in entries]
    drinks = [_historical_value(entry.drinks, index, last_index) for index, entry in enumerate(entries)]
    zazen_values = [_historical_bool_score(entry.zazen, index, last_index) for index, entry in enumerate(entries)]
    routine_values = [
        _historical_routine_score(entry.morning_routine, entry.evening_routine, index, last_index)
        for index, entry in enumerate(entries)
    ]
    fitness_values = [
        _historical_fitness_score(entry.fitness_walk, entry.fitness_run, entry.fitness_other, index, last_index)
        for index, entry in enumerate(entries)
    ]

    acute_sleep = ema_sparse(sleep_values, fast_alpha)
    chronic_sleep = ema_sparse(sleep_values, slow_alpha)
    acute_bedtime = ema_sparse(bedtimes, fast_alpha)
    chronic_bedtime = ema_sparse(bedtimes, slow_alpha)
    acute_drinks = ema_sparse(drinks, fast_alpha)
    chronic_drinks = ema_sparse(drinks, slow_alpha)
    acute_zazen = ema_sparse(zazen_values, fast_alpha)
    chronic_zazen = ema_sparse(zazen_values, slow_alpha)
    acute_routine = ema_sparse(routine_values, fast_alpha)
    chronic_routine = ema_sparse(routine_values, slow_alpha)
    acute_fitness = ema_sparse(fitness_values, fast_alpha)
    chronic_fitness = ema_sparse(fitness_values, slow_alpha)

    start_date = entries[0].date
    return {
        "s": start_date.isoformat(),
        "o": [(entry.date - start_date).days for entry in entries],
        "bt": [_clock_minutes(entry.bedtime) for entry in entries],
        "wk": [_clock_minutes(entry.wake_time) for entry in entries],
        "sl": [_minutes_from_hours(entry.sleep_hours) for entry in entries],
        "as": [_minutes_from_hours(value) for value in acute_sleep],
        "cs": [_minutes_from_hours(value) for value in chronic_sleep],
        "ab": [_clock_minutes_from_folded_hours(value) for value in acute_bedtime],
        "cb": [_clock_minutes_from_folded_hours(value) for value in chronic_bedtime],
        "dr": [_tenths_value(value) for value in drinks],
        "ad": [_tenths_value(value) for value in acute_drinks],
        "cd": [_tenths_value(value) for value in chronic_drinks],
        "mr": [_bool_flag(entry.morning_routine) for entry in entries],
        "er": [_bool_flag(entry.evening_routine) for entry in entries],
        "rv": [_percent_value(value) for value in routine_values],
        "ar": [_percent_value(value) for value in acute_routine],
        "cr": [_percent_value(value) for value in chronic_routine],
        "zz": [_bool_flag(entry.zazen) for entry in entries],
        "zv": [_percent_value(value) for value in zazen_values],
        "az": [_percent_value(value) for value in acute_zazen],
        "cz": [_percent_value(value) for value in chronic_zazen],
        "fw": [_bool_flag(entry.fitness_walk) for entry in entries],
        "fr": [_bool_flag(entry.fitness_run) for entry in entries],
        "fo": [entry.fitness_other for entry in entries],
        "fv": [_percent_value(value) for value in fitness_values],
        "af": [_percent_value(value) for value in acute_fitness],
        "cf": [_percent_value(value) for value in chronic_fitness],
    }


def render_html(payload: dict) -> str:
    data_json = json.dumps(payload, separators=(",", ":"))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Parker Daily Metrics Dashboard</title>
  <style>
    :root {{
      --ink: #334155;
      --muted: #64748b;
      --grid: #dbe3ec;
      --paper: #f8fafc;
      --panel: #ffffff;
      --bar: #dbe7f5;
      --bar-strong: #bdd3eb;
      --bar-inverted: #f4bd8f;
      --blue: #5b8cc9;
      --blue-dark: #2f6fb5;
      --amber: #e89044;
      --amber-dark: #cf7322;
      --drink-bar: #f8dcc4;
      --purple: #9a7fd6;
      --purple-dark: #6747b0;
      --purple-bar: #ebe2fb;
      --gray: #8e98a6;
      --gray-dark: #5f6b79;
      --gray-bar: #e7ebf0;
      --red: #c95656;
      --red-dark: #9f3131;
      --red-bar: #f5dddd;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #f8fafc 0%, #edf3f8 100%);
      color: var(--ink);
      font-family: ui-serif, Georgia, Cambria, "Times New Roman", serif;
    }}
    main {{
      max-width: 1240px;
      margin: 0 auto;
      padding: 32px 28px 48px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: end;
      margin-bottom: 20px;
    }}
    h1 {{
      margin: 0;
      font-size: 34px;
      line-height: 1.05;
      letter-spacing: 0;
    }}
    .subtle {{
      color: var(--muted);
      font-size: 15px;
      margin-top: 8px;
    }}
    .stats {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .toolbar {{
      display: flex;
      flex-direction: column;
      align-items: stretch;
      gap: 12px;
      margin-bottom: 14px;
      position: sticky;
      top: 0;
      z-index: 10;
      padding: 10px 0 12px;
      background: rgba(248, 250, 252, .92);
      backdrop-filter: blur(8px);
    }}
    .toolbar-main {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }}
    .toolbar-controls {{
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .range-toggle {{
      display: inline-flex;
      border: 1px solid #d6dee8;
      background: rgba(255, 255, 255, .75);
    }}
    .range-toggle button, .legend-toggle {{
      border: 0;
      background: transparent;
      color: #52647c;
      font: 600 13px/1 ui-sans-serif, system-ui, sans-serif;
      padding: 10px 14px;
      cursor: pointer;
    }}
    .range-toggle button[data-active="true"], .legend-toggle[data-active="true"] {{
      background: #e8f0f8;
      color: #294f7f;
    }}
    .legend-toggle {{
      border: 1px solid #d6dee8;
      background: rgba(255, 255, 255, .75);
    }}
    .custom-range {{
      display: none;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .custom-range[data-visible="true"] {{
      display: flex;
    }}
    .custom-range label {{
      color: #52647c;
      font: 600 12px/1 ui-sans-serif, system-ui, sans-serif;
    }}
    .custom-range input {{
      border: 1px solid #d6dee8;
      background: rgba(255, 255, 255, .88);
      color: #334155;
      font: 600 13px/1 ui-sans-serif, system-ui, sans-serif;
      padding: 10px 12px;
    }}
    .stat {{
      background: rgba(255, 255, 255, .72);
      border: 1px solid #e1e8f0;
      padding: 10px 12px;
      min-width: 116px;
      text-align: center;
    }}
    .stat b {{
      display: block;
      font-size: 18px;
    }}
    .stat span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-top: 2px;
    }}
    .stat-sleep, .stat-bed {{
      background: rgba(219, 234, 254, .76);
      border-color: rgba(147, 197, 253, .48);
      color: var(--blue-dark);
    }}
    .stat-sleep span, .stat-bed span {{
      color: var(--blue-dark);
    }}
    .stat-drinks {{
      background: rgba(255, 237, 213, .8);
      border-color: rgba(251, 191, 36, .28);
      color: var(--amber-dark);
    }}
    .stat-drinks span {{
      color: var(--amber-dark);
    }}
    .stat-zazen {{
      background: rgba(235, 226, 251, .84);
      border-color: rgba(154, 127, 214, .34);
      color: var(--purple-dark);
    }}
    .stat-zazen span {{
      color: var(--purple-dark);
    }}
    .stat-routines {{
      background: rgba(231, 235, 240, .88);
      border-color: rgba(142, 152, 166, .34);
      color: var(--gray-dark);
    }}
    .stat-routines span {{
      color: var(--gray-dark);
    }}
    .stat-fitness {{
      background: rgba(245, 221, 221, .86);
      border-color: rgba(201, 86, 86, .3);
      color: var(--red-dark);
    }}
    .stat-fitness span {{
      color: var(--red-dark);
    }}
    .stat-range {{
      background: rgba(255, 255, 255, .78);
      border-color: #d9e2ec;
      color: var(--ink);
    }}
    .stat-range span {{
      color: var(--muted);
    }}
    .dashboard {{
      background: rgba(255, 255, 255, .78);
      border: 1px solid #e0e8f0;
      box-shadow: 0 18px 60px rgba(51, 65, 85, .08);
      padding: 20px;
    }}
    svg {{
      display: block;
      width: 100%;
      height: auto;
      background: var(--panel);
    }}
    .axis text, .legend text {{
      fill: #52647c;
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 13px;
    }}
    .axis path, .axis line {{
      stroke: #cbd5e1;
    }}
    .grid {{
      stroke: #cbd5e1;
      stroke-opacity: .7;
      stroke-width: .9;
    }}
    .label {{
      fill: #52647c;
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 15px;
      font-weight: 600;
    }}
    .chart-title {{
      font-family: ui-serif, Georgia, Cambria, "Times New Roman", serif;
      font-size: 22px;
      font-weight: 700;
      opacity: .78;
    }}
    .hover-label {{
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 18px;
      font-weight: 600;
      dominant-baseline: middle;
    }}
    .hover-date {{
      fill: #334155;
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 16px;
      font-weight: 700;
    }}
    .empty {{
      padding: 48px 20px;
      text-align: center;
      color: var(--muted);
      background: var(--panel);
      border: 1px dashed #cbd5e1;
    }}
    @media (max-width: 760px) {{
      main {{ padding: 20px 12px 32px; }}
      header {{ display: block; }}
      .stats {{ justify-content: flex-start; margin-top: 16px; }}
      .toolbar {{ top: 0; }}
      .toolbar-main {{ align-items: flex-start; }}
      .dashboard {{ padding: 8px; overflow-x: auto; }}
      svg {{ min-width: 900px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Parker Daily Metrics Dashboard</h1>
        <div class="subtle">Local sleep, routines, fitness, and drinks trends from Parker's private metrics file.</div>
      </div>
    </header>
    <div class="toolbar">
      <div class="toolbar-main">
        <div class="toolbar-controls">
          <div class="range-toggle" id="range-toggle">
            <button type="button" data-range="7w" data-active="true">Past 7 weeks</button>
            <button type="button" data-range="4w" data-active="false">Past 4 weeks</button>
            <button type="button" data-range="1w" data-active="false">Last 7 days</button>
            <button type="button" data-range="pw" data-active="false">Previous 7 days</button>
            <button type="button" data-range="custom" data-active="false">Custom</button>
          </div>
          <button type="button" class="legend-toggle" id="legend-toggle" data-active="false">Show legends</button>
        </div>
        <div class="stats" id="stats"></div>
      </div>
      <div class="custom-range" id="custom-range" data-visible="false">
        <label for="custom-start">Start</label>
        <input type="date" id="custom-start">
        <label for="custom-end">End</label>
        <input type="date" id="custom-end">
      </div>
    </div>
    <section class="dashboard" id="dashboard"></section>
  </main>
  <script>
    const payload = {data_json};

    const W = 1180;
    const chartLeft = 88;
    const chartRightPad = 36;
    const plotRight = W - chartRightPad;
    const plotWidth = plotRight - chartLeft;
    const margin = {{ left: chartLeft, right: chartRightPad }};
    const hoverLabelHeight = 28;
    const hoverLabelPadding = 8;
    const hoverLabelGap = 24;
    const lineLabelOffset = 18;

    const chartSpecs = [
      {{ key: "sleep", title: "Sleep", top: 44, height: 315, legendY: 410, weekendFill: "rgba(241, 245, 249, .72)", pillFill: "#dbeafe" }},
      {{ key: "bed", title: "Bedtime", top: 474, height: 270, legendY: 788, weekendFill: "rgba(241, 245, 249, .72)", pillFill: "#dbeafe" }},
      {{ key: "drinks", title: "Drinks", top: 834, height: 220, legendY: 1116, weekendFill: "rgba(232, 144, 68, .10)", pillFill: "#ffedd5" }},
      {{ key: "zazen", title: "Zazen", top: 1184, height: 120, legendY: 1372, weekendFill: "rgba(154, 127, 214, .08)", pillFill: "#ebe2fb" }},
      {{ key: "routines", title: "Routines", top: 1434, height: 134, legendY: 1636, weekendFill: "rgba(142, 152, 166, .08)", pillFill: "#e7ebf0" }},
      {{ key: "fitness", title: "Fitness", top: 1699, height: 147, legendY: 1914, weekendFill: "rgba(201, 86, 86, .08)", pillFill: "#f5dddd" }},
    ];
    const H = 1964;

    const parseDate = value => new Date(value + "T00:00:00");
    const addDays = (date, days) => {{
      const next = new Date(date);
      next.setDate(next.getDate() + days);
      return next;
    }};
    const isoDate = date => `${{date.getFullYear()}}-${{String(date.getMonth() + 1).padStart(2, "0")}}-${{String(date.getDate()).padStart(2, "0")}}`;
    const fmtDate = date => `${{date.getMonth() + 1}}/${{date.getDate()}}`;
    const bedtimeAxisHours = minutes => {{
      if (minutes == null) return null;
      const foldedMinutes = minutes >= 18 * 60 ? minutes - 24 * 60 : minutes;
      return foldedMinutes / 60;
    }};
    const wakeAxisHours = minutes => (minutes == null ? null : (minutes - 6 * 60) / 60);
    const decodeTenths = value => (value == null ? null : value / 10);
    const decodePercent = value => (value == null ? null : value / 100);
    const decodeBool = value => (value == null ? null : value === 1);
    const fmtHours = value => {{
      const totalMinutes = Math.round(value * 60);
      const hours = Math.floor(totalMinutes / 60);
      const minutes = totalMinutes % 60;
      return `${{hours}}:${{String(minutes).padStart(2, "0")}}`;
    }};
    const fmtPercent = value => `${{Math.round(value * 100)}}%`;
    const fmtClockMinutes = (minutes, withSuffix = false) => {{
      const normalizedMinutes = ((Math.round(minutes) % (24 * 60)) + (24 * 60)) % (24 * 60);
      const hours = Math.floor(normalizedMinutes / 60);
      const remainder = normalizedMinutes % 60;
      const hour12 = hours === 0 ? 12 : hours > 12 ? hours - 12 : hours;
      const suffix = hours >= 12 ? "p" : "a";
      return withSuffix
        ? `${{hour12}}:${{String(remainder).padStart(2, "0")}}${{suffix}}`
        : `${{hour12}}:${{String(remainder).padStart(2, "0")}}`;
    }};
    const fmtBedtime = value => fmtClockMinutes(Math.round((value < 0 ? value + 24 : value) * 60), true);
    const fmtClockLabel = value => fmtClockMinutes(Math.round((value < 0 ? value + 24 : value) * 60));
    const rows = payload.s
      ? payload.o.map((offset, index) => {{
          const dateObj = addDays(parseDate(payload.s), offset);
          const bedtimeMin = payload.bt[index];
          const wakeMin = payload.wk[index];
          const sleepMinutes = payload.sl[index];
          return {{
            date: isoDate(dateObj),
            dateObj,
            bedtimeMin,
            wakeMin,
            bedtimeHour: bedtimeAxisHours(bedtimeMin),
            wakeHour: wakeAxisHours(wakeMin),
            sleepHours: sleepMinutes == null ? null : sleepMinutes / 60,
            invertedWindow: sleepMinutes != null && sleepMinutes < 6 * 60,
            acuteSleep: payload.as[index] == null ? null : payload.as[index] / 60,
            chronicSleep: payload.cs[index] == null ? null : payload.cs[index] / 60,
            acuteBedtime: bedtimeAxisHours(payload.ab[index]),
            chronicBedtime: bedtimeAxisHours(payload.cb[index]),
            drinks: decodeTenths(payload.dr[index]),
            acuteDrinks: decodeTenths(payload.ad[index]),
            chronicDrinks: decodeTenths(payload.cd[index]),
            morningRoutine: decodeBool(payload.mr[index]),
            eveningRoutine: decodeBool(payload.er[index]),
            routineValue: decodePercent(payload.rv[index]),
            acuteRoutine: decodePercent(payload.ar[index]),
            chronicRoutine: decodePercent(payload.cr[index]),
            zazen: decodeBool(payload.zz[index]),
            zazenValue: decodePercent(payload.zv[index]),
            acuteZazen: decodePercent(payload.az[index]),
            chronicZazen: decodePercent(payload.cz[index]),
            fitnessWalk: decodeBool(payload.fw[index]),
            fitnessRun: decodeBool(payload.fr[index]),
            fitnessOther: payload.fo[index],
            fitnessValue: decodePercent(payload.fv[index]),
            acuteFitness: decodePercent(payload.af[index]),
            chronicFitness: decodePercent(payload.cf[index]),
          }};
        }})
      : [];

    function linePath(data, x, y, key) {{
      let path = "";
      let drawing = false;
      data.forEach(d => {{
        if (d[key] == null) {{
          drawing = false;
          return;
        }}
        path += `${{drawing ? "L" : "M"}} ${{x(d)}} ${{y(d[key])}} `;
        drawing = true;
      }});
      return path.trim();
    }}

    function areaSegmentPath(left, right, y, topKey, bottomKey) {{
      if (left[topKey] == null || right[topKey] == null || left[bottomKey] == null || right[bottomKey] == null) {{
        return "";
      }}
      return [
        `M ${{left.x}} ${{y(left[topKey])}}`,
        `L ${{right.x}} ${{y(right[topKey])}}`,
        `L ${{right.x}} ${{y(right[bottomKey])}}`,
        `L ${{left.x}} ${{y(left[bottomKey])}} Z`,
      ].join(" ");
    }}

    function makeScale(domainMin, domainMax, rangeMin, rangeMax) {{
      const span = domainMax - domainMin || 1;
      return value => rangeMin + ((value - domainMin) / span) * (rangeMax - rangeMin);
    }}

    function clamp(value, min, max) {{
      return Math.max(min, Math.min(max, value));
    }}

    function rowsForRange(allRows, rangeKey, customStart, customEnd) {{
      if (!allRows.length) return [];
      if (rangeKey === "custom") {{
        const start = customStart ? parseDate(customStart) : allRows[0].dateObj;
        const end = customEnd ? parseDate(customEnd) : allRows[allRows.length - 1].dateObj;
        if (start > end) return [];
        return allRows.filter(row => row.dateObj >= start && row.dateObj <= end);
      }}
      if (rangeKey === "1w" || rangeKey === "pw") {{
        const today = parseDate(isoDate(new Date()));
        const endOffset = rangeKey === "1w" ? -1 : -8;
        const end = addDays(today, endOffset);
        const start = addDays(end, -6);
        return allRows.filter(row => row.dateObj >= start && row.dateObj <= end);
      }}
      const latestDate = allRows[allRows.length - 1].dateObj;
      const cutoff = new Date(latestDate);
      if (rangeKey === "4w") {{
        cutoff.setDate(cutoff.getDate() - 27);
      }} else {{
        cutoff.setDate(cutoff.getDate() - 48);
      }}
      return allRows.filter(row => row.dateObj >= cutoff);
    }}

    function hoverLabel(xPos, yPos, text, color, anchor = "start") {{
      const width = Math.max(30, text.length * 7 + hoverLabelPadding * 2);
      const rectX = anchor === "start" ? xPos - hoverLabelPadding : xPos - width + hoverLabelPadding;
      const textX = xPos;
      return `
        <rect x="${{rectX}}" y="${{yPos - hoverLabelHeight / 2 - 1}}" width="${{width}}" height="${{hoverLabelHeight}}" rx="4" fill="#ffffff" opacity=".9"/>
        <text class="hover-label" x="${{textX}}" y="${{yPos}}" text-anchor="${{anchor}}" fill="${{color}}">${{text}}</text>
      `;
    }}

    function hoverDot(xPos, yPos, color) {{
      return `<circle cx="${{xPos}}" cy="${{yPos}}" r="4.5" fill="${{color}}" stroke="#ffffff" stroke-width="1.5"/>`;
    }}

    function barLabel(xPos, yPos, text, color, anchor = "middle") {{
      return `<text class="hover-label" x="${{xPos}}" y="${{yPos}}" text-anchor="${{anchor}}" fill="${{color}}">${{text}}</text>`;
    }}

    function distributeLabelYs(values, scale, minY, maxY) {{
      const placed = values
        .filter(item => item.value != null)
        .map(item => ({{ ...item, targetY: scale(item.value) }}))
        .sort((a, b) => a.targetY - b.targetY);

      if (!placed.length) return placed;

      placed[0].labelY = clamp(placed[0].targetY, minY, maxY);
      for (let i = 1; i < placed.length; i += 1) {{
        placed[i].labelY = Math.max(placed[i].targetY, placed[i - 1].labelY + hoverLabelGap);
      }}

      const overflow = placed[placed.length - 1].labelY - maxY;
      if (overflow > 0) {{
        placed[placed.length - 1].labelY -= overflow;
        for (let i = placed.length - 2; i >= 0; i -= 1) {{
          placed[i].labelY = Math.min(placed[i].labelY, placed[i + 1].labelY - hoverLabelGap);
        }}
        if (placed[0].labelY < minY) {{
          const underflow = minY - placed[0].labelY;
          placed.forEach(item => {{
            item.labelY += underflow;
          }});
        }}
      }}

      return placed;
    }}

    function drawLegend(items, startY, svgParts) {{
      const swatchWidth = 44;
      const textGap = 12;
      const itemGap = 28;
      const itemWidths = items.map(item => swatchWidth + textGap + Math.max(60, item[0].length * 8.2));
      const totalWidth = itemWidths.reduce((sum, width) => sum + width, 0) + itemGap * (items.length - 1);
      let itemX = margin.left + (plotWidth - totalWidth) / 2;
      items.forEach((item, index) => {{
        if (item[1] === "rect") svgParts.push(`<rect x="${{itemX}}" y="${{startY - 9}}" width="${{swatchWidth}}" height="12" fill="${{item[2]}}" opacity=".72"/>`);
        if (item[1] === "line") svgParts.push(`<line x1="${{itemX}}" x2="${{itemX + swatchWidth}}" y1="${{startY - 3}}" y2="${{startY - 3}}" stroke="${{item[2]}}" stroke-width="2"/>`);
        if (item[1] === "dot") svgParts.push(`<line x1="${{itemX}}" x2="${{itemX + swatchWidth}}" y1="${{startY - 3}}" y2="${{startY - 3}}" stroke="${{item[2]}}" stroke-width="3" stroke-linecap="round" stroke-dasharray="1 8"/>`);
        svgParts.push(`<text class="legend" x="${{itemX + swatchWidth + textGap}}" y="${{startY + 2}}">${{item[0]}}</text>`);
        itemX += itemWidths[index] + itemGap;
      }});
    }}

    function draw(rangeKey = "7w", showLegends = false, customStart = "", customEnd = "") {{
      const container = document.getElementById("dashboard");
      const stats = document.getElementById("stats");
      const toggle = document.getElementById("range-toggle");
      const legendToggle = document.getElementById("legend-toggle");
      const customRange = document.getElementById("custom-range");
      const customStartInput = document.getElementById("custom-start");
      const customEndInput = document.getElementById("custom-end");
      if (!rows.length) {{
        stats.innerHTML = "";
        container.innerHTML = '<div class="empty">No daily metrics yet. Log a row with log-daily-metrics.py, then render again.</div>';
        return;
      }}

      const allRows = rows;
      const data = rowsForRange(allRows, rangeKey, customStart, customEnd);
      toggle.querySelectorAll("button").forEach(button => {{
        button.dataset.active = String(button.dataset.range === rangeKey);
      }});
      legendToggle.dataset.active = String(showLegends);
      legendToggle.textContent = showLegends ? "Hide legends" : "Show legends";
      customRange.dataset.visible = String(rangeKey === "custom");
      customStartInput.value = customStart;
      customEndInput.value = customEnd;

      if (!data.length) {{
        stats.innerHTML = "";
        container.innerHTML = '<div class="empty">No daily metrics fall within the selected date range.</div>';
        return;
      }}

      const start = data[0].dateObj;
      const end = data[data.length - 1].dateObj;
      const slotWidth = plotWidth / data.length;
      const barWidth = Math.max(8, slotWidth * .82);
      const x = d => margin.left + d.index * slotWidth + slotWidth / 2;
      const ySleep = makeScale(5, 8.5, chartSpecs[0].top + chartSpecs[0].height, chartSpecs[0].top);
      const yBed = makeScale(-2, 2.1, chartSpecs[1].top + chartSpecs[1].height, chartSpecs[1].top);
      const maxDrinks = Math.max(6, ...data.map(row => row.drinks ?? 0));
      const drinksCeil = Math.max(2, Math.ceil(maxDrinks / 2) * 2);
      const yDrinks = makeScale(0, drinksCeil, chartSpecs[2].top + chartSpecs[2].height, chartSpecs[2].top);
      const yPercentZazen = makeScale(0, 1, chartSpecs[3].top + chartSpecs[3].height, chartSpecs[3].top);
      const yPercentRoutines = makeScale(0, 1, chartSpecs[4].top + chartSpecs[4].height, chartSpecs[4].top);
      const yPercentFitness = makeScale(0, 1, chartSpecs[5].top + chartSpecs[5].height, chartSpecs[5].top);

      const sleepRows = data.filter(row => row.sleepHours != null);
      const avgSleep = sleepRows.length
        ? sleepRows.reduce((sum, row) => sum + row.sleepHours, 0) / sleepRows.length
        : null;
      const avgBed = sleepRows.length
        ? sleepRows.reduce((sum, row) => sum + row.bedtimeHour, 0) / sleepRows.length
        : null;
      const drinksRows = data.filter(row => row.drinks != null);
      const avgDrinks = drinksRows.length
        ? drinksRows.reduce((sum, row) => sum + row.drinks, 0) / drinksRows.length
        : null;
      const zazenRows = data.filter(row => row.zazenValue != null);
      const avgZazen = zazenRows.length
        ? zazenRows.reduce((sum, row) => sum + row.zazenValue, 0) / zazenRows.length
        : null;
      const routineRows = data.filter(row => row.routineValue != null);
      const avgRoutine = routineRows.length
        ? routineRows.reduce((sum, row) => sum + row.routineValue, 0) / routineRows.length
        : null;
      const fitnessRows = data.filter(row => row.fitnessValue != null);
      const avgFitness = fitnessRows.length
        ? fitnessRows.reduce((sum, row) => sum + row.fitnessValue, 0) / fitnessRows.length
        : null;
      stats.innerHTML = `
        <div class="stat stat-sleep"><b>${{avgSleep == null ? "n/a" : fmtHours(avgSleep)}}</b><span>Avg sleep</span></div>
        <div class="stat stat-bed"><b>${{avgBed == null ? "n/a" : fmtBedtime(avgBed)}}</b><span>Avg bedtime</span></div>
        <div class="stat stat-drinks"><b>${{avgDrinks == null ? "n/a" : avgDrinks.toFixed(1).replace(/\\.0$/, "")}}</b><span>Avg drinks</span></div>
        <div class="stat stat-zazen"><b>${{avgZazen == null ? "n/a" : fmtPercent(avgZazen)}}</b><span>Zazen</span></div>
        <div class="stat stat-routines"><b>${{avgRoutine == null ? "n/a" : fmtPercent(avgRoutine)}}</b><span>Routines</span></div>
        <div class="stat stat-fitness"><b>${{avgFitness == null ? "n/a" : fmtPercent(avgFitness)}}</b><span>Fitness</span></div>
        <div class="stat stat-range"><b>${{fmtDate(start)}}-${{fmtDate(end)}}</b><span>Range</span></div>
      `;

      data.forEach((d, index) => {{
        d.index = index;
        d.x = x(d);
      }});

      const svgParts = [`<svg viewBox="0 0 ${{W}} ${{H}}" role="img" aria-label="Daily metrics trends">`];

      data.forEach(d => {{
        const day = d.dateObj.getDay();
        if (day !== 0 && day !== 6) return;
        const left = margin.left + d.index * slotWidth;
        chartSpecs.forEach(spec => {{
          svgParts.push(`<rect x="${{left}}" y="${{spec.top}}" width="${{slotWidth}}" height="${{spec.height}}" fill="${{spec.weekendFill}}"/>`);
        }});
      }});

      data.forEach(d => {{
        if (d.sleepHours != null) {{
          svgParts.push(`<rect x="${{x(d) - barWidth / 2}}" y="${{ySleep(d.sleepHours)}}" width="${{barWidth}}" height="${{ySleep(5) - ySleep(d.sleepHours)}}" fill="var(--bar)" opacity=".72"/>`);
        }}
        if (d.bedtimeHour != null && d.wakeHour != null) {{
          const windowTop = Math.min(yBed(d.bedtimeHour), yBed(d.wakeHour));
          const rawWindowHeight = Math.abs(yBed(d.wakeHour) - yBed(d.bedtimeHour));
          const windowHeight = Math.max(rawWindowHeight, 1.5);
          const windowFill = d.invertedWindow ? "var(--bar-inverted)" : "var(--bar-strong)";
          svgParts.push(`<rect x="${{x(d) - barWidth / 2}}" y="${{windowTop}}" width="${{barWidth}}" height="${{windowHeight}}" fill="${{windowFill}}" opacity=".46"/>`);
        }}
        if (d.drinks != null) {{
          svgParts.push(`<rect x="${{x(d) - barWidth / 2}}" y="${{yDrinks(d.drinks)}}" width="${{barWidth}}" height="${{yDrinks(0) - yDrinks(d.drinks)}}" fill="var(--drink-bar)" opacity=".78"/>`);
        }}
        if (d.zazen === true) {{
          svgParts.push(`<rect x="${{x(d) - barWidth / 2}}" y="${{yPercentZazen(1)}}" width="${{barWidth}}" height="${{yPercentZazen(0) - yPercentZazen(1)}}" fill="var(--purple-bar)" opacity=".78"/>`);
        }}
        if (d.morningRoutine === true) {{
          svgParts.push(`<rect x="${{x(d) - barWidth / 2}}" y="${{yPercentRoutines(0.5)}}" width="${{barWidth}}" height="${{yPercentRoutines(0) - yPercentRoutines(0.5)}}" fill="var(--gray-bar)" opacity=".82"/>`);
        }}
        if (d.eveningRoutine === true) {{
          svgParts.push(`<rect x="${{x(d) - barWidth / 2}}" y="${{yPercentRoutines(1)}}" width="${{barWidth}}" height="${{yPercentRoutines(0.5) - yPercentRoutines(1)}}" fill="var(--gray-bar)" opacity=".82"/>`);
        }}
        if (d.fitnessWalk === true) {{
          svgParts.push(`<rect x="${{x(d) - barWidth / 2}}" y="${{yPercentFitness(1 / 3)}}" width="${{barWidth}}" height="${{yPercentFitness(0) - yPercentFitness(1 / 3)}}" fill="var(--red-bar)" opacity=".84"/>`);
        }}
        if (d.fitnessRun === true) {{
          svgParts.push(`<rect x="${{x(d) - barWidth / 2}}" y="${{yPercentFitness(2 / 3)}}" width="${{barWidth}}" height="${{yPercentFitness(1 / 3) - yPercentFitness(2 / 3)}}" fill="var(--red-bar)" opacity=".84"/>`);
        }}
        if (d.fitnessOther) {{
          svgParts.push(`<rect x="${{x(d) - barWidth / 2}}" y="${{yPercentFitness(1)}}" width="${{barWidth}}" height="${{yPercentFitness(2 / 3) - yPercentFitness(1)}}" fill="var(--red-bar)" opacity=".84"/>`);
        }}
      }});

      const sleepGrid = [5, 6, 7, 8];
      const bedGrid = [-2, -1, 0, 1, 2];
      const drinksGrid = Array.from({{ length: drinksCeil / 2 + 1 }}, (_, index) => index * 2);
      const zazenGrid = [0, 1];
      const routinesGrid = [0, 0.5, 1];
      const fitnessGrid = [0, 1 / 3, 2 / 3, 1];

      sleepGrid.forEach(value => {{
        svgParts.push(`<line class="grid" x1="${{margin.left}}" x2="${{plotRight}}" y1="${{ySleep(value)}}" y2="${{ySleep(value)}}"/>`);
        svgParts.push(`<text class="axis" x="${{margin.left - 18}}" y="${{ySleep(value) + 5}}" text-anchor="end">${{value}}h</text>`);
      }});
      bedGrid.forEach(value => {{
        svgParts.push(`<line class="grid" x1="${{margin.left}}" x2="${{plotRight}}" y1="${{yBed(value)}}" y2="${{yBed(value)}}"/>`);
        svgParts.push(`<text class="axis" x="${{margin.left - 18}}" y="${{yBed(value) + 5}}" text-anchor="end">${{fmtBedtime(value)}}</text>`);
      }});
      drinksGrid.forEach(value => {{
        svgParts.push(`<line class="grid" x1="${{margin.left}}" x2="${{plotRight}}" y1="${{yDrinks(value)}}" y2="${{yDrinks(value)}}"/>`);
        svgParts.push(`<text class="axis" x="${{margin.left - 18}}" y="${{yDrinks(value) + 5}}" text-anchor="end">${{value}}</text>`);
      }});
      zazenGrid.forEach(value => {{
        const zY = yPercentZazen(value);
        svgParts.push(`<line class="grid" x1="${{margin.left}}" x2="${{plotRight}}" y1="${{zY}}" y2="${{zY}}"/>`);
      }});
      routinesGrid.forEach(value => {{
        const rY = yPercentRoutines(value);
        svgParts.push(`<line class="grid" x1="${{margin.left}}" x2="${{plotRight}}" y1="${{rY}}" y2="${{rY}}"/>`);
      }});
      fitnessGrid.forEach(value => {{
        const fY = yPercentFitness(value);
        svgParts.push(`<line class="grid" x1="${{margin.left}}" x2="${{plotRight}}" y1="${{fY}}" y2="${{fY}}"/>`);
      }});

      data.forEach((d, index) => {{
        const isMonday = d.dateObj.getDay() === 1;
        const shouldLabel = index === 0 || index === data.length - 1 || isMonday;
        if (!shouldLabel) return;
        const xx = x(d);
        chartSpecs.forEach(spec => {{
          svgParts.push(`<text class="axis" x="${{xx}}" y="${{spec.top + spec.height + 30}}" text-anchor="middle">${{fmtDate(d.dateObj)}}</text>`);
        }});
      }});

      svgParts.push(`<text class="chart-title" x="${{margin.left}}" y="${{chartSpecs[0].top - 6}}" fill="var(--blue-dark)">Sleep</text>`);
      svgParts.push(`<text class="chart-title" x="${{margin.left}}" y="${{chartSpecs[1].top - 8}}" fill="var(--blue-dark)">Bedtime</text>`);
      svgParts.push(`<text class="chart-title" x="${{margin.left}}" y="${{chartSpecs[2].top - 8}}" fill="var(--amber-dark)">Drinks</text>`);
      svgParts.push(`<text class="chart-title" x="${{margin.left}}" y="${{chartSpecs[3].top - 8}}" fill="var(--purple-dark)">Zazen</text>`);
      svgParts.push(`<text class="chart-title" x="${{margin.left}}" y="${{chartSpecs[4].top - 8}}" fill="var(--gray-dark)">Routines</text>`);
      svgParts.push(`<text class="chart-title" x="${{margin.left}}" y="${{chartSpecs[5].top - 8}}" fill="var(--red-dark)">Fitness</text>`);
      svgParts.push(`<text class="axis" x="${{margin.left - 18}}" y="${{yPercentZazen(0.5) + 5}}" text-anchor="end">Sit</text>`);
      svgParts.push(`<text class="axis" x="${{margin.left - 18}}" y="${{yPercentRoutines(0.75) + 5}}" text-anchor="end">Evening</text>`);
      svgParts.push(`<text class="axis" x="${{margin.left - 18}}" y="${{yPercentRoutines(0.25) + 5}}" text-anchor="end">Morning</text>`);
      svgParts.push(`<text class="axis" x="${{margin.left - 18}}" y="${{yPercentFitness(5 / 6) + 5}}" text-anchor="end">Other</text>`);
      svgParts.push(`<text class="axis" x="${{margin.left - 18}}" y="${{yPercentFitness(0.5) + 5}}" text-anchor="end">Run</text>`);
      svgParts.push(`<text class="axis" x="${{margin.left - 18}}" y="${{yPercentFitness(1 / 6) + 5}}" text-anchor="end">Walk</text>`);

      for (let i = 0; i < data.length - 1; i += 1) {{
        const left = data[i];
        const right = data[i + 1];
        const segments = [
          ["acuteSleep", "chronicSleep", ySleep, ((left.acuteSleep + right.acuteSleep) / 2) >= ((left.chronicSleep + right.chronicSleep) / 2), false],
          ["acuteBedtime", "chronicBedtime", yBed, ((left.acuteBedtime + right.acuteBedtime) / 2) <= ((left.chronicBedtime + right.chronicBedtime) / 2), false],
          ["acuteDrinks", "chronicDrinks", yDrinks, ((left.acuteDrinks + right.acuteDrinks) / 2) <= ((left.chronicDrinks + right.chronicDrinks) / 2), false],
          ["acuteZazen", "chronicZazen", yPercentZazen, ((left.acuteZazen + right.acuteZazen) / 2) >= ((left.chronicZazen + right.chronicZazen) / 2), false],
          ["acuteRoutine", "chronicRoutine", yPercentRoutines, ((left.acuteRoutine + right.acuteRoutine) / 2) >= ((left.chronicRoutine + right.chronicRoutine) / 2), false],
          ["acuteFitness", "chronicFitness", yPercentFitness, ((left.acuteFitness + right.acuteFitness) / 2) >= ((left.chronicFitness + right.chronicFitness) / 2), true],
        ];
        segments.forEach(segment => {{
          const path = areaSegmentPath(left, right, segment[2], segment[0], segment[1]);
          if (!path) return;
          const positiveFill = segment[4] ? "rgba(214, 98, 98, .035)" : "rgba(91, 140, 201, .07)";
          const coolingFill = segment[4] ? "rgba(91, 140, 201, .07)" : "rgba(214, 98, 98, .035)";
          const fill = segment[3] ? positiveFill : coolingFill;
          svgParts.push(`<path d="${{path}}" fill="${{fill}}"/>`);
        }});
      }}

      svgParts.push(`<path d="${{linePath(data, x, ySleep, "acuteSleep")}}" fill="none" stroke="var(--blue)" stroke-width="2.5"/>`);
      svgParts.push(`<path d="${{linePath(data, x, ySleep, "chronicSleep")}}" fill="none" stroke="var(--blue-dark)" stroke-width="3" stroke-linecap="round" stroke-dasharray="1 9"/>`);
      svgParts.push(`<path d="${{linePath(data, x, yBed, "acuteBedtime")}}" fill="none" stroke="var(--blue)" stroke-width="2.5"/>`);
      svgParts.push(`<path d="${{linePath(data, x, yBed, "chronicBedtime")}}" fill="none" stroke="var(--blue-dark)" stroke-width="3" stroke-linecap="round" stroke-dasharray="1 9"/>`);
      svgParts.push(`<path d="${{linePath(data, x, yDrinks, "acuteDrinks")}}" fill="none" stroke="var(--amber)" stroke-width="2.5"/>`);
      svgParts.push(`<path d="${{linePath(data, x, yDrinks, "chronicDrinks")}}" fill="none" stroke="var(--amber-dark)" stroke-width="3" stroke-linecap="round" stroke-dasharray="1 9"/>`);
      svgParts.push(`<path d="${{linePath(data, x, yPercentZazen, "acuteZazen")}}" fill="none" stroke="var(--purple)" stroke-width="2.5"/>`);
      svgParts.push(`<path d="${{linePath(data, x, yPercentZazen, "chronicZazen")}}" fill="none" stroke="var(--purple-dark)" stroke-width="3" stroke-linecap="round" stroke-dasharray="1 9"/>`);
      svgParts.push(`<path d="${{linePath(data, x, yPercentRoutines, "acuteRoutine")}}" fill="none" stroke="var(--gray)" stroke-width="2.5"/>`);
      svgParts.push(`<path d="${{linePath(data, x, yPercentRoutines, "chronicRoutine")}}" fill="none" stroke="var(--gray-dark)" stroke-width="3" stroke-linecap="round" stroke-dasharray="1 9"/>`);
      svgParts.push(`<path d="${{linePath(data, x, yPercentFitness, "acuteFitness")}}" fill="none" stroke="var(--red)" stroke-width="2.5"/>`);
      svgParts.push(`<path d="${{linePath(data, x, yPercentFitness, "chronicFitness")}}" fill="none" stroke="var(--red-dark)" stroke-width="3" stroke-linecap="round" stroke-dasharray="1 9"/>`);

      if (showLegends) {{
        drawLegend([
          ["Sleep Duration", "rect", "var(--bar)"],
          ["Acute Sleep", "line", "var(--blue)"],
          ["Chronic Sleep", "dot", "var(--blue-dark)"],
        ], chartSpecs[0].legendY, svgParts);
        drawLegend([
          ["Sleep Window", "rect", "var(--bar-strong)"],
          ["Inverted Window", "rect", "var(--bar-inverted)"],
          ["Acute Bedtime", "line", "var(--blue)"],
          ["Chronic Bedtime", "dot", "var(--blue-dark)"],
        ], chartSpecs[1].legendY, svgParts);
        drawLegend([
          ["Drinks", "rect", "var(--drink-bar)"],
          ["Acute Drinks", "line", "var(--amber)"],
          ["Chronic Drinks", "dot", "var(--amber-dark)"],
        ], chartSpecs[2].legendY, svgParts);
        drawLegend([
          ["Zazen Complete", "rect", "var(--purple-bar)"],
          ["Acute Zazen", "line", "var(--purple)"],
          ["Chronic Zazen", "dot", "var(--purple-dark)"],
        ], chartSpecs[3].legendY, svgParts);
        drawLegend([
          ["Routine Complete", "rect", "var(--gray-bar)"],
          ["Acute Routine", "line", "var(--gray)"],
          ["Chronic Routine", "dot", "var(--gray-dark)"],
        ], chartSpecs[4].legendY, svgParts);
        drawLegend([
          ["Fitness Activity", "rect", "var(--red-bar)"],
          ["Acute Fitness", "line", "var(--red)"],
          ["Chronic Fitness", "dot", "var(--red-dark)"],
        ], chartSpecs[5].legendY, svgParts);
      }}

      svgParts.push(`<g id="hover-layer"></g>`);
      svgParts.push(`</svg>`);
      container.innerHTML = svgParts.join("");

      const svgNode = container.querySelector("svg");
      const hoverLayer = document.getElementById("hover-layer");

      function clearHover() {{
        hoverLayer.innerHTML = "";
      }}

      function habitSegmentLabel(xPos, yPos, text, color) {{
        return `<text class="hover-label" x="${{xPos}}" y="${{yPos}}" text-anchor="middle" fill="${{color}}">${{text}}</text>`;
      }}

      function drawHover(index) {{
        const d = data[index];
        if (!d) return;

        const focusX = x(d);
        const sleepLabelX = clamp(focusX + lineLabelOffset, margin.left + 8, plotRight - 8);
        const anchor = "start";

        const sleepValues = distributeLabelYs([
          {{ key: "acuteSleep", value: d.acuteSleep, color: "var(--blue)", text: fmtHours(d.acuteSleep) }},
          {{ key: "chronicSleep", value: d.chronicSleep, color: "var(--blue-dark)", text: fmtHours(d.chronicSleep) }},
        ], ySleep, chartSpecs[0].top + 24, chartSpecs[0].top + chartSpecs[0].height - 10);
        const bedtimeValues = distributeLabelYs([
          {{ key: "acuteBedtime", value: d.acuteBedtime, color: "var(--blue)", text: fmtClockLabel(d.acuteBedtime) }},
          {{ key: "chronicBedtime", value: d.chronicBedtime, color: "var(--blue-dark)", text: fmtClockLabel(d.chronicBedtime) }},
        ], yBed, chartSpecs[1].top + 24, chartSpecs[1].top + chartSpecs[1].height - 10);
        const drinkValues = distributeLabelYs([
          {{ key: "acuteDrinks", value: d.acuteDrinks, color: "var(--amber)", text: d.acuteDrinks == null ? null : d.acuteDrinks.toFixed(1).replace(/\\.0$/, "") }},
          {{ key: "chronicDrinks", value: d.chronicDrinks, color: "var(--amber-dark)", text: d.chronicDrinks == null ? null : d.chronicDrinks.toFixed(1).replace(/\\.0$/, "") }},
        ], yDrinks, chartSpecs[2].top + 24, chartSpecs[2].top + chartSpecs[2].height - 10);
        const zazenValues = distributeLabelYs([
          {{ key: "acuteZazen", value: d.acuteZazen, color: "var(--purple)", text: d.acuteZazen == null ? null : fmtPercent(d.acuteZazen) }},
          {{ key: "chronicZazen", value: d.chronicZazen, color: "var(--purple-dark)", text: d.chronicZazen == null ? null : fmtPercent(d.chronicZazen) }},
        ], yPercentZazen, chartSpecs[3].top + 24, chartSpecs[3].top + chartSpecs[3].height - 10);
        const routineValues = distributeLabelYs([
          {{ key: "acuteRoutine", value: d.acuteRoutine, color: "var(--gray)", text: d.acuteRoutine == null ? null : fmtPercent(d.acuteRoutine) }},
          {{ key: "chronicRoutine", value: d.chronicRoutine, color: "var(--gray-dark)", text: d.chronicRoutine == null ? null : fmtPercent(d.chronicRoutine) }},
        ], yPercentRoutines, chartSpecs[4].top + 24, chartSpecs[4].top + chartSpecs[4].height - 10);
        const fitnessValues = distributeLabelYs([
          {{ key: "acuteFitness", value: d.acuteFitness, color: "var(--red)", text: d.acuteFitness == null ? null : fmtPercent(d.acuteFitness) }},
          {{ key: "chronicFitness", value: d.chronicFitness, color: "var(--red-dark)", text: d.chronicFitness == null ? null : fmtPercent(d.chronicFitness) }},
        ], yPercentFitness, chartSpecs[5].top + 24, chartSpecs[5].top + chartSpecs[5].height - 10);

        let markup = "";
        markup += `<line x1="${{focusX}}" x2="${{focusX}}" y1="${{chartSpecs[0].top}}" y2="${{chartSpecs[5].top + chartSpecs[5].height}}" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4 5"/>`;

        const dateText = fmtDate(d.dateObj);
        const dateX = clamp(focusX, margin.left + 34, plotRight - 34);
        const dateWidth = Math.max(56, dateText.length * 9 + 18);
        chartSpecs.forEach(spec => {{
          markup += `<rect x="${{dateX - dateWidth / 2}}" y="${{spec.top - 24}}" width="${{dateWidth}}" height="24" rx="12" fill="${{spec.pillFill}}" opacity=".95"/>`;
          markup += `<text class="hover-date" x="${{dateX}}" y="${{spec.top - 7}}" text-anchor="middle">${{dateText}}</text>`;
        }});

        if (d.sleepHours != null) {{
          markup += barLabel(
            focusX,
            clamp(ySleep(d.sleepHours) + 22, ySleep(d.sleepHours) + 22, ySleep(5) - 12),
            fmtHours(d.sleepHours),
            "var(--blue-dark)"
          );
        }}

        if (d.bedtimeHour != null && d.wakeHour != null) {{
          const windowTopY = Math.min(yBed(d.bedtimeHour), yBed(d.wakeHour));
          const windowBottomY = Math.max(yBed(d.bedtimeHour), yBed(d.wakeHour));
          if (d.sleepHours < 7) {{
            markup += barLabel(
              focusX,
              clamp(windowBottomY + 20, chartSpecs[1].top + 24, chartSpecs[1].top + chartSpecs[1].height - 6),
              fmtClockLabel(d.bedtimeHour),
              "var(--blue-dark)"
            );
            markup += barLabel(
              focusX,
              clamp(windowTopY - 8, chartSpecs[1].top + 20, chartSpecs[1].top + chartSpecs[1].height - 24),
              fmtClockLabel(d.wakeHour + 6),
              "var(--blue-dark)"
            );
          }} else {{
            markup += barLabel(
              focusX,
              clamp(windowBottomY - 12, windowTopY + 22, windowBottomY - 12),
              fmtClockLabel(d.bedtimeHour),
              "var(--blue-dark)"
            );
            markup += barLabel(
              focusX,
              clamp(windowTopY + 24, windowTopY + 24, windowBottomY - 12),
              fmtClockLabel(d.wakeHour + 6),
              "var(--blue-dark)"
            );
          }}
        }}

        if (d.drinks != null) {{
          markup += barLabel(
            focusX,
            clamp(yDrinks(d.drinks) + 22, yDrinks(d.drinks) + 22, yDrinks(0) - 12),
            d.drinks.toFixed(1).replace(/\\.0$/, ""),
            "var(--amber-dark)"
          );
        }}

        if (d.zazen === true) {{
          markup += habitSegmentLabel(focusX, yPercentZazen(0.5), "Sit", "var(--purple-dark)");
        }}
        if (d.morningRoutine === true) {{
          markup += habitSegmentLabel(focusX, (yPercentRoutines(0) + yPercentRoutines(0.5)) / 2, "Morning", "var(--gray-dark)");
        }}
        if (d.eveningRoutine === true) {{
          markup += habitSegmentLabel(focusX, (yPercentRoutines(0.5) + yPercentRoutines(1)) / 2, "Evening", "var(--gray-dark)");
        }}
        if (d.fitnessWalk === true) {{
          markup += habitSegmentLabel(focusX, (yPercentFitness(0) + yPercentFitness(1 / 3)) / 2, "Walk", "var(--red-dark)");
        }}
        if (d.fitnessRun === true) {{
          markup += habitSegmentLabel(focusX, (yPercentFitness(1 / 3) + yPercentFitness(2 / 3)) / 2, "Run", "var(--red-dark)");
        }}
        if (d.fitnessOther) {{
          const otherText = d.fitnessOther.length > 14 ? d.fitnessOther.slice(0, 14) + "..." : d.fitnessOther;
          markup += habitSegmentLabel(focusX, (yPercentFitness(2 / 3) + yPercentFitness(1)) / 2, otherText, "var(--red-dark)");
        }}

        [sleepValues, bedtimeValues, drinkValues, zazenValues, routineValues, fitnessValues].forEach((seriesGroup, groupIndex) => {{
          const yScales = [ySleep, yBed, yDrinks, yPercentZazen, yPercentRoutines, yPercentFitness];
          seriesGroup.forEach(item => {{
            const yy = yScales[groupIndex](d[item.key]);
            markup += hoverDot(focusX, yy, item.color);
            markup += hoverLabel(sleepLabelX, item.labelY, item.text, item.color, anchor);
          }});
        }});

        hoverLayer.innerHTML = markup;
      }}

      data.forEach((d, index) => {{
        const band = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        band.setAttribute("x", String(margin.left + index * slotWidth));
        band.setAttribute("y", String(chartSpecs[0].top));
        band.setAttribute("width", String(slotWidth));
        band.setAttribute("height", String(chartSpecs[5].top + chartSpecs[5].height - chartSpecs[0].top));
        band.setAttribute("fill", "transparent");
        band.style.cursor = "crosshair";
        band.addEventListener("mouseenter", () => drawHover(index));
        band.addEventListener("mousemove", () => drawHover(index));
        band.addEventListener("click", () => drawHover(index));
        svgNode.appendChild(band);
      }});

      svgNode.addEventListener("mouseleave", clearHover);
      clearHover();
    }}

    const allRows = rows;
    let currentRange = "7w";
    let currentShowLegends = false;
    let currentCustomStart = allRows.length ? allRows[0].date : "";
    let currentCustomEnd = allRows.length ? allRows[allRows.length - 1].date : "";

    document.getElementById("range-toggle").querySelectorAll("button").forEach(button => {{
      button.addEventListener("click", () => {{
        currentRange = button.dataset.range;
        draw(currentRange, currentShowLegends, currentCustomStart, currentCustomEnd);
      }});
    }});
    document.getElementById("legend-toggle").addEventListener("click", () => {{
      currentShowLegends = !currentShowLegends;
      draw(currentRange, currentShowLegends, currentCustomStart, currentCustomEnd);
    }});
    document.getElementById("custom-start").addEventListener("input", event => {{
      currentCustomStart = event.target.value;
      if (currentRange === "custom") draw(currentRange, currentShowLegends, currentCustomStart, currentCustomEnd);
    }});
    document.getElementById("custom-end").addEventListener("input", event => {{
      currentCustomEnd = event.target.value;
      if (currentRange === "custom") draw(currentRange, currentShowLegends, currentCustomStart, currentCustomEnd);
    }});
    draw(currentRange, currentShowLegends, currentCustomStart, currentCustomEnd);
  </script>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    payload = dashboard_payload(Path(args.data), args.fast_alpha, args.slow_alpha)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(payload), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
