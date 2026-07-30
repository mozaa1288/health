# Food Log Storage and Schema

## Canonical storage

Food consumption is stored only in ChatGPT Library:

```text
food-log-YYYY-MM-DD.jsonl
```

Each local date in `America/Los_Angeles` has one file and each line is one complete meal revision. Use the Library workflow to prepare the file locally, run the bundled scripts, then save the updated file back to the same path. Do not use the former spreadsheet at runtime. It is a legacy migration input only.

Nutrition lookup assets, weekly plans, pantry data, and food evidence remain separate. Resolve those through their existing workflows only when needed.

## Meal record

Schema version: `food_log.meal.v1`.

Required top-level fields:

| Field | Meaning |
|---|---|
| `schema_version` | `food_log.meal.v1` |
| `record_type` | `meal` |
| `entry_id` | Stable identifier for the eating event |
| `revision` | Starts at 1 and increments for the same `entry_id` |
| `status` | `Active` or `Deleted` |
| `logged_at` | ISO-8601 local timestamp with offset |
| `local_date` | `YYYY-MM-DD`; must match filename and timestamp |
| `meal` | Breakfast, Lunch, Dinner, Snack, or Other |
| `description` | User-facing meal description |
| `original_text` | User's supplied wording |
| `planned_meal_id` | Matching plan meal or null |
| `last_updated` | ISO-8601 timestamp with offset |
| `items` | Non-empty list of food components |
| `totals` | Meal nutrients; null when a core nutrient is incomplete |
| `known_nutrition_subtotal` | Sum of known item nutrition |

Each item contains stable `item_id`, item name, original `quantity` and `unit`, normalized `base_quantity`, edible grams when known, nutrition, match/source/confidence metadata, and optional source evidence.

Example:

```json
{
  "schema_version": "food_log.meal.v1",
  "record_type": "meal",
  "entry_id": "meal-38f097d97b473fad",
  "revision": 1,
  "status": "Active",
  "logged_at": "2026-07-29T08:00:00-07:00",
  "local_date": "2026-07-29",
  "meal": "Breakfast",
  "description": "Greek yogurt with berries and seeds",
  "original_text": "1 cup Fage, 20 blueberries, 2 tbsp chia, quarter cup pepitas",
  "planned_meal_id": null,
  "last_updated": "2026-07-29T15:42:00-07:00",
  "items": [
    {
      "item_id": "item-1f5593ae944a79f9",
      "item": "Chia seeds",
      "quantity": 2,
      "unit": "tbsp",
      "base_quantity": {"amount": 30, "unit": "ml"},
      "edible_grams": 20,
      "nutrition": {
        "calories": 97.2,
        "protein_g": 3.31,
        "carbs_g": 8.43,
        "fat_g": 6.15,
        "fiber_g": 6.88,
        "sodium_mg": 3.2
      },
      "nutrition_row_id": "1181",
      "nutrition_match": "Exact",
      "source": "Canonical CSV",
      "confidence": "High",
      "note": "10 g per tablespoon from confirmed serving conversion",
      "source_url": null,
      "source_accessed": null
    }
  ],
  "totals": {
    "calories": 97.2,
    "protein_g": 3.31,
    "carbs_g": 8.43,
    "fat_g": 6.15,
    "fiber_g": 6.88,
    "sodium_mg": 3.2
  },
  "known_nutrition_subtotal": {
    "calories": 97.2,
    "protein_g": 3.31,
    "carbs_g": 8.43,
    "fat_g": 6.15,
    "fiber_g": 6.88,
    "sodium_mg": 3.2
  }
}
```

## Append and history behavior

- New meal: append revision 1.
- Identical retry: no-op.
- Correction: append the full corrected meal with the same `entry_id` and next revision.
- Removal: append a `Deleted` revision; do not erase earlier lines.
- Current view: final revision for each `entry_id` wins; omit final `Deleted` records.
- Append with the bundled helper, which validates the filename/date, schema, revision sequence, IDs, nutrients, and newline before an `O_APPEND` write.

## Unit rules

The compiler normalizes mass to `g`, US food volume to `ml`, and discrete items to `count`. Nutrition scaling is always based on edible grams.

- Mass quantities convert directly.
- Volume requires a sourced `density_g_per_ml`, a sourced `grams_per_unit`, or explicit sourced `nutrition_grams_total`.
- Count requires a sourced `grams_per_unit` or explicit sourced `nutrition_grams_total`.
- When explicit grams conflict with a deterministic conversion, compilation fails.
- Keep the conversion source or estimate in the item note.

## Legacy migration

The old consumption spreadsheet is read only for the one-time historical migration. Export its exact legacy CSV and run:

```bash
python scripts/migrate_food_log_csv.py legacy_food_log.csv migrated/
```

Validate every generated daily file before saving it back under the same exact Library filename. Do not keep the spreadsheet synchronized after migration.
