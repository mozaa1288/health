# Health Data Registry

## Registry

- Google Sheet: `Health Data Registry`
- Drive ID: `1AHvwyDzlhznRFvAry5Tqj37Ol9w5HOOhES4htrqoXjE`
- Canonical path: `Health/00 System & Governance/Health Data Registry`
- Layout schema: `health_drive_layout.v1`
- Asset tab: `Assets`
- Columns `A:K`: `Asset Key`, `Name`, `Kind`, `Drive ID`, `Canonical Path`,
  `Schema Version`, `Primary Writer`, `Write Policy`, `Status`, `Last Verified`, `Notes`

Read spreadsheet metadata first, then the bounded populated region of `Assets`. Match `Asset Key`
exactly. Require one matching row and verify its Drive metadata before using it. Stop when the row
is missing or duplicated, `Status` is not `Active`, the Drive ID cannot be read, or the ID and
metadata disagree. Do not substitute a same-named file found elsewhere.

## Garmin archive asset

Require:

- Asset Key: `garmin-archive`
- Kind: `Folder`
- Schema Version: `garmin_mcp_daily_archive.v1`
- Write Policy: `Append-only`
- Current Drive ID: `1PRhI2z03g_HwHXNJpfjQ7ff5Ijnk0786`
- Current path: `Health/01 Raw Data/Garmin Daily Archive`

Use the row's live Drive ID after validation. Treat the current ID and path above as expected
migration-state checks, not permission to bypass the registry. If the registry intentionally
changes the ID later, accept the new active row only after verifying its metadata and record the
change in the registry's `Change Log`.

`garmin_mcp_daily_archive.v1` is the registry-level dataset contract. The bundled builder's raw
artifact envelope label remains `garmin-daily-archive-envelope/v2`; do not rewrite either value to
make them match.

## Related Garmin account-export asset

The daily archive and account exports are separate datasets. The archive skill must not write to,
copy from, or normalize records into the account-export asset.

The registry must also contain this active row for downstream consumers:

- Asset Key: `garmin-account-exports`
- Kind: `Folder`
- Drive ID: `1ZtmcG_OYj5SO2R_fS3gCUkiYdFVUmU10`
- Canonical Path: `Health/01 Raw Data/Garmin Account Exports`
- Schema Version: `garmin_account_export.v1`
- Primary Writer: `import-garmin-account-export`

This is a registration requirement for the historical-export workflow, not an expansion of the
daily archive's destination or append-only contract.

Consumers normalize compatible raw endpoint payloads with the
`import-garmin-account-export` skill's `normalize_garmin_records.py` adapter. Overlay coverage per
dataset and use `(stable_id, canonical_record_sha256)` for exact deduplication.
