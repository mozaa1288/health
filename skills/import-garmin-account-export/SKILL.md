---
name: import-garmin-account-export
description: Validate and normalize a Garmin account-data export ZIP into an immutable historical snapshot in Google Drive. Use for historical Garmin imports, backfills, or refreshing the registered account-export baseline.
---

# Import Garmin Account Export

Convert a Garmin export ZIP into one preserved raw snapshot plus normalized JSONL datasets for downstream health workflows.

## Import workflow

1. Resolve `garmin-account-exports` through the live Health Data Registry. On the first import, create and register the folder before using it.
2. Obtain the source ZIP and record its Drive ID, filename, size, and SHA-256 digest.
3. Run the bundled importer into a new empty local directory:

```bash
python scripts/import_garmin_account_export.py \
  --input garmin-export.zip \
  --output-dir normalized-export \
  --snapshot-date YYYY-MM-DD \
  --source-drive-id DRIVE_FILE_ID
```

4. Require a zero exit code and a manifest with `validation.status: validated`. Stop on corrupt ZIPs, unsafe paths, supported JSON parse failures, hash mismatches, or a nonempty output directory.
5. Store the snapshot under a unique date folder containing:

```text
Original/<date>_garmin_account_export.zip
Normalized/*.jsonl
catalog.md
manifest.json
```

6. Preserve the original ZIP bytes. Never overwrite an earlier snapshot or unpack sensitive identity, media, GPS, ECG, course, or FIT files into Drive. FIT files may be inventoried without being decoded.
7. Upload the normalized files, catalog, and manifest, then verify their names, parents, sizes, and hashes where available.
8. Register the snapshot and report dataset counts, date coverage, skipped data, conflicts, and anomalies.

## Using imported history

Use the newest fully validated snapshot as the historical baseline. Verify the manifest and listed hashes before reading normalized files.

For newer daily-archive or live Garmin payloads, run `scripts/normalize_garmin_records.py`, merge coverage per dataset, and deduplicate only exact `(stable_id, canonical_record_sha256)` pairs. Preserve conflicting hashes and legitimate multiple activities. Missing data remains unknown, and future-dated anomalies are excluded from coverage and planning.

Keep the historical export separate from the append-only daily Garmin archive.
