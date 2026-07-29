# Recommendation Input and Ranking Contract

## Purpose

This contract defines the deterministic input used to validate and rank proposed next-meal options. It compares actual known intake with the current validated plan without treating a single day as a medical diagnosis.

## Input JSON

```json
{
  "local_date": "2026-07-28",
  "as_of_local": "2026-07-28T18:30:00-07:00",
  "target_source": {
    "week_start": "2026-07-27",
    "compiled_plan_name": "2026-07-27_compiled_plan.json",
    "compiled_plan_drive_id": "drive-file-id",
    "nutrition_csv_drive_id": "1tFqCTo50otb-nuRuy1Xt7yQWI3iddiLM"
  },
  "planned_baseline": {
    "calories": 2200,
    "protein_g": 140,
    "carbs_g": 250,
    "fat_g": 70,
    "fiber_g": 30,
    "sodium_mg": 2300
  },
  "logged": {
    "known_nutrition": {
      "calories": 1300,
      "protein_g": 70,
      "carbs_g": 150,
      "fat_g": 45,
      "fiber_g": 18,
      "sodium_mg": 1400
    },
    "unknown_items": [
      {
        "entry_id": "entry-id",
        "item": "Unresolved cooking fat",
        "reason": "Amount was not specified"
      }
    ]
  },
  "options": [
    {
      "id": "planned-dinner",
      "name": "Planned tofu bowl",
      "kind": "planned_meal",
      "availability": "planned",
      "planned_meal_id": "2026-07-28-dinner",
      "preparation": "Reheat the rice and tofu; add kimchi after heating.",
      "ingredients": [
        {
          "ingredient": "Tofu",
          "quantity": 260,
          "unit": "g",
          "nutrition_grams_total": 260,
          "nutrition_row_id": 123,
          "nutrition_match_type": "exact"
        }
      ]
    }
  ]
}
```

## Required rules

- `local_date` and `as_of_local` must refer to the same `America/Los_Angeles` date.
- Every baseline and known-nutrition value must be numeric and nonnegative.
- `unknown_items` must include every active food-log item with unknown calories, protein, carbohydrates, or fat.
- Provide one to three candidate options with unique IDs.
- Each option requires one or more quantified ingredients.
- Each ingredient must resolve to the canonical nutrition CSV using `nutrition_row_id` or a unique `nutrition_name`.
- `nutrition_match_type` must be `exact` or `proxy`; every proxy requires a note.
- Allowed availability values are:
  - `planned`;
  - `confirmed_pantry`;
  - `projected_pantry`;
  - `purchase_required`.
- A planned option requires `planned_meal_id`.

## Nutrient semantics

The baseline is the validated plan's total for the day. The ranking function uses:

- calorie closeness;
- protein shortfall as the strongest nutrition penalty;
- carbohydrate closeness;
- fat closeness, with excess penalized more than being modestly below plan;
- fiber shortfall only;
- sodium above the planned reference only.

Fiber above plan and sodium below plan receive no penalty. Sodium below plan must never be described as a deficit to fill.

## Availability semantics

Availability affects ranking:

1. `planned` and `confirmed_pantry` are preferred.
2. `projected_pantry` receives a caution penalty and must be disclosed.
3. `purchase_required` receives the largest availability penalty.

The compiler validates the supplied classification; the workflow is responsible for deriving it from the authoritative plan and pantry contracts.

## Output interpretation

- `validated`: no unknown logged nutrition affects the current day.
- `advisory_with_unknowns`: one or more logged items have unresolved core nutrition. Current and projected totals are lower bounds.
- `ranked_options[0]` is the recommended option.
- Signed `remaining_vs_plan` values are positive when still below the planned baseline and negative when above it.
- `fiber_floor_gap` is never negative.
- `sodium_above_plan_reference` is never negative.

The output is advisory only. It authorizes no Food Log or pantry write.
