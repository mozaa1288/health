# Personal Health Automation Skills

A version-controlled set of health workflows backed by the Google Drive health-data system.

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
| `sync-food` | Add clear consumed meals that are missing from the Food Log. |
| `recommend-meal` | Recommend a practical next meal or snack. |
| `update-pantry` | Update pantry inventory from receipts, lists, photos, or corrections. |

## Data architecture

Google Drive is the health-data source of truth. Skills resolve authoritative Drive assets through the Health Data Registry before reading or writing.

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
- Food Log row and nutrition compilation.

Food synchronization, pantry updates, and meal recommendations use direct, conservative workflows instead of intermediate planning or ranking scripts.

## Validation

```bash
python scripts/validate_repo.py
```

The validator checks the exact skill catalogs and folders, `SKILL.md` names, relative links, Python syntax, generated artifacts, and bundled tests.

## Privacy

Never commit Garmin credentials, tokens, cookies, daily Garmin archives, Food Log exports, receipt images, or other health records. This repository is for workflow instructions, code, schemas, and non-secret identifiers only.
