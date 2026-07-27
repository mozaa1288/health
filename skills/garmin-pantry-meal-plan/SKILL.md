---
name: garmin-pantry-meal-plan
description: Create, revise, retrieve, and explain the user's Garmin-tailored, pantry-aware weekly meal plan and consolidated grocery list. Use for the Sunday meal-plan automation; requests such as “make this week’s meal plan,” “what am I eating today?”, “what should I prep?”, or “what groceries do I need?”; and any change to the current weekly plan, nutrition totals, pantry allocation, or grocery quantities.
---

# Garmin Pantry Meal Plan

Build one-person weekly meal plans from recent Garmin training and recovery data, current pantry inventory, the preferred-food nutrition map, and the canonical nutrition CSV. Compile every generated or revised plan with the bundled Python tool and fail closed when validation does not pass.

## Choose the operation

### Retrieve or explain the current plan

1. Resolve and verify the `weekly-plans` asset from the Health Data Registry as specified in `references/sources.md`.
2. Search that verified folder for the most recent plan. Do not select a same-named folder found by path search.
3. Prefer the latest validated `compiled_plan.json` whose week contains the requested date. Read its companion `weekly_meal_plan.md` for preparation instructions and Garmin rationale.
4. Answer from those artifacts without regenerating the week.
5. If no persisted validated plan covers the date, say so and offer to generate one. Do not reconstruct precise meals or grocery quantities from the pantry ledger alone.

### Generate or revise a plan

Follow the complete workflow below. A revision is a full recompile, not a manual patch to displayed totals or grocery quantities.

## Read the required references

- Read [references/sources.md](references/sources.md) for authoritative file IDs, folders, date windows, and persistence rules.
- Read [references/meal-plan-contract.md](references/meal-plan-contract.md) for dietary constraints, Garmin logic, pantry selection, validation, writeback, and output requirements.
- Read [references/plan-json.md](references/plan-json.md) before constructing `plan.json`.

## Generate the week

1. Resolve and verify every required asset from the Health Data Registry as specified in `references/sources.md`. Stop before reading source data or writing outputs if any registry or live-metadata check fails.
2. Resolve the target week in `America/Los_Angeles`.
3. Build the Garmin history from the newest validated normalized account export as the historical baseline, then overlay the verified raw daily archive and current two-day connector pull for freshness. Verify the export manifest and every referenced artifact hash before use. Normalize compatible raw endpoint responses with the `import-garmin-account-export` skill's bundled `normalize_garmin_records.py` adapter. Merge per dataset, deduplicate only exact `stable_id` plus `canonical_record_sha256` pairs, and preserve conflicting records and legitimate multiple activities. Exclude records flagged as anomalies, report them, and never treat missing Garmin data as zero.
4. Analyze activity volume, steps, calories when available, resting heart rate, sleep, stress, Body Battery, HRV, body composition, workout duration, distance, and hard/long versus light/rest days.
5. Read the complete populated pantry tabs from the verified pantry Sheet before selecting recipes. Apply the inventory eligibility order in the contract exactly.
6. Fetch the complete preferred-food nutrition map and the current canonical nutrition CSV from their verified Drive IDs. Use mapped row IDs when a preferred food appears. Do not substitute remembered macros or prose estimates.
7. Design the whole week as structured `plan.json`. Give every meal a unique ID, local date, name, and explicit one-person ingredient quantities. Reference a specific nutrition row and edible grams for every ingredient.
8. Add package metadata for every possible grocery shortfall. Subtract eligible inventory before package rounding.
9. Run:

```bash
python scripts/meal_plan_compiler.py plan.json \
  --nutrition-csv nutrition_corrected.csv \
  --output-json compiled_plan.json \
  --output-markdown grocery_audit.md
```

Resolve `scripts/meal_plan_compiler.py` relative to this skill directory when the working directory differs.

10. Deliver nothing until the process exits successfully, `compiled_plan.json` has `status: validated`, and every validation flag is true. Repair `plan.json` and rerun on failure; never suppress an error or manually override compiler output.
11. Use compiler output as the sole source for meal nutrition, daily totals, pantry allocation, grocery shortfalls, package rounding, projected carryover, and proxy disclosures.
12. Replace any existing projected ledger rows for the same week, then write the compiled inventory allocation to the weekly pantry ledger. Do not overwrite confirmed pantry quantities from a projected plan.
13. Persist the validated plan artifacts using the naming and folder rules in `references/sources.md`, then verify their Drive metadata and folder placement.

## Present the result

Include:

- A seven-day plan with explicit one-person servings.
- Per-meal calories, protein, carbohydrates, and fat.
- Daily nutrition totals.
- A grouped grocery list showing recipe use, inventory contribution, net shortfall, amount to buy, and projected ending inventory.
- `Use from pantry — buy none`.
- A concise meal-prep plan.
- Garmin-driven calorie and carbohydrate adjustments.
- Pantry assumptions and nutrition proxy disclosures.
- A clear statement that nutrition, pantry, and grocery validation passed.

For focused questions, return only the relevant slice of the persisted plan unless the user asks for the full week.

## Bundled tooling

`scripts/meal_plan_compiler.py` is the authoritative deterministic compiler. Do not fetch or recreate the compiler from Drive during normal use. Fetch live data sources, not replacement code.

Treat weekly plan documents, compiled outputs, grocery audits, and reports as derived artifacts. Never use them to replace or silently correct raw Garmin captures, reference nutrition data, or confirmed pantry state.
