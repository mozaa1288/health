---
name: log-food
description: Add, identify, review, correct, or remove consumed food and drinks in daily append-only JSONL logs stored in ChatGPT Library. Use for meal logging, ambiguous food lookup, packaged foods, barcodes, photos, restaurant meals, daily totals, and corrections.
---

# Log Food

Record actual consumption as one meal object per line in the daily ChatGPT Library file. Do not update pantry inventory merely because food was eaten.

Read [references/sources-and-schema.md](references/sources-and-schema.md) for the file location, schema, and append rules. Read [references/lookup-workflow.md](references/lookup-workflow.md) when a food is not already an unambiguous exact match.

## Add or correct food

1. Resolve the consumed date and time in `America/Los_Angeles`.
2. Search Library for the exact title `food-log-YYYY-MM-DD.jsonl` and prepare it locally. A missing file means an empty day.
3. Run `scripts/food_log_jsonl.py read` and check current entries before writing.
4. Reuse one high-confidence prior JSONL item when brand, product, flavor, serving basis, and user wording agree. Otherwise resolve nutrition from the validated plan, current label or barcode, ranked lookup, canonical nutrition CSV, or official restaurant nutrition.
5. Ask one targeted question only when food identity, consumed quantity, or a calorie-dense addition cannot be resolved safely. Clear food with unresolved nutrition may be logged with null nutrients and a short note.
6. Preserve the user's wording. Use explicit item quantities and deterministic conversions:
   - mass is normalized to grams;
   - US food volume is normalized to milliliters;
   - count remains count;
   - volume or count needs `density_g_per_ml`, `grams_per_unit`, or explicit sourced edible grams before CSV nutrition can be scaled.
7. Compile the meal:

```bash
python scripts/food_log_compiler.py entry.json \
  --nutrition-csv nutrition_corrected.csv \
  --output meal.json
```

8. Append and validate:

```bash
python scripts/food_log_jsonl.py append \
  food-log-YYYY-MM-DD.jsonl meal.json
python scripts/food_log_jsonl.py validate \
  food-log-YYYY-MM-DD.jsonl
```

9. Save the changed daily file back to the same Library path.

An identical retry is a no-op. A changed meal with the same stable `entry_id` is a correction and must use `--correction`; it appends the next revision. Removal uses the `delete` command and appends a tombstone. Never rewrite prior lines.

## Review totals

Prepare each requested daily file, run `food_log_jsonl.py read`, and use the returned current records and summary. The final revision for each `entry_id` wins; deleted entries are excluded. Null nutrition is unknown, not zero.

## Rules

- Never use a Google Sheet as a runtime food-log source or destination.
- Never log plans, recommendations, purchases, medications, supplements, or water unless explicitly requested.
- Never infer pantry changes from consumption.
- Never invent a serving size, label value, restaurant configuration, conversion factor, or consumed quantity.
- Fuzzy rank is not confirmation. Exact barcode, current label, or one unambiguous prior match may be automatic; otherwise require a numbered choice.
- Use dry weights only when explicitly stated. Use drained weight for brined foods when appropriate.

## Response

After a write, report the meal, local time, calories, protein, carbohydrates, and fat, plus one concise note for estimates, proxies, or unresolved nutrition.
