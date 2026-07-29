---
name: import-garmin-account-export
description: Validate and normalize a Garmin account-data export ZIP into an immutable historical snapshot in Google Drive. Use for historical Garmin imports, backfills, or filling gaps not covered by the synced daily Garmin archive.
---

# Import Garmin Account Export

Convert a Garmin export ZIP into one preserved raw snapshot plus normalized JSONL datasets for fallback historical coverage.

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

## Source role

The synced `garmin_YYYY-MM-DD.json` files in `garmin-archive` are the default Garmin history. An account export is supplemental and may fill only dates or datasets that are absent or unusable in the daily archive.

For a date and dataset with a valid daily archive payload, prefer the daily file. Do not replace it merely because an export record is available.

When combining sources:

1. Verify the export manifest and listed hashes.
2. Extract the relevant top-level dataset from each daily file.
3. Run `scripts/normalize_garmin_records.py` separately for each compatible dataset payload.
4. Deduplicate only exact `(stable_id, canonical_record_sha256)` pairs.
5. Preserve conflicting hashes and legitimate multiple activities.
6. Treat missing data and `{ "error": ... }` payloads as unknown.
7. Exclude future-dated anomalies from coverage and planning.

Keep imported exports separate from the per-day Garmin archive.
