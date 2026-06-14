---
name: daily-metrics-logging
description: Use daily metrics logging when Pavel shares 'heartbeat' statistics of sleep, bedtime, drinks, routines, or zazen for specific dates, or when the agent needs summary stats for preset or custom date ranges.
---

# Daily Metrics Logging

Daily Metrics Logging is Parker's canonical workflow for recording private heartbeat metrics and for retrieving dashboard-mirrored summary stats without exposing or hand-editing the underlying storage file.

## Operating Contract

- During normal logging or summary lookup, Parker should not open, inspect, or summarize the private metrics CSV directly. Use the command interface instead.
- Canonical storage leaves drinks at `0` and false activity booleans (routines, zazen, fitness flags) blank rather than writing explicit `0`/`no` values.
- Use this skill for recording or correcting data values for a date, redrawing the dashboard, or retrieving summary stats for review/planning conversations; not for changing dashboard code, formulas, or storage design.
- Treat unspecified fields as "leave unchanged." Do not clear an existing field unless Pavel explicitly asks to blank it out.
- A normal metrics write refreshes the dashboard automatically.
- Do not run multiple metrics writes in parallel. The logging script uses a file lock to defend against accidental concurrent calls, but Parker should still issue daily logging commands sequentially so outcomes are easy to inspect and reason about.
- You may call the standalone dashboard redraw command without modifying data first.
- In dashboard trends, missing non-sleep values on past rows are treated as `0` / no activity. Missing sleep remains unknown, and missing non-sleep values on the latest row remain unknown because the day may still be incomplete.
- There is no need to proactively offer setting any routines or fitness to "nothing" because that is the default.

## Commands

Run commands from the project root.

Primary logging command:

```bash
.agents/skills/daily-metrics-logging/scripts/log-daily-metrics.py --date YYYY-MM-DD [fields...]
```

Standalone redraw command:

```bash
.agents/skills/daily-metrics-logging/scripts/render-sleep-dashboard.py
```

Summary command:

```bash
.agents/skills/daily-metrics-logging/scripts/summarize-daily-metrics.py --preset 1w
```

Weekly review heartbeat block command:

```bash
.agents/skills/daily-metrics-logging/scripts/summarize-daily-metrics.py --weekly-review-markdown
```

Optional anchored form for an as-of date:

```bash
.agents/skills/daily-metrics-logging/scripts/summarize-daily-metrics.py --weekly-review-markdown --end YYYY-MM-DD
```

The logging command inserts a new row for the date if none exists, or updates the existing row for that date while preserving any fields not provided in the command. After a successful write, it redraws the dashboard automatically.

The summary command returns dashboard-mirrored averages for a preset or custom range without modifying data.

The weekly review heartbeat command returns the preformatted Markdown fenced text block used by the habits weekly review, comparing last 7 days (`1w`) against previous 7 days (`pw`). With `--end YYYY-MM-DD`, it instead compares the 7-day window ending on that date against the preceding 7 days.

## Accepted Fields

- `--date YYYY-MM-DD`
  Example: `2026-05-02`
  Defaults to today's local date if omitted.

- `--bedtime HH:MM`
  Use 24-hour `HH:MM`.
  Examples: `22:40`, `00:30`, `01:15`

- `--wake HH:MM`
  Use 24-hour `HH:MM`.
  Examples: `06:10`, `07:30`, `08:00`

- `--drinks NUMBER`
  Use decimal alcohol units.
  Examples: `0`, `1.5`, `3.5`, `4`
  Canonical storage keeps `0` as blank.

- `--morning-routine BOOL`
- `--evening-routine BOOL`
- `--zazen BOOL`
- `--fitness-walk BOOL`
- `--fitness-run BOOL`
  Accepted boolean values:
  `1`, `0`, `yes`, `no`, `true`, `false`, `y`, `n`
  Canonical storage keeps false values blank and stores only positive activity as explicit `yes`.

- `--fitness-other TEXT`
  Free text for other activity.
  Examples: `Pilates`, `yard work`, `walk`
  Any non-empty text counts as an "other" fitness activity in the dashboard.

- `--notes TEXT`
  Free text note for that date.

## Common Patterns

Sleep only:

```bash
.agents/skills/daily-metrics-logging/scripts/log-daily-metrics.py --date 2026-05-02 --bedtime 22:40 --wake 06:10
```

Add drinks and zazen later without disturbing sleep:

```bash
.agents/skills/daily-metrics-logging/scripts/log-daily-metrics.py --date 2026-05-02 --drinks 1.5 --zazen yes
```

Record routines and fitness:

```bash
.agents/skills/daily-metrics-logging/scripts/log-daily-metrics.py --date 2026-05-02 --morning-routine yes --evening-routine no --fitness-walk yes --fitness-other "yard work"
```

Redraw only:

```bash
.agents/skills/daily-metrics-logging/scripts/render-sleep-dashboard.py
```

Last 7 days summary:

```bash
.agents/skills/daily-metrics-logging/scripts/summarize-daily-metrics.py --preset 1w
```

Previous 7 days summary as JSON:

```bash
.agents/skills/daily-metrics-logging/scripts/summarize-daily-metrics.py --preset pw --json
```

Weekly review heartbeat block:

```bash
.agents/skills/daily-metrics-logging/scripts/summarize-daily-metrics.py --weekly-review-markdown
```

Weekly review heartbeat block anchored to a specific end date:

```bash
.agents/skills/daily-metrics-logging/scripts/summarize-daily-metrics.py --weekly-review-markdown --end 2026-06-06
```

Custom range summary:

```bash
.agents/skills/daily-metrics-logging/scripts/summarize-daily-metrics.py --start 2026-05-01 --end 2026-05-20
```

## Parker Workflow

### Logging Data

1. Determine the target date. If Pavel says "yesterday" or similar, resolve it before calling the command. If Pavel describes sleep as "slept from ... to ...", "I slept ...", or similar and says "last night" or gives no explicit date, log the sleep against yesterday's date, because the row represents the date the sleep began.
2. Translate the shared facts into command flags using the formats above.
3. Include only the fields Pavel actually provided or corrected. Do not infer or write `no` for omitted activity-style boolean fields (routines, zazen, fitness); omission means leave the stored value unchanged.
4. Run `.agents/skills/daily-metrics-logging/scripts/log-daily-metrics.py` once per date, sequentially. Do not use parallel tool calls for multiple writes to the metrics CSV.
5. Confirm what was recorded in natural language without dumping the private store.
6. If the task is redraw-only, run `.agents/skills/daily-metrics-logging/scripts/render-sleep-dashboard.py` directly instead of the logging command.

### Reading Data

If you need to retrieve averages such as last 7 days vs previous 7 days, past 4 weeks, past 7 weeks, or a custom metrics summary for review/planning, run `.agents/skills/daily-metrics-logging/scripts/summarize-daily-metrics.py` rather than reading the CSV or scraping the HTML.

Use the default text output for normal summary lookups. Do not use `--json` unless Pavel explicitly asks for JSON or you are debugging the summary workflow.

If Pavel wants the compact weekly-review heartbeat block, use `--weekly-review-markdown` instead of assembling it manually. If he wants it as of a specific date, add `--end YYYY-MM-DD`.

When retrieving or reporting summaries, note that the CLI intentionally mirrors current dashboard semantics: `1w` and `pw` are anchored to today/yesterday logic, while `4w` and `7w` are anchored to the latest data row.

## Boundaries

- Do not read the private metrics file during ordinary logging or summary lookup unless debugging a broken workflow or Pavel explicitly asks to inspect the stored data.
- Do not use this skill for dashboard project development; resume the sleep dashboard project instead.
- If the command cannot import its helpers or cannot write output, do not hand-edit the CSV. First confirm the command was run from the project root and that the bundled skill scripts are present.
- If future dashboard range or averaging semantics change, update the summary command in lockstep so Parker's programmatic summaries keep mirroring the dashboard.
