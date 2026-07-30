# Personal Health Automation Skills

A version-controlled set of health workflows using ChatGPT Library for daily food logs and Google Drive for the remaining registered health assets.

## Install in Claude Code

```text
/plugin marketplace add mozaa1288/health
/plugin install health-automation@mozaa-health
/reload-plugins
```

## Skills

The repository contains exactly six verb–object skills:

| Skill | Purpose |
|---|---|
| `pull-garmin-data` | Retrieve Drive-synced daily Garmin archives. |
| `plan-meals` | Build, revise, and retrieve weekly meal plans and grocery lists. |
| `log-food` | Record and review food that was actually consumed. |
| `sync-food` | Add clear consumed meals missing from the daily JSONL log. |
| `recommend-meal` | Recommend a practical next meal or snack. |
| `update-pantry` | Update pantry inventory from receipts, lists, photos, or corrections. |

## Data architecture

Food consumption uses one append-only ChatGPT Library file per local date:

```text
food-log-YYYY-MM-DD.jsonl
```

Each JSONL line is one complete meal revision. Stable entry IDs make identical retries no-ops; corrections and deletions append another revision, and the last revision wins. The legacy food spreadsheet is migration input only and is not used at runtime.

Google Drive remains authoritative for Garmin archives, pantry inventory, weekly plans, nutrition lookup assets, and food evidence. Those skills resolve Drive assets through the Health Data Registry.

The companion collector script runs separately on a trusted machine with a maintained `garminconnect` release (version 0.3.5 or newer) and the existing `~/.garminconnect` token store. The token store must remain readable only by the local user. By default the collector refreshes today and yesterday, and it can backfill an explicit date range. It atomically writes one file per local date:

```text
garmin_YYYY-MM-DD.json
```

Each file includes `date`, timezone-aware `pulled_at`, and raw Garmin sections such as `stats`, `user_summary`, `sleep`, `heart_rate`, `stress`, `body_battery`, `steps`, `hrv`, `respiration`, `spo2`, `max_metrics`, `training_status`, `training_readiness`, `body_composition`, `weigh_ins`, `daily_weigh_ins`, and `activities`.

Google Drive Desktop or a separate `rclone copy` task syncs the completed daily files into the registered `garmin-archive` folder. `pull-garmin-data` and other Garmin-consuming skills retrieve the newest valid daily archive file for each date from that Drive folder. They do not require another Garmin workflow.

Raw endpoint responses are preserved. Endpoint failures remain inline as `{"error": "..."}`. Missing files, failed sections, empty payloads, and null fields are unavailable data—never zero.

## Retained scripts

Scripts remain only where deterministic code provides clear value:

- local Garmin collection and atomic archive writing;
- meal-plan nutrition, pantry allocation, and grocery compilation;
- food-log nutrition compilation, deterministic unit conversion, JSONL append/read/validation, and legacy CSV migration.

Food synchronization, pantry updates, and meal recommendations use direct, conservative workflows instead of intermediate planning or ranking scripts.

## Validation

```bash
python scripts/validate_repo.py
```

The validator checks the exact skill catalogs and folders, `SKILL.md` names, relative links, Python syntax, generated artifacts, and bundled tests.

## Privacy

Never commit Garmin credentials, tokens, cookies, daily Garmin archives, `food-log-YYYY-MM-DD.jsonl` files, legacy food-log exports, receipt images, or other health records. This repository is for workflow instructions, code, schemas, and non-secret identifiers only.
