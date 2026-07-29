---
name: pull-garmin-data
description: Pull daily Garmin health and activity data into one raw JSON file per local date. Use on a trusted local machine with python-garminconnect access for daily refreshes, historical backfills, or repairing missing Garmin archive dates.
---

# Pull Garmin Data

Run this workflow only on a trusted local machine that has the user's Garmin token store and permission to write the local archive folder. ChatGPT-hosted runtimes generally cannot access those credentials or local paths.

## Default behavior

1. Authenticate with the existing `python-garminconnect` token store using `garminconnect` 0.3.5 or newer. Keep the token store readable only by the local user.
2. Refresh today and yesterday in `America/Los_Angeles`.
3. Preserve one raw file per date:

```text
garmin_YYYY-MM-DD.json
```

4. Write files atomically so an interrupted pull cannot leave a truncated archive.
5. Keep endpoint errors inline as `{"error": "..."}`. Missing or failed data is unknown, not zero.
6. Never commit credentials, tokens, cookies, temporary files, or raw Garmin archive files to GitHub.
7. Let Google Drive for desktop or a separate `rclone copy` task sync the completed JSON files. This skill pulls Garmin data; it does not manage cloud synchronization.

## Run

From this skill directory:

```bash
python scripts/pull_garmin_data.py
```

Useful options:

```bash
# Refresh the last seven dates
python scripts/pull_garmin_data.py --days 7

# Backfill an exact range
python scripts/pull_garmin_data.py   --start-date 2024-07-29   --end-date 2026-07-28

# Replace every existing file in a range
python scripts/pull_garmin_data.py --days 30 --force
```

The output directory defaults to `%USERPROFILE%\Documents\Health\Daily_Archives` on Windows and can be overridden with `--output-dir` or `GARMIN_ARCHIVE_DIR`.

For a large backfill, keep a nonzero `--delay-seconds` value and rerun dates that report endpoint failures rather than treating missing results as zero.

## Validation

For each written file verify:

- valid JSON;
- filename date equals top-level `date`;
- timezone-aware `pulled_at`;
- expected endpoint sections are present;
- the file is nonempty.

Report dates written, dates skipped, endpoint failures, and the output directory.
