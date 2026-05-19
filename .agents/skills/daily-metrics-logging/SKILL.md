---
name: daily-metrics-logging
description: Use daily metrics logging when Pavel shares statisticts (also refered to as heartbeat) about bedtime, wake time, drinks, routines, zazen, and fitness for specific dates.
---

# Daily Metrics Logging

Daily Metrics Logging is Parker's canonical workflow for recording one day of private metrics without exposing or hand-editing the underlying storage file.

## Operating Contract

- During normal logging, Parker should not open, inspect, or summarize the private metrics CSV. Use the command interface instead.
- Use this skill for recording or correcting data values for a date, not for changing dashboard code, formulas, or storage design.
- Treat unspecified fields as "leave unchanged." Do not clear an existing field unless Pavel explicitly asks to blank it out.
- A normal metrics write refreshes the dashboard automatically.
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

The logging command inserts a new row for the date if none exists, or updates the existing row for that date while preserving any fields not provided in the command. After a successful write, it redraws the dashboard automatically.

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

- `--morning-routine BOOL`
- `--evening-routine BOOL`
- `--zazen BOOL`
- `--fitness-walk BOOL`
- `--fitness-run BOOL`
  Accepted boolean values:
  `1`, `0`, `yes`, `no`, `true`, `false`, `y`, `n`

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

## Parker Workflow

1. Determine the target date. If Pavel says "yesterday" or similar, resolve it before calling the command. If Pavel describes sleep as "slept from ... to ...", "I slept ...", or similar and says "last night" or gives no explicit date, log the sleep against yesterday's date, because the row represents the date the sleep began.
2. Translate the shared facts into command flags using the formats above.
3. Include only the fields Pavel actually provided or corrected. Do not infer or write `no` for omitted activity-style boolean fields (routines, zazen, fitness); omission means leave the stored value unchanged.
4. Run `.agents/skills/daily-metrics-logging/scripts/log-daily-metrics.py`.
5. Confirm what was recorded in natural language without dumping the private store.
6. If the task is redraw-only, run `.agents/skills/daily-metrics-logging/scripts/render-sleep-dashboard.py` directly instead of the logging command.

## Boundaries

- Do not read the private metrics file during ordinary logging unless debugging a broken workflow or Pavel explicitly asks to inspect the stored data.
- Do not use this skill for dashboard project development; resume the sleep dashboard project instead.
- If the command cannot import its helpers or cannot write output, do not hand-edit the CSV. First confirm the command was run from the project root and that the bundled skill scripts are present.
