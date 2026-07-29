---
name: recommend-next-meal
description: Recommend the user's next meal or evening snack from today's authoritative Food Consumption Log, the current validated weekly plan, and eligible pantry inventory. Use for “what should I eat next?”, dinner or snack recommendations, adjustments after deviating from the plan, or comparisons of today's logged intake against the planned daily nutrition. Produces source-backed, quantitatively validated options without logging unconsumed food or diagnosing nutritional deficiencies.
---

# Recommend Next Meal

Recommend—not log—the next one-person meal or snack. Base the recommendation on today's actual active food-log rows, the validated compiled weekly plan covering today, and foods supported by the registered pantry and preferred-food sources.

## Read dependencies

Before every operation, read:

- `references/recommendation-contract.md` in this skill;
- `../log-food/references/sources-and-schema.md` for registry, food-log, and nutrition-source rules;
- `../garmin-pantry-meal-plan/references/sources.md` for weekly-plan and pantry source resolution;
- `../garmin-pantry-meal-plan/references/meal-plan-contract.md` for dietary constraints, nutrition conventions, and pantry eligibility.

Use `scripts/recommend_next_meal.py` for every quantitative comparison or recommendation. Do not manually calculate or rank options in prose.

## Workflow

### 1. Establish the request

Resolve the current local date and time in `America/Los_Angeles`. Determine whether the user wants the next ordinary meal, a specific meal such as dinner, a post-workout meal, or an evening snack. Use the current validated weekly plan as the Garmin-adapted baseline; pull live Garmin data only when the user explicitly asks to account for an unplanned workout or a meaningful same-day activity change.

### 2. Resolve and verify sources

Resolve every asset through the live `Health Data Registry` by exact asset key. At minimum verify:

- `food-log`;
- `weekly-plans`;
- `pantry-tracker`;
- `preferred-food-map`;
- `canonical-nutrition`.

Verify live file identity, MIME type, parent, schema, and access policy as required by the dependency contracts. Never substitute a title search result, stale hardcoded path, assistant memory, or a derived summary for an authoritative source.

### 3. Read today's actual intake

Read the bounded active rows in `Food Log` for the current local date. Aggregate item rows by entry and calculate the known subtotal for calories, protein, carbohydrates, fat, fiber, and sodium.

Blank nutrition is unknown, not zero. Preserve every affected entry in `unknown_items`. When unknown items exist, describe the known subtotal and every projected option as a **lower bound**. Do not claim an exact remaining deficit.

### 4. Read today's planned baseline

Select the latest validated `YYYY-MM-DD_compiled_plan.json` whose week contains today. Require:

- `status: validated`;
- all validation flags true;
- a verified canonical-nutrition identity;
- a `daily_totals` entry for today.

Use today's compiled `daily_totals` as the **planned daily baseline**, not as a medical requirement. Use the plan's exact meals, quantities, nutrition rows, edible grams, and proxy notes when building a planned-meal option.

Determine which planned meals remain unconsumed by comparing their stable meal IDs against active `Planned Meal ID` values in the food log. Do not assume a meal was eaten merely because it was planned.

### 5. Build candidate options

Use the following hierarchy:

1. The next unconsumed planned meal, unchanged, when still appropriate.
2. A minimally adjusted version of that planned meal when actual intake materially differs from plan.
3. A simple meal or snack composed from eligible pantry inventory and preferred foods.
4. An explicitly labeled purchase-required option only when the user permits shopping or no verified on-hand option can be produced.

Build two options by default and no more than three. Every option must have:

- a stable option ID and one-person name;
- explicit ingredient quantities and units;
- a canonical nutrition row ID or unique name for every ingredient;
- edible grams or a documented exact conversion;
- proxy disclosures;
- an availability classification of `planned`, `confirmed_pantry`, `projected_pantry`, or `purchase_required`;
- concise preparation guidance.

Apply the weekly-plan dietary constraints: vegetarian base, no mushrooms or cucumber, and salmon only when explicitly requested as a substitution. Never claim projected pantry inventory is confirmed. Do not infer pantry depletion from logged consumption.

### 6. Compile and rank

Create `recommendation_input.json` following `references/recommendation-contract.md`, then run:

```bash
python scripts/recommend_next_meal.py recommendation_input.json \
  --nutrition-csv nutrition_corrected.csv \
  --output recommendation_result.json
```

Resolve paths relative to this skill directory. Continue only when the process exits successfully and the output status is `validated` or `advisory_with_unknowns`.

The compiler distinguishes nutrient semantics:

- calories, protein, and carbohydrates: closeness to the planned baseline;
- fat: closeness with a stronger penalty for excess;
- fiber: a floor, not something to reduce when above plan;
- sodium: an upward guardrail only; never recommend food to “fill” sodium.

Do not override the compiler's ranking manually. A purchase-required option may not outrank a verified on-hand option solely because its macros are marginally closer.

### 7. Present the recommendation

State:

- current known logged subtotal versus the planned daily baseline;
- any unknown-nutrition entries and the lower-bound limitation;
- the recommended option first, followed by one alternative;
- explicit ingredients and quantities;
- option macros and projected known daily totals;
- the important remaining gaps or excesses using “below/above plan,” never “nutrient deficient”;
- availability and proxy disclosures;
- concise preparation notes.

Do not recommend extreme compensation, intentional meal skipping, or adding sodium merely to match the plan. A one-day comparison is not a diagnosis of nutritional deficiency.

### 8. Logging boundary

A recommendation is not evidence of consumption. Never write it to the Food Consumption Log or modify pantry inventory. After the user explicitly states what they consumed, route the actual meal through `../log-food/SKILL.md` using the consumed quantities and substitutions.

## Failure behavior

Stop rather than guessing when the registry, food-log schema, plan validation, nutrition CSV, required quantities, or compiler cannot be verified. If no validated plan covers today, provide a clearly labeled pantry-based recommendation only when authoritative food-log, pantry, preferred-food, and canonical-nutrition sources are available; otherwise report the exact missing source.
