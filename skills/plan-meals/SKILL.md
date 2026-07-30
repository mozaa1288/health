---
name: plan-meals
description: Create, revise, retrieve, and explain a practical one-person weekly meal plan and grocery list using recent activity, pantry inventory, preferred foods, and canonical nutrition data.
---

# Plan Meals

Build a practical vegetarian weekly plan from the synced daily Garmin archive, current pantry inventory, the preferred-food map, and the canonical nutrition CSV.

## Retrieve an existing plan

1. Resolve `weekly-plans` through the live Health Data Registry.
2. Use the latest validated `compiled_plan.json` whose week contains the requested date.
3. Use its companion `weekly_meal_plan.md` for preparation notes and rationale.
4. Do not regenerate the week for a simple retrieval question.

## Generate or revise a plan

1. Resolve and verify `garmin-archive`, `pantry-tracker`, `weekly-plans`, `preferred-food-map`, and `canonical-nutrition` through the Health Data Registry.
2. Use the target week in `America/Los_Angeles`.
3. Build Garmin context from Drive-synced `garmin_YYYY-MM-DD.json` files in the registered archive:
   - use the most recent 14 complete local days available;
   - require each filename date to match its top-level `date`;
   - when more than one valid file exists for a date, use the newest by timezone-aware `pulled_at`;
   - use `pulled_at` only as a collection timestamp, not as the health-record date;
   - read raw sections such as `stats`, `user_summary`, `sleep`, `heart_rate`, `stress`, `body_battery`, `steps`, `hrv`, `respiration`, `spo2`, `max_metrics`, `training_status`, `training_readiness`, `body_composition`, `weigh_ins`, `daily_weigh_ins`, and `activities`;
   - treat endpoint errors, missing sections, empty payloads, null fields, and missing dates as unavailable—not zero;
   - treat the current local day as partial and exclude it from complete-day averages unless clearly labeled.
4. Do not require any other Garmin data source for normal meal planning. If a daily file or section is unavailable, disclose the gap and continue using only the available evidence.
5. When recent actual intake or plan adherence is relevant, read the exact `food-log-YYYY-MM-DD.jsonl` files directly from Drive folder `13E1t9q2JQrCliQyO8xecHNcDdUyhMjaI` and use only each entry's final active revision. Never read the legacy consumption spreadsheet.
6. Read the pantry's populated `Pantry Inventory`, `Weekly Ledger`, and `Rules & Lists` ranges.
7. Count inventory only when it is:
   - currently confirmed and recently verified;
   - otherwise the newest confirmed or reconciled ledger ending;
   - otherwise the immediately prior week's projected ending, clearly labeled projected.
   Treat anything else as unavailable.
8. Follow the user's standing preferences: one person, vegetarian base, skip weekday breakfasts, no mushrooms or cucumber, practical meals, gradual fat loss without impairing running recovery, and relatively steady protein.
9. Use the preferred-food map and canonical nutrition CSV for all numerical nutrition. Track grains and pasta in their defined dry-weight convention, use explicit edible grams, and disclose proxies.
10. Create `plan.json` using [references/plan-json.md](references/plan-json.md). Give every meal a stable ID, date, name, and quantified ingredients. Add inventory and package metadata for grocery reconciliation.
11. Run:

```bash
python scripts/meal_plan_compiler.py plan.json \
  --nutrition-csv nutrition_corrected.csv \
  --output-json compiled_plan.json \
  --output-markdown grocery_audit.md
```

12. Publish only when the compiler exits successfully, returns `status: validated`, and every validation flag is true. Use compiler output for meal nutrition, daily totals, grocery quantities, pantry allocation, package rounding, and proxy disclosures.
13. Replace only projected ledger rows for the same week. Never overwrite confirmed pantry quantities from a projected plan.
14. Save and verify these week-specific files in `weekly-plans`:

```text
YYYY-MM-DD_plan.json
YYYY-MM-DD_compiled_plan.json
YYYY-MM-DD_grocery_audit.md
YYYY-MM-DD_weekly_meal_plan.md
```

## Response

For a full plan, show the seven days, explicit one-person servings, per-meal and daily macros, grocery list, pantry-only items, prep notes, Garmin-driven adjustments, missing-data limitations, and important assumptions. For focused questions, return only the relevant part of the validated plan.
