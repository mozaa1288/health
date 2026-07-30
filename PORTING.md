# Porting notes

This repository mirrors the personal ChatGPT health automation skills as readable, self-contained directories.

## Scope

The bundle contains six verb–object skills: `pull-garmin-data`, `plan-meals`, `log-food`, `sync-food`, `recommend-meal`, and `update-pantry`.

## Data boundary

ChatGPT Library is the sole food-log source of truth, with one append-only `food-log-YYYY-MM-DD.jsonl` file per local date. Google Drive remains authoritative for Garmin archives, pantry inventory, weekly plans, nutrition lookup assets, and food evidence. This repository contains only skill instructions, deterministic scripts, schemas, and tests; it does not contain personal daily logs or other health records.

## Source hygiene

The port is checked for credentials and generated artifacts. Garmin credentials stay in the local `~/.garminconnect` token store and must never be committed. Daily Garmin archives, daily food JSONL, migration exports, and evidence files are also excluded.
