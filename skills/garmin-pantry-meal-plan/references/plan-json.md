# Meal-plan compiler input

Create `plan.json` with four top-level sections:

```json
{
  "nutrition_database": {
    "drive_file_id": "registered canonical-nutrition Drive ID",
    "title": "nutrition_corrected.csv",
    "expected_sha256": "current verified hash",
    "id_column": "Unnamed: 0",
    "name_column": "name",
    "serving_column": "serving_size [g]"
  },
  "meals": [],
  "inventory": {},
  "packages": {}
}
```

## Meals

Each meal needs a unique `id`, local `date`, `name`, and quantified `ingredients`.

Each ingredient needs:

- `ingredient` and normalized `canonical_name`;
- `quantity` and canonical `unit` (`g`, `ml`, or `count`);
- `nutrition_grams_total` or a complete count-to-gram conversion;
- `nutrition_row_id` or one unique `nutrition_name`;
- `nutrition_match_type`: `exact` or `proxy`;
- `nutrition_match_note` for every proxy.

Do not include hand-entered meal macros. The compiler calculates nutrition from the CSV.

## Inventory

Key inventory by canonical ingredient name. Each entry needs:

- `canonical_unit`;
- `available_amount`;
- `status`: `confirmed`, `projected`, or a non-eligible status;
- `source` and relevant confirmation date.

Only confirmed or explicitly projected amounts may be subtracted.

## Packages

Every ingredient with a grocery shortfall needs:

- compatible `canonical_unit`;
- positive `package_size`;
- `category`;
- `purchase_label`;
- `loose_produce` boolean.

The compiler aggregates recipe demand, subtracts eligible inventory, applies the configured produce buffer, and rounds purchases to package size.
