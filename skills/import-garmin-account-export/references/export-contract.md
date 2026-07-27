# Garmin Account Export Contract

## Registry identity

- Registry: `Health Data Registry`
- Registry Drive ID: `1AHvwyDzlhznRFvAry5Tqj37Ol9w5HOOhES4htrqoXjE`
- Asset key: `garmin-account-exports`
- Canonical path: `Health/01 Raw Data/Garmin Account Exports`
- Schema version: `garmin_account_export.v1`
- Update policy: append-only immutable snapshots
- Timezone for snapshot dates and consumer day boundaries: `America/Los_Angeles`

Resolve the asset by exact registry key and Drive ID. Verify its live type, name, and parent. Do not use a same-named folder found by search.

## Snapshot contract

Each snapshot date has exactly one immutable original ZIP and one normalized artifact set. A later import on the same local date must use a distinct timestamp-suffixed snapshot folder rather than overwrite the first.

The original ZIP is the audit source. It may contain identity, contact, device, media, ECG, GPS, social, consent, and account records. Keep it private and do not unpack those categories into Drive. Preserve its Drive ID when moving it is permitted. If Drive denies write access, preserve the source in place and store a byte-identical snapshot copy; the manifest must record both IDs and the shared SHA-256.

Normalized files are newline-delimited JSON. Every line has:

- `schema_version`
- `dataset`
- `stable_id`
- `source_record_sha256`
- `canonical_record_sha256`
- `source_file`
- `source_index`
- `event_date` when derivable
- `record`, with direct account, device, UUID, email, and GPS identifiers removed
- `conflict_group` when the same stable ID has differing payloads

## Datasets

| File | Purpose |
|---|---|
| `daily.jsonl` | Daily steps, energy, stress, heart rate, Body Battery, hydration, and related summaries |
| `activities.jsonl` | Summarized activities without GPS coordinates or device/account identifiers |
| `sleep.jsonl` | Substantive sleep records; retro-only placeholders are omitted |
| `health_status.jsonl` | Garmin health-status metrics |
| `hydration.jsonl` | Hydration and sweat-loss events |
| `training_status.jsonl` | Training load and status history |
| `vo2max.jsonl` | VO2 max and max-MET history |
| `acclimation.jsonl` | Heat and altitude acclimation history |
| `biometrics.jsonl` | Body-metric history and current profile values |
| `fitness_age.jsonl` | Fitness-age history |
| `heart_rate_zones.jsonl` | Heart-rate zone configuration |
| `personal_records.jsonl` | Garmin personal records |
| `gear.jsonl` | Gear inventory without account identifiers |
| `fit_inventory.jsonl` | Metadata inventory of nested FIT files; no FIT payload is extracted or decoded |

An absent file means the source export had no usable records for that dataset. It does not mean a zero value.

## Manifest validation

Accept a snapshot only when:

- `schema_version` is `garmin-account-export-manifest/v1`;
- `validation.status` is `validated`;
- the original ZIP digest matches `source.sha256`;
- every artifact exists and matches its listed SHA-256 and byte size;
- JSONL line counts match `record_count`;
- anomaly records are excluded from trustworthy coverage.

The manifest's coverage is based on parsed record dates, never filename windows. Future dates more than seven days after the snapshot date are anomalies and are not evidence of coverage.

## Historical plus freshness merge

Use account exports as historical baselines. Use `garmin-archive` and the live Garmin connector for newer captures and current values.

1. Select the newest validated account-export snapshot.
2. Read only the datasets needed for the task.
3. For each dataset independently, add successful daily-archive and live records after its trustworthy coverage boundary and include overlaps needed for deduplication.
4. Normalize raw archive or live records with the bundled `normalize_garmin_records.py` adapter, then deduplicate exact `stable_id` and `canonical_record_sha256` pairs.
5. Preserve differing canonical hashes under the same stable ID as conflicts.
6. For a derived decision, use the newest successful capture with the clearest source timestamp and disclose material conflicts.
7. Preserve gaps and failed endpoints as unknown.

Never rewrite the historical export from daily captures, and never backfill the daily archive by copying normalized export records into it.
