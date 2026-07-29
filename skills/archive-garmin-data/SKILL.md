---
name: archive-garmin-data
description: Verify and use the per-day Garmin JSON archives produced by the user's external python-garminconnect collector. Use for archive checks, coverage audits, missing-day investigations, or confirming that the laptop cron output has synced to Google Drive.
---

# Archive Garmin Data

The external laptop collector is the default Garmin source. It writes one raw JSON file per local date and syncs those files into the registered Google Drive `garmin-archive` folder. Normal runs do not require the live Garmin connector.

## Expected file format

Files are named:

```text
garmin_YYYY-MM-DD.json
```

Each file must contain:

- `date` matching the filename;
- `pulled_at` as an ISO timestamp;
- raw endpoint sections such as `stats`, `user_summary`, `sleep`, `heart_rate`, `stress`, `body_battery`, `steps`, `hrv`, `respiration`, `spo2`, `max_metrics`, `training_status`, `training_readiness`, `body_composition`, `weigh_ins`, `daily_weigh_ins`, and `activities`.

A missing section or `{"error": "..."}` means unavailable data, not zero. Preserve raw payloads and errors as evidence.

## Workflow

1. Resolve `garmin-archive` through the live Health Data Registry and verify the returned Drive folder.
2. Read the relevant `garmin_YYYY-MM-DD.json` files directly from that folder.
3. Verify that each file parses, its filename date matches `date`, and `pulled_at` is valid.
4. When more than one file covers a date, use the one with the newest valid `pulled_at` while preserving older copies as history.
5. Treat the current local day as partial. Prefer a refreshed copy of yesterday after the day has closed.
6. Report missing dates, endpoint errors, empty datasets, and stale files plainly.

## Source precedence

For Garmin analysis, use sources in this order:

1. Synced per-day collector files from `garmin-archive`.
2. The newest validated Garmin account export only to fill dates or datasets missing from the daily files.
3. The live Garmin connector only for same-day freshness when the collector file has not synced yet, or when the user explicitly requests a live refresh.

Do not replace successful daily-file data with connector summaries. Do not treat missing fields as zero.

## Collector behavior

The collector should refresh today and yesterday on each run, because a file created during the day is incomplete. It may skip older nonempty dates. Once a date has been refreshed after the following day begins, treat it as the stable daily archive.

The bundled `scripts/build_garmin_archive.py` remains available only for an explicit manual connector capture. It is not part of the default workflow.

## Response

Report the date coverage, newest pull time, missing or stale dates, endpoint errors, verified Drive folder, and whether the archive is ready for downstream use.