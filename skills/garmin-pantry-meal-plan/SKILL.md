---
name: garmin-pantry-meal-plan
description: Create, revise, retrieve, and explain a one-person Garmin-aware, pantry-aware weekly meal plan and grocery list. Use for weekly planning, today's meals, prep guidance, groceries, or plan revisions.
---

# Garmin Pantry Meal Plan

Build a practical vegetarian weekly plan from recent Garmin activity, current pantry inventory, the preferred-food map, and the canonical nutrition CSV.

## Retrieve an existing plan

1. Resolve `weekly-plans` through the live Health Data Registry.
2. Use the latest validated `compiled_plan.json` whose week contains the requested date.
3. Use its companion `weekly_meal_plan.md` for preparation notes and rationale.
4. Do not regenerate the week for a simple retrieval question.

## Generate or revise a plan

1. Resolve and verify these registry assets: `garmin-account-exports`, `garmin-archive`, `pantry-tracker`, `weekly-plans`, `preferred-food-map`, and `canonical-nutrition`.
2. Use the target week in `America/Los_Angeles`.
3. Build recent Garmin context from the newest validated account export, then overlay newer daily archives and the current live window when available. Merge per dataset, preserve gaps and conflicts, and never treat missing data as zero.
4. Read the pantry's populated `Pantry Inventory`, `Weekly Ledger`, and `Rules & Lists` ranges.
5. Count inventory only when it is:
   - currently confirmed and recently verified;
   - otherwise the newest confirmed or reconciled ledger ending;
   - otherwise the immediately prior week's projected ending, clearly labeled projected.
   Treat anything else as unavailable.
6. Follow the user's standing preferences: one person, vegetarian base, skip weekday breakfasts, no mushrooms or cucumber, practical meals, gradual fat loss without impairing running recovery, and relatively steady protein.
7. Use the preferred-food map and canonical nutrition CSV for all numerical nutrition. Track grains and pasta in their defined dry-weight convention, use explicit edible grams, and disclose proxies.
8. Create `plan.json` using [references/plan-json.md](references/plan-json.md). Give every meal a stable ID, date, name, and quantified ingredients. Add inventory and package metadata for grocery reconciliation.
9. Run:

```bash
python scripts/meal_plan_compiler.py plan.json \
  --nutrition-csv nutrition_corrected.csv \
  --output-json compiled_plan.json \
  --output-markdown grocery_audit.md
```

10. Publish only when the compiler exits successfully, returns `status: validated`, and every validation flag is true. Use compiler output for meal nutrition, daily totals, grocery quantities, pantry allocation, package rounding, and proxy disclosures.
11. Replace only projected ledger rows for the same week. Never overwrite confirmed pantry quantities from a projected plan.
12. Save four week-specific files in the verified `weekly-plans` folder:

```text
YYYY-MM-DD_plan.json
YYYY-MM-DD_compiled_plan.json
YYYY-MM-DD_grocery_audit.md
YYYY-MM-DD_weekly_meal_plan.md
```

Verify their names and folder placement after writing.

## Response

For a full plan, show the seven days, explicit one-person servings, per-meal and daily macros, grocery list, pantry-only items, prep notes, Garmin-driven adjustments, and important assumptions. For focused questions, return only the relevant part of the validated plan.
