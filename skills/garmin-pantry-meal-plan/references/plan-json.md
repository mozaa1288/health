# `plan.json` Structure

Use this shape as the compiler input. Values below illustrate structure only.

```json
{
  "nutrition_database": {
    "drive_file_id": "1tFqCTo50otb-nuRuy1Xt7yQWI3iddiLM",
    "title": "nutrition_corrected.csv",
    "expected_sha256": "optional-current-hash",
    "id_column": "Unnamed: 0",
    "name_column": "name",
    "serving_column": "serving_size [g]"
  },
  "produce_buffer_pct": 3,
  "meals": [
    {
      "id": "2026-07-27-lunch",
      "date": "2026-07-27",
      "name": "Example bowl",
      "ingredients": [
        {
          "ingredient": "Quinoa",
          "canonical_name": "quinoa",
          "quantity": 80,
          "unit": "g",
          "nutrition_grams_total": 80,
          "nutrition_row_id": 443,
          "nutrition_match_type": "exact",
          "nutrition_match_note": "Track dry grams before cooking."
        }
      ]
    }
  ],
  "inventory": {
    "quinoa": {
      "canonical_unit": "g",
      "available_amount": 120,
      "status": "confirmed",
      "source": "Pantry Inventory",
      "last_confirmed": "2026-07-26"
    }
  },
  "packages": {
    "quinoa": {
      "canonical_unit": "g",
      "package_size": 454,
      "category": "Grains",
      "purchase_label": "Quinoa, dry",
      "loose_produce": false
    }
  }
}
```

## Ingredient requirements

Each ingredient requires:

- `ingredient`
- `canonical_name`
- `quantity`
- `unit`
- `nutrition_grams_total` or an explicit canonical conversion sufficient to derive edible grams
- `nutrition_row_id` or an unambiguous `nutrition_name`
- `nutrition_match_type` of `exact` or `proxy`
- `nutrition_match_note` for every proxy

Use `canonical_amount_per_unit` and `canonical_unit` when the recipe unit cannot be converted directly. Use `nutrition_grams_per_canonical_unit` for repeatable count-to-gram conversion.

Do not add a `macros` object to a meal. The compiler rejects manual macros.

Set `pantry_on_hand: true` only for items intentionally excluded from grocery reconciliation, such as water or a non-purchased pantry seasoning. Do not use it to bypass the inventory model for ordinary recipe ingredients.

## Package requirements

Every ingredient with a net shortfall requires package metadata:

- compatible `canonical_unit`;
- positive `package_size`;
- `category`;
- `purchase_label`;
- `loose_produce` boolean.

The compiler aggregates exact recipe demand, subtracts eligible inventory, applies any allowed produce buffer, and then rounds to package size.
