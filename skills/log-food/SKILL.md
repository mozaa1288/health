---
name: log-food
description: Add, identify, review, correct, or remove food and drinks in the authoritative Google Drive Food Consumption Log. Use for meal logging, ambiguous food-name lookup and user selection, packaged foods, barcodes, package photos, restaurant meals, planned meals, daily totals, and corrections.
---

# Log Food

Record what the user actually consumed in the dedicated Food Consumption Log. Do not change pantry inventory merely because food was eaten.

Read [references/sources-and-schema.md](references/sources-and-schema.md) for the registry identity and exact Food Log columns.
Read [references/lookup-workflow.md](references/lookup-workflow.md) whenever a food or packaged product is not already an unambiguous exact match.

## Add or correct food

1. Resolve the consumed date and time in `America/Los_Angeles`.
2. Resolve `food-log` through the live Health Data Registry and verify the dedicated spreadsheet, required tabs, and 27-column `Food Log` schema.
3. Read existing entries for the target date before writing.
4. Reuse a single high-confidence active prior Food Log match when the brand, product, flavor, serving basis, and the user's wording agree.
5. Otherwise resolve nutrition in this order:
   - a validated planned meal covering that date;
   - the user's current package label or exact barcode;
   - ranked lookup across prior Food Log rows, the preferred-food map, Open Food Facts, and the canonical nutrition CSV;
   - current official restaurant nutrition for the user's actual configured order.
6. For ranked lookup, run `scripts/food_lookup.py search` with two or more useful terms when available. Present the compact numbered results and have the user choose when the top result is not decisive. Run `scripts/food_lookup.py select` on the saved candidate file before compiling the entry. Never silently choose among materially different products.
7. Ask one targeted question only when the food, quantity, calorie-dense addition, or configurable restaurant build cannot be identified safely. If the item is clear but nutrition is unavailable, log it with blank nutrients and a short unresolved note.
8. Build one stable entry with one row per component. Preserve the user's wording and mark proxies or estimates clearly.
9. For entries with nutrition, run:

```bash
python scripts/food_log_compiler.py entry.json \
  --nutrition-csv nutrition_corrected.csv \
  --output compiled_entry.json
```

10. Write only to the `Food Log` tab:
   - identical retry: no-op;
   - correction: replace all rows for that Entry ID;
   - new meal: append after the last populated row;
   - removal: mark the entry Deleted unless permanent deletion is explicitly requested.
11. Read the affected rows back and verify IDs, date, meal, quantities, nutrients, sources, and status. Check the affected Daily Summary date when practical.

## Review totals

Read active Food Log rows for the requested dates, group components by Entry ID, and sum known nutrients. Blank nutrition is unknown, not zero. Use Daily Summary only when it agrees with the item rows.

## Rules

- Never write consumption rows to the pantry tracker.
- Never invent a serving size, nutrition row, label value, restaurant configuration, or consumed quantity.
- Never treat fuzzy lookup rank as confirmation. Exact barcode, exact current label, or an unambiguous high-confidence prior match may be automatic; otherwise require the user's numbered choice.
- Prefer previously confirmed active Food Log matches over generic database results, but require the same brand, product line, flavor when relevant, and serving basis.
- For photos, ask about uncertain oil, dressing, cheese, nuts, sauces, or other calorie-dense components before asking about low-calorie produce. Exclude unreported additions instead of silently estimating them.
- Use dry weights only when the user or planned meal specifies dry weight.
- Use drained weight for brined foods when appropriate and explicit edible-gram conversions for count items.
- Do not log plans, recommendations, purchases, supplements, medications, or water as consumed food unless explicitly requested.

## Response

After a lookup, show at most eight numbered candidates with product, serving, calories, protein, source, and match note.

After a write, report the meal, local time, calories, protein, carbohydrates, and fat, plus one concise note for any proxy, excluded addition, or unresolved nutrition.
