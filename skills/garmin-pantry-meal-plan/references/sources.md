# Authoritative Sources and Persistence

## Registry-first source resolution

Use the Google Sheet `Health Data Registry` as the authoritative catalog:

- Drive ID: `1AHvwyDzlhznRFvAry5Tqj37Ol9w5HOOhES4htrqoXjE`
- Canonical path: `Health/00 System & Governance/Health Data Registry`
- Registry schema version: `health_drive_layout.v1`
- Tab: `Assets`
- Exact columns A:K: `Asset Key`, `Name`, `Kind`, `Drive ID`, `Canonical Path`, `Schema Version`, `Primary Writer`, `Write Policy`, `Status`, `Last Verified`, `Notes`

At the start of every retrieval, generation, or revision:

1. Fetch the registry by its exact Drive ID. Verify that its live metadata identifies the expected Google Sheet and canonical location.
2. Read the complete populated range of `Assets`; do not rely on a preview or a cached copy.
3. Resolve each needed asset by exact `Asset Key`. Require exactly one matching row with `Status` equal to `Active` and a nonblank `Drive ID`.
4. Fetch each asset by the registry row's exact `Drive ID`. Verify its live name, kind/MIME type, and parent folder against the registry row. Treat `Canonical Path` as a human-readable location check, not as the identity.
5. Confirm that the current registry rows match the bootstrap identities below. Stop and report configuration drift if a row is missing, duplicated, inactive, points to a different Drive ID, or disagrees with live metadata. Do not fall back to a same-named file or folder.

## Required assets

| Asset key | Purpose | Expected current identity |
|---|---|---|
| `garmin-archive` | Raw Garmin daily captures | Drive folder `1PRhI2z03g_HwHXNJpfjQ7ff5Ijnk0786` at `Health/01 Raw Data/Garmin Daily Archive` |
| `garmin-account-exports` | Validated normalized historical Garmin account exports | Drive folder `1ZtmcG_OYj5SO2R_fS3gCUkiYdFVUmU10` at `Health/01 Raw Data/Garmin Account Exports`; schema `garmin_account_export.v1`; primary writer `import-garmin-account-export` |
| `pantry-tracker` | Pantry inventory and weekly ledger | Google Sheet `1PfVg-73Ksgi6YRVJ30K7-m6UHCJBE29E0u43FbbyKmw` at `Health/03 Operational Trackers/Pantry & Fridge Inventory Tracker` |
| `weekly-plans` | Current and historical weekly plan artifacts | Drive folder `15snr42midAQ4CqajszQckpztMsD5Ppmh` at `Health/04 Plans/Weekly Meal Plans` |
| `preferred-food-map` | Preferred-food nutrition mappings | Google Doc `1xmQuCVBzvKMRG5bAZB_xAdKXsbXTMc8m9hExS22zRyA` |
| `canonical-nutrition` | Canonical numerical nutrition data | Drive file `1tFqCTo50otb-nuRuy1Xt7yQWI3iddiLM` |

Read the pantry sheet's complete populated ranges from:

- `Pantry Inventory`
- `Weekly Ledger`
- `Rules & Lists`

Fetch live versions on every generation or revision after registry resolution succeeds. The preferred-food map's recorded CSV hash is a consistency check, not permission to use an old CSV.

## Garmin window

Use the 14 local calendar days ending on the most recent available date. First resolve `garmin-account-exports` and select its newest validated normalized export. Confirm that the export manifest is present and valid, and verify the hash of every manifest-referenced artifact before reading its normalized records. That export is the historical baseline; it does not replace the freshness sources below.

For each needed dataset, overlay enough newest raw JSON daily archives to span its missing or newer dates, then merge the connected Garmin service's current two-day window. Extract compatible endpoint payloads and normalize them with the `import-garmin-account-export` skill's bundled `normalize_garmin_records.py` adapter. Deduplicate only records that share both `stable_id` and `canonical_record_sha256`. Preserve conflicts, including one `stable_id` with different canonical hashes, for disclosure and preserve legitimate multiple activities. Exclude records explicitly marked anomalous from meal-planning calculations and report their exclusion. Never use one dataset's coverage end as another's, and never infer a missing day or metric as zero.

Use companion Markdown only to discover files or assess completeness. Analyze raw JSON. Report missing days, failed endpoints, tier limits, and archive gaps.

## Persisted weekly plans

Store generated plans only in the verified `weekly-plans` folder. The registry row must resolve to Drive folder `15snr42midAQ4CqajszQckpztMsD5Ppmh` at `Health/04 Plans/Weekly Meal Plans`. Do not create a replacement folder when the registered folder is missing or inaccessible.

Use the local Monday date that starts the plan week:

- `YYYY-MM-DD_plan.json`
- `YYYY-MM-DD_compiled_plan.json`
- `YYYY-MM-DD_grocery_audit.md`
- `YYYY-MM-DD_weekly_meal_plan.md`

Never overwrite a different week's files. When regenerating the same week, replace that week's four files so retrieval has one authoritative current version. Verify each file's Drive metadata and parent folder after writing.

`weekly_meal_plan.md` contains the user-facing plan, meal-prep guidance, Garmin rationale, and assumptions. `compiled_plan.json` remains authoritative for exact meals, nutrition, inventory allocation, and groceries.

All four weekly-plan files are derived artifacts. They may be regenerated from verified sources and compiler logic, but they must never be treated as evidence that modifies raw Garmin archives, canonical nutrition references, or confirmed pantry observations. The projected weekly pantry ledger writeback is operational state and remains governed by the writeback rules in `meal-plan-contract.md`.
