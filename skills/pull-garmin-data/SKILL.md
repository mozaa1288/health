---
name: pull-garmin-data
description: Retrieve and validate Drive-synced daily Garmin health and activity archives. Use for recent Garmin data, date-range retrieval, archive coverage checks, or missing-date investigations.
---

# Pull Garmin Data

Retrieve raw Garmin daily archives from Google Drive — no live Garmin connection needed.

## Default contract

1. **Resolve the date(s) first.** Get the real current date/time in `America/Los_Angeles` (e.g. `TZ='America/Los_Angeles' date`) — don't assume from context. Default to today + yesterday for "the latest" with no range given.
2. **Retrieve, don't inspect.** Find and download the archive(s) (steps below), then hand off to the bundled scripts. Never `view`/`cat`/read the raw JSON directly — files run 400–500 KB and will truncate or blow context if pulled into the conversation.
3. **Let the scripts do the work.** `read_garmin_archive.py` decodes and validates; `format_garmin_markdown.py` renders the report. Run both; view only their output.
4. Deviate from this only when the user explicitly asks for raw data or a specific section.

## Where the files live

Folder `garmin-archive` — Drive ID `1PRhI2z03g_HwHXNJpfjQ7ff5Ijnk0786`
(`Health/01 Raw Data/Garmin Daily Archive`). Re-resolve via the Health Data
Registry (`Health/00 System & Governance`) only if a search against this ID
returns nothing.

Files: `garmin_YYYY-MM-DD.json`, one per local date.

## Steps

1. Search Drive scoped to the folder ID and target date(s):
   ```
   parentId = '1PRhI2z03g_HwHXNJpfjQ7ff5Ijnk0786' and (title contains 'garmin_2026-07-27' or title contains 'garmin_2026-07-28')
   ```
2. If duplicates exist, pick the newest by `pulled_at` (visible in the search result's `contentSnippet` — don't download every candidate just to compare). `modifiedTime` is a fallback tiebreaker.
3. Download the winner to disk — not through a content-returning tool.
4. Run:
   ```bash
   python scripts/read_garmin_archive.py <files>
   python scripts/format_garmin_markdown.py <files>
   ```
   Reader flags: `--json`, `--section sleep`, `--decode-to DIR`. Formatter flags: `-o file.md`, `--no-traces`.
5. Paste the formatter's Markdown output directly into the reply — no HTML, artifact, or chart image; it has to survive being copied into another assistant.

## Report contents

Comparison table (multi-day) · per-channel half-hourly traces for body battery, heart rate, stress, steps (`·` = no samples; Range is true sample extremes, not bucket averages) · sleep window and stage split · activities · a provenance line (source file, `pulled_at`, unavailable sections) — keep that line, it's how the reader knows an absence was a real absence.

## Interpreting the data

| Shape | Meaning |
|---|---|
| `{"error": "..."}` | Endpoint failed — report explicitly |
| `[]` / `{}` | Endpoint succeeded, nothing recorded — normal |
| `null` / key absent | Section missing — report as a problem |

Never render an absence as `0` or a zero-height bar. `training_readiness` and `max_metrics` are routinely empty on qualifying days — not errors. Today's file is a snapshot (`stats.wellnessEndTimeLocal` shows how far it synced) — say so rather than presenting partial totals as final. Archives currently carry a naive (offset-free) `pulled_at`; the reader flags this as a warning, not a failure — don't re-pull over it.

**Truncated reads look like empty sections, not errors** — the dangerous case. Both scripts detect it (5+ empty sections, or any of `stats`/`sleep`/`heart_rate`/`stress`/`steps` empty) and refuse to report. Re-download and re-run; `--allow-partial` is for inspection only and will misreport data.

## Local collector (not the retrieval path)

`scripts/pull_garmin_data.py` runs on a trusted local machine with `garminconnect` 0.3.5+ and an existing `~/.garminconnect` token store — it's the upstream collector that populates Drive, not how data is retrieved here.

```bash
python scripts/pull_garmin_data.py
python scripts/pull_garmin_data.py --start-date 2026-07-01 --end-date 2026-07-28
```

Never commit the token store or raw archives to GitHub.
