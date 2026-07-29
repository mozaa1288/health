# Porting notes

This repository mirrors the personal ChatGPT health automation skills as readable, self-contained directories.

## Scope

The bundle contains six verb–object skills: `pull-garmin-data`, `plan-meals`, `log-food`, `sync-food`, `recommend-meal`, and `update-pantry`.

## Data boundary

Google Drive remains the source of truth. Garmin data is collected locally into Drive-synced daily `garmin_YYYY-MM-DD.json` files. This repository contains skill instructions, deterministic scripts, schemas, and tests only. It does not contain daily Garmin archives, food-log rows, receipt images, pantry photos, or other health records.

## Source hygiene

The port is checked for credentials and generated artifacts. Garmin credentials stay in the local `~/.garminconnect` token store and must never be committed. Drive file IDs may remain because the skills use registry-first identity verification; those IDs are identifiers, not authentication secrets.
