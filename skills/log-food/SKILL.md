---
name: log-food
description: Add, review, correct, or remove food and drinks in the authoritative Google Drive Food Consumption Log. Use for meal logging, planned meals, packaged foods, restaurant meals, daily totals, and corrections.
---

# Log Food

Record what the user actually consumed in the dedicated Food Consumption Log. Do not change pantry inventory merely because food was eaten.

Read [references/sources-and-schema.md](references/sources-and-schema.md) for the registry identity and exact Food Log columns.

## Add or correct food

1. Resolve the consumed date and time in `America/Los_Angeles`.
2. Resolve `food-log` through the live Health Data Registry and verify the dedicated spreadsheet, required tabs, and 27-column `Food Log` schema.
3. Read existing entries for the target date before writing.
4. Resolve nutrition in this order:
   - a validated planned meal covering that date;
   - the preferred-food map and canonical nutrition CSV;
   - the user's package label;
   - exact barcode or product data from the registered Open Food Facts index;
   - current official restaurant nutrition for the user's actual configured order.
5. Ask one targeted question only when the food, quantity, or configurable restaurant build cannot be identified safely. If the item is clear but nutrition is unavailable, log it with blank nutrients and a short unresolved note.
6. Build one stable entry with one row per component. Preserve the user's wording and mark proxies or estimates clearly.
7. For entries with nutrition, run:

```bash
python scripts/food_log_compiler.py entry.json \
  --nutrition-csv nutrition_corrected.csv \
  --output compiled_entry.json
```

8. Write only to the `Food Log` tab:
   - identical retry: no-op;
   - correction: replace all rows for that Entry ID;
   - new meal: append after the last populated row;
   - removal: mark the entry Deleted unless permanent deletion is explicitly requested.
9. Read the affected rows back and verify IDs, date, meal, quantities, nutrients, sources, and status. Check the affected Daily Summary date when practical.

## Review totals

Read active Food Log rows for the requested dates, group components by Entry ID, and sum known nutrients. Blank nutrition is unknown, not zero. Use Daily Summary only when it agrees with the item rows.

## Rules

- Never write consumption rows to the pantry tracker.
- Never invent a serving size, nutrition row, label value, restaurant configuration, or consumed quantity.
- Use dry weights only when the user or planned meal specifies dry weight.
- Use drained weight for brined foods when appropriate and explicit edible-gram conversions for count items.
- Do not log plans, recommendations, purchases, supplements, medications, or water as consumed food unless explicitly requested.

## Response

After a write, report the meal, local time, calories, protein, carbohydrates, and fat, plus one concise note for any proxy or unresolved nutrition.
