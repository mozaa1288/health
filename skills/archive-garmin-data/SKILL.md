---
name: archive-garmin-data
description: Archive the complete rolling Garmin data window into append-only Google Drive snapshots. Use for daily Garmin archiving, manual captures, archive verification, or repairing the daily archive task.
---

# Archive Garmin Data

Preserve the complete rolling two-day window exposed by the connected Garmin service. Save raw source responses, not a rewritten health summary.

## Workflow

1. Resolve `garmin-archive` through the live Health Data Registry and verify the returned Drive folder. Do not use a same-named folder found by search.
2. Record the capture time in `America/Los_Angeles` and UTC, the requested date range, and which dates appear complete or partial.
3. Discover and call every read-only Garmin capability available in the current connector. Keep each request and its complete result, including empty responses, failures, unavailable endpoints, and tier limitations.
4. Build a JSON input bundle with capture metadata and one record per Garmin call. Assign the actual tool response directly to each call record; do not manually transcribe or normalize fields.
5. Run the bundled builder:

```bash
python3 scripts/build_garmin_archive.py \
  --input garmin_mcp_calls.json \
  --output <unique-timestamped-name>.json
```

Continue only when the script reports `status: ok`.

6. Create a short Markdown index containing the capture time, covered dates, JSON filename, endpoint outcomes, partial-day notes, failures, and verification status.
7. Upload both files to the verified `garmin-archive` folder. Use unique timestamped names and never overwrite an earlier capture.
8. Read both files or their definitive metadata back and verify the parent folder, names, nonempty content, matching capture window, valid JSON, and correct Markdown-to-JSON reference.

## Rules

- Google Drive is the archive destination; do not substitute another service.
- Keep daily snapshots separate from normalized Garmin account exports.
- Preserve raw response structure and errors as evidence.
- Do not fabricate unavailable values or treat missing data as zero.
- Partial success is partial, not complete; preserve any valid artifact and identify the failed step.

## Scheduled task

The standard task runs daily at 10:00 AM in `America/Los_Angeles` and performs this complete workflow for the current rolling two-day window. The task prompt should simply point to this repository skill as the authoritative workflow.

## Response

Report the covered dates, partial-day status, JSON and Markdown filenames, verified folder, endpoint failures or limitations, and final state: complete, partial, or failed.
