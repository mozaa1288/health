---
name: pull-garmin-data
description: Retrieve and validate Drive-synced daily Garmin health and activity archives. Use for recent Garmin data, date-range retrieval, archive coverage checks, or missing-date investigations.
---

# Pull Garmin Data

Retrieve raw Garmin daily archives from Google Drive. Google Drive is the normal
retrieval source — no Garmin account export or live Garmin connection is needed.

## Where the files live

Folder `garmin-archive` — **Drive ID `1PRhI2z03g_HwHXNJpfjQ7ff5Ijnk0786`**
(`Health/01 Raw Data/Garmin Daily Archive`), schema `garmin_mcp_daily_archive.v1`.

Use that ID directly. Only re-resolve it through the Health Data Registry
(`Health/00 System & Governance`) if a search against it returns nothing, which
means the folder moved.

Files are named `garmin_YYYY-MM-DD.json`, one per local date.

## Workflow

1. **Pick dates** in `America/Los_Angeles`. Default to today and yesterday when
   asked for "the latest" with no range given.

2. **Find the files** with a single scoped search:

   ```
   parentId = '1PRhI2z03g_HwHXNJpfjQ7ff5Ijnk0786' and (title contains 'garmin_2026-07-27' or title contains 'garmin_2026-07-28')
   ```

3. **Pick the newest file per date** if duplicates exist. `pulled_at` is the
   second line of every archive, so it appears in the search result's
   `contentSnippet` — compare those and download only the winner. Do not
   download every candidate just to read its timestamp. Drive `modifiedTime` is
   a usable tiebreaker but `pulled_at` wins where the two disagree.

4. **Download to disk, not into context.** These archives are 400–500 KB. Tools
   that return file *content* cap their output and will hand back truncated JSON.
   Save the file to the working directory and let the scripts read it from disk.
   Never paste an archive's content through a content-returning tool and then
   parse what came back.

5. **Decode and validate** with the bundled reader, which accepts the raw
   archive, the Drive tool-result envelope, or the inner base64 object without
   any manual unwrapping:

   ```bash
   python scripts/read_garmin_archive.py <downloaded files>
   ```

   It prints a side-by-side metric table, per-day activities, unavailable
   sections, and any validation problems. Useful flags:

   - `--json` — machine-readable summary for downstream skills
   - `--section sleep` — dump one raw section verbatim
   - `--decode-to DIR` — write the decoded raw archives to disk

   Exit code is `1` when any file has a fatal problem, `0` otherwise.

6. **Report** with the formatter, which emits plain Markdown — tables and text
   only, so it pastes natively into ChatGPT, Gemini, Slack, or Notion with no
   rendering layer:

   ```bash
   python scripts/format_garmin_markdown.py <files>            # to stdout
   python scripts/format_garmin_markdown.py <files> -o day.md  # to a file
   python scripts/format_garmin_markdown.py <files> --no-traces
   ```

   Paste its output directly into the reply. Do not build an HTML page, an
   artifact, or a chart image — the report has to survive being copied into
   another assistant.

## What the report contains

- **Comparison table** across days (only when more than one day is pulled).
- **Through the day** — one row per channel (body battery, heart rate, stress,
  steps), drawn with block characters at half-hour resolution and split into
  four six-hour columns so time position is readable without a monospace font.
  `·` marks a half hour with no samples. The Range column reports true sample
  extremes, not bucket averages, so smoothing never hides a real peak.
- **Sleep** — window plus stage split with durations and percentages.
- **Activities** — name, type, duration, distance.
- **Provenance line** — source file, `pulled_at`, and unavailable sections.
  Keep this. It is how the reader knows an absence was an absence.

Partial same-day pulls are labeled with the local sync time at the top of the
day's section.

## Reading the payload

Every archive carries these 17 sections: `stats`, `user_summary`, `sleep`,
`heart_rate`, `stress`, `body_battery`, `steps`, `hrv`, `respiration`, `spo2`,
`max_metrics`, `training_status`, `training_readiness`, `body_composition`,
`weigh_ins`, `daily_weigh_ins`, `activities`. Preserve and return them raw —
never reshape or rename them.

**Distinguishing failures from real absences.** The collector wraps every
endpoint call, so a failed call is stored as a dict with an `error` key and
nothing else:

```json
"hrv": {"error": "HTTPError: 500 Server Error"}
```

That — and only that — is an endpoint failure. Everything else is a real
absence of data:

| Shape | Meaning |
|---|---|
| `{"error": "..."}` | Endpoint failed. Report it explicitly. |
| `[]` or `{}` | Endpoint succeeded, Garmin had nothing. Normal. |
| `null` / key absent | Section missing. Report as a data problem. |
| Nested `null` fields | Metric not recorded that day. Not zero. |

Never render an unavailable value as `0`, and never as a zero-height bar in the
trace rows — the formatter uses `·` for that. `training_readiness` is routinely
empty, and `max_metrics` is empty on days with no qualifying activity — neither
is an error.

**Partial same-day data.** Today's file is a snapshot, not a complete day.
`stats.wellnessEndTimeLocal` shows how far the watch had synced; say so when
reporting a same-day pull rather than presenting partial totals as final.

**Known discrepancy.** Archives currently in Drive have a naive (offset-free)
`pulled_at`, which the collector's own validator would flag. The reader treats
this as a warning, not a failure. Do not re-pull over it.

## Truncated reads

A truncated download does not look like an error — it looks like empty sections,
which under the table above means "Garmin had nothing." That is the one failure
mode that silently corrupts a report: the day's real numbers get published as
absences, and whatever reads the report fills the gaps on its own.

Both scripts guard against it. If any of `stats`, `sleep`, `heart_rate`,
`stress`, or `steps` is empty — or five or more sections are empty at once — the
reader raises `SUSPECTED TRUNCATED READ` and the formatter withholds the report
entirely rather than rendering a plausible-looking one.

When that fires, re-download the file to disk and re-run. Do not work around it
by reporting the sections as unavailable. `--allow-partial` exists for
inspection only and will misreport data.

## Local collector

`scripts/pull_garmin_data.py` is the upstream collector, not the retrieval path.
Run it on a trusted local machine with `garminconnect` 0.3.5+ and the existing
`~/.garminconnect` token store:

```bash
python scripts/pull_garmin_data.py
python scripts/pull_garmin_data.py --start-date 2026-07-01 --end-date 2026-07-28
```

It writes daily files atomically; Google Drive Desktop or a separate
`rclone copy` syncs them to the registered folder. Never commit the token store,
temporary files, or raw Garmin archives to GitHub.
