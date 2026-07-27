---
name: archive-garmin-data
description: Archive the complete data currently exposed by the connected Garmin fitness service into append-only Google Drive snapshots. Use for the user's daily Garmin archive, a manual Garmin capture, recovery of rolling two-day Garmin history, verification of an archived capture, or creation and maintenance of the corresponding scheduled task.
---

# Archive Garmin Data

Preserve Garmin history that would otherwise disappear when the live connector advances beyond its rolling two-day window. Capture source responses faithfully rather than turning the archive into a summary.

## Fixed contract

- Use the connected Garmin fitness service as the source.
- Use Google Drive as the archive destination. Do not substitute Dropbox.
- Resolve the destination from the `Health Data Registry` before every capture.
- Store captures under registry asset key `garmin-archive`, currently
  `Health/01 Raw Data/Garmin Daily Archive`.
- Treat each run as an append-only snapshot. Never overwrite, replace, or silently revise an earlier capture.
- Preserve the complete rolling two-day window exposed at run time, including partial days.
- Save two independently readable artifacts: one raw JSON archive and one Markdown capture index.
- Verify both uploaded artifacts by reading their Drive metadata or contents after creation.
- Retain errors, missing-data responses, endpoint availability, and subscription-tier limitations as evidence rather than omitting them.
- Keep this daily archive contract separate from imported Garmin account exports. Never copy normalized account-export files or records into this append-only daily archive.

## Registry preflight

Read [references/health-data-registry.md](references/health-data-registry.md) before every capture,
verification, reconstruction, or scheduled-task repair. Resolve and verify `garmin-archive`
before calling Garmin or uploading anything. Use the registry row's Drive ID as the destination;
the path is a human-readable validation field, not the lookup key.

## Capture workflow

### 1. Establish the capture window

Record:

- capture time in America/Los_Angeles and UTC;
- requested and returned date range;
- source/service identity;
- whether each returned date appears complete or partial.

Request the entire rolling two-day range, not merely "today." Do not discard an older partial day when a newer day is available.

### 2. Pull everything exposed

Enumerate and call every read-only Garmin capability available in the current connector. Include, when exposed:

- daily wellness and summary metrics;
- steps, heart rate, sleep, stress, HRV, respiration, energy/body-battery, calories, intensity, and other time-series points;
- activities and detailed activity records;
- training, recovery, performance, VO2max, fitness-age, and related metrics;
- body composition and weight;
- profile or device-related data available to the connector.

Do not assume this list is exhaustive. Connector capability discovery determines the final endpoint inventory for each run.

Capture the returned payloads without normalizing away fields. For each attempted capability, store the request parameters, response payload, success or failure state, and any error or access-limit message. Do not fabricate unavailable values or retry in a way that changes the requested window.

### Directly serialize MCP responses

Build the archive programmatically from the actual MCP call results. Do not manually transcribe, translate, summarize, or reconstruct Garmin fields.

After calling the Garmin tools, create a UTF-8 JSON input bundle with this exact shape:

```json
{
  "capture": {
    "captured_at_local": "...",
    "captured_at_utc": "...",
    "timezone": "America/Los_Angeles",
    "requested_date_range": {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"},
    "returned_date_range": {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"},
    "date_completeness": {}
  },
  "calls": [
    {
      "endpoint": "get_health_summary",
      "request": {"date": "YYYY-MM-DD"},
      "result": {}
    }
  ]
}
```

Assign each actual MCP call result directly to `result`. Do not edit, translate, or extract fields from it while building this input bundle.

Then run the bundled builder; this is mandatory:

```bash
python3 scripts/build_garmin_archive.py \
  --input /absolute/path/to/garmin_mcp_calls.json \
  --output /absolute/path/to/<timestamped-archive-name>.json
```

Resolve `scripts/build_garmin_archive.py` relative to this `SKILL.md`. Do not replace it with an improvised transformation. Continue only when the script prints a JSON result with `"status": "ok"`.

The script selects `structuredContent` directly, falls back to verbatim `content`, records `isError` separately, serializes the archive, validates the serialized JSON, writes it, and parses the written file again.

For every call:

1. Retain the exact request arguments.
2. If the result has `structuredContent`, assign that value directly to the endpoint record's `response` field and serialize it with a standard JSON serializer.
3. If `structuredContent` is absent, retain the returned `content` blocks verbatim as the fallback response.
4. Record transport metadata such as `isError` separately from the response payload.
5. Derive only archive-level metadata such as endpoint name, capture timestamp, request arguments, and outcome label. Never rewrite the source payload to fit a custom health schema.

Do not store both a JSON string embedded in a text content block and the equivalent `structuredContent`; prefer `structuredContent` to avoid duplication. Validate the finished artifact with a JSON parser before upload.

### 3. Build the raw JSON artifact

Create valid UTF-8 JSON with:

- capture metadata and date coverage;
- an endpoint inventory;
- the directly serialized `structuredContent` for every call that returns it, without field-by-field translation;
- verbatim response content blocks only when structured JSON is unavailable;
- explicit records for empty, failed, unavailable, or tier-limited calls;
- a schema/version label for the archive envelope.

Use a unique timestamped filename that identifies the covered dates and capture time. Before uploading, confirm the filename does not collide with an existing file. If it does, add a deterministic suffix; never overwrite.

### 4. Build the Markdown capture index

Create a separate, human-readable Markdown file that states:

- capture timestamp and covered dates;
- the raw JSON filename;
- endpoints attempted and their outcomes;
- which dates are complete or partial;
- meaningful gaps, failures, and tier limits;
- verification status.

Keep the index factual. Do not replace raw detail with interpretation. Include Garmin attribution in user-facing health or fitness summaries.

### 5. Upload and verify

Use the registry-resolved Drive folder, then upload both artifacts. Read back each created file or its definitive metadata and verify:

- it exists under the verified `garmin-archive` Drive ID;
- its name matches the intended unique filename;
- its content is non-empty;
- the JSON parses successfully;
- the Markdown names the correct JSON artifact;
- both represent the same capture timestamp and coverage window.

Report success only after all checks pass. On partial success, preserve any successfully created artifact, clearly identify the failed step, and do not claim the capture is complete.

## Scheduled-task behavior

When creating or repairing the automation, use:

- cadence: daily;
- time: exactly 10:00 AM;
- timezone: America/Los_Angeles;
- execution instruction: perform the full workflow in this skill for the complete current rolling two-day Garmin window.

Before creating the automation, perform harmless read-only checks against the Garmin source, the
Health Data Registry, and the registry-resolved archive folder. If any requires connection or
authorization, stop for the user to connect it; do not create a task that cannot access its
required services.

The scheduled prompt must remain self-contained and preserve the fixed contract. Scheduling controls when the skill runs; it does not replace any capture or verification step.

## Downstream reconstruction

The daily archive is a freshness layer, not a replacement for imported historical Garmin account exports. For downstream analysis, the newest validated normalized account export supplies the historical baseline; overlay daily raw snapshots and the current live two-day window for freshness. Do not copy normalized exports into this archive or treat daily snapshots as the export's replacement.

When a consumer reconstructs history, it must extract compatible endpoint payloads and normalize them with the `import-garmin-account-export` skill's bundled `normalize_garmin_records.py` adapter. Merge coverage per dataset. Deduplicate only exact `stable_id` plus `canonical_record_sha256` pairs. Preserve conflicting snapshots rather than silently choosing one, preserve legitimate multiple activities, and never treat gaps as zero. Until 14 distinct archived days exist, explicitly state how many archived days are available.

## Completion response

Return a concise status containing:

- captured date range;
- whether any day was partial;
- raw JSON and Markdown filenames;
- verified Drive folder;
- endpoint failures or tier limitations;
- final state: complete, partial, or failed.
