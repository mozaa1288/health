# Porting notes

This repository mirrors the personal ChatGPT health automation skills as readable, self-contained directories.

## Scope

The bundle contains eight verb–object skills: `pull-garmin-data`, `plan-meals`, `log-food`, `list-food`, `sync-food`, `recommend-meal`, `update-pantry`, and `plot-health-data`.

## Data boundary

Google Drive is the source of truth. Food consumption uses one append-only `food-log-YYYY-MM-DD.jsonl` file per local date in `Health/03 Operational Trackers/Food Logs`; Garmin archives, pantry inventory, weekly plans, nutrition lookup assets, and food evidence remain Drive-backed. This repository contains only skill instructions, deterministic scripts, schemas, and tests; it does not contain personal daily logs or other health records.

## Source hygiene

The port is checked for credentials and generated artifacts. Garmin credentials stay in the local `~/.garminconnect` token store and must never be committed. Daily Garmin archives, daily food JSONL, and evidence files are also excluded.
