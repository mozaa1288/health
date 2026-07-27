---
name: import-garmin-account-export
description: Validate, inventory, normalize, and register a Garmin account-data export ZIP as an immutable historical snapshot in the user's Google Drive health-data system. Use when the user provides a Garmin data dump, requests historical Garmin import or backfill, wants Garmin export data made usable by other health skills, or asks to refresh the registered Garmin account-export baseline.
---

# Import Garmin Account Export

Turn a Garmin account export into a private, immutable raw snapshot plus validated, privacy-reduced JSONL datasets that downstream skills can consume.

## Read the contract

Read [references/export-contract.md](references/export-contract.md) before importing, registering, replacing, or consuming an account export.

## Import an export

1. Resolve and verify `raw-folder`, `garmin-account-exports`, and `health-data-registry` from the Health Data Registry. On the first import only, create `Health/01 Raw Data/Garmin Account Exports`, then register it before treating it as authoritative.
2. Fetch the source ZIP without expanding it into Drive. Record its Drive ID, name, byte size, and SHA-256 digest.
3. Run the bundled importer into a new local output directory:

```bash
python scripts/import_garmin_account_export.py \
  --input garmin-export.zip \
  --output-dir normalized-export \
  --snapshot-date YYYY-MM-DD \
  --source-drive-id DRIVE_FILE_ID
```

Resolve the script relative to this skill directory when the working directory differs.

4. Require a zero exit code and a manifest with `validation.status: validated`. Stop on ZIP corruption, unsafe paths, JSON parse failures in supported datasets, output-hash mismatch, or a pre-existing nonempty output directory.
5. Create an append-only Drive snapshot:

```text
Health/01 Raw Data/Garmin Account Exports/YYYY-MM-DD/
├── Original/
│   └── YYYY-MM-DD_garmin_account_export.zip
├── Normalized/
│   └── *.jsonl
├── catalog.md
└── manifest.json
```

6. Preserve the original ZIP bytes and Drive ID when moving an already-uploaded file. If Drive denies write access to that source file, leave it untouched and upload a byte-identical snapshot copy; record both Drive IDs and the shared SHA-256 in the manifest and change log. Never replace a prior snapshot or unpack sensitive identity, ECG, media, course, or FIT files into Drive.
7. Upload every generated normalized file, `catalog.md`, and `manifest.json`. Verify each file's live parent, name, size, and digest where available.
8. Append a registry change-log entry. Do not change `garmin-archive`; it remains the separate daily freshness source.
9. Report dataset counts, trustworthy date coverage, skipped placeholders, conflicts, and anomalies. Explicitly disclose that FIT data is inventoried rather than decoded.

## Consumer resolution

Use the newest fully validated snapshot as the historical baseline. Verify the manifest and every listed artifact hash before reading JSONL.

Overlay later daily Garmin archive captures and the live connector window per dataset, not from one global coverage date. Extract each compatible raw endpoint payload and normalize it with `scripts/normalize_garmin_records.py`. Deduplicate exact records by `stable_id` plus `canonical_record_sha256`. When the same stable ID has different canonical hashes, preserve the conflict and prefer the newest successful capture only for a derived decision, with a disclosure. Never turn missing data into zero.

Do not use future-dated records listed in `anomalies` as coverage or as planning evidence. Do not read the original ZIP when normalized data satisfies the task.

## Bundled tooling

`scripts/import_garmin_account_export.py` is the authoritative deterministic importer. It uses only the Python standard library, validates paths and ZIP integrity, removes direct account/device/GPS identifiers from consumer records, and writes provenance-bearing JSONL.

`scripts/normalize_garmin_records.py` applies the same identity, privacy, and canonical-hash rules to a compatible raw daily-archive endpoint or live connector payload before cross-layer merging.
