# Porting notes

This repository mirrors the personal ChatGPT health automation skills as readable, self-contained directories.

## Scope

The bundle includes the Garmin archive and account-export import skills, the Garmin-aware pantry meal planner, food logging and daily reconciliation, and receipt/list/photo pantry updates.

## Data boundary

Google Drive remains the source of truth. This repository contains skill instructions, deterministic scripts, schemas, and tests only. It does not contain Garmin exports, food-log rows, receipt images, pantry photos, or other health records.

## Source hygiene

The port was checked for credentials and generated artifacts. A reference example copied from a real consumption statement was replaced with synthetic food data. Drive file IDs remain because the skills use registry-first identity verification; these IDs are identifiers, not authentication secrets.
