# Radar scheduling

## Principle: no home-grown scheduler

`scripts/run_radar.py` is a **one-shot**: it executes one run and then exits.
Periodicity is delegated to the OS scheduler. Reimplementing a
scheduler (loop, `while True: sleep`, drift handling, persistence of the
next triggers…) would be redundant, fragile and untested — cron and
Task Scheduler already do this work robustly and under supervision.

## Linux / macOS — cron

Example: every day at 08:00, with logs.

```cron
0 8 * * * cd /opt/radar && uv run python scripts/run_radar.py >> /var/log/radar.log 2>&1
```

Secrets come from the service environment (or from a `.env` loaded by a
wrapper) — **never** in plain text in a shared crontab.

## Windows — Task Scheduler

```bat
schtasks /Create /SC DAILY /ST 08:00 /TN "RadarRun" ^
  /TR "cmd /c cd /d C:\radar && uv run python scripts\run_radar.py >> logs\radar.log 2>&1"
```

The variables (`ANTHROPIC_API_KEY`, `FEED_URLS`, `STORE_DIR`) are defined at
the **User** or **System** level, outside the repository.

## Network error handling: skip + continue (decision)

When fetching a feed fails (network, HTTP, malformed XML), we **skip that
feed and continue** with the others, rather than **abort** the whole run. A
radar is multi-source: a dead or slow feed must not cancel the collection of
the others. The decision is implemented in the fetcher of the composition
root (`_make_feed_fetcher`, `except (OSError, ParseError): continue`).

**Code bugs** (outside network I/O/parsing), on the other hand, deliberately
propagate.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success — `PipelineReport` written to the report file (JSON, UTF-8). |
| `2` | Missing configuration (e.g. `ANTHROPIC_API_KEY`) — clear message on stderr. |
| `3` | Alert (module 3.4) — run cost or LLM failures above the threshold — message on stderr. The report is still written. |
| other / traceback | Unhandled error — visible in the logs, the scheduler can alert. |

The scheduler (cron/Task Scheduler) can rely on this exit code to
notify or retry.
