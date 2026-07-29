---
name: pull-garmin-data
description: Retrieve and validate Drive-synced daily Garmin health and activity archives. Use for recent Garmin data, date-range retrieval, archive coverage checks, or missing-date investigations.
---

# Pull Garmin Data

Pull Garmin data from the Google Drive folder registered as `garmin-archive`.

## Workflow

1. Resolve `garmin-archive` through the Health Data Registry and verify the registered Google Drive folder.
2. Determine the requested dates in `America/Los_Angeles`. Default to today and yesterday when the user asks for the latest data without a range.
3. Find files named:

```text
garmin_YYYY-MM-DD.json
```

4. For each date, use the newest valid file by timezone-aware `pulled_at`. Require the filename date to match the top-level `date`.
5. Preserve and return the raw sections, including `stats`, `user_summary`, `sleep`, `heart_rate`, `stress`, `body_battery`, `steps`, `hrv`, `respiration`, `spo2`, `max_metrics`, `training_status`, `training_readiness`, `body_composition`, `weigh_ins`, `daily_weigh_ins`, and `activities`.
6. Treat endpoint errors, missing sections, empty payloads, null fields, and missing dates as unavailable data—not zero.
7. Report the files used, their `pulled_at` timestamps, available sections, endpoint failures, and any missing dates.

Do not require a Garmin account export or a live Garmin connection. Google Drive is the normal retrieval source.

## Local collector

The included script is the upstream collector, not the normal ChatGPT retrieval path. Run it separately on a trusted local machine with `garminconnect` 0.3.5 or newer and the existing `~/.garminconnect` token store:

```bash
python scripts/pull_garmin_data.py
python scripts/pull_garmin_data.py --start-date 2024-07-29 --end-date 2026-07-28
```

The script atomically writes the daily files. Google Drive Desktop or a separate `rclone copy` task syncs them to the registered Drive folder. Never commit the token store, temporary files, or raw Garmin archives to GitHub.
