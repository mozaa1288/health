---
name: log-food
description: Add food and drinks the user consumed to a durable running nutrition log backed by Google Drive sources, including barcode/name lookup for packaged foods and configurable restaurant meals resolved from current official nutrition. Use for requests such as “log my lunch,” “I ate a Field Roast sausage,” “scan this barcode,” “I ate a Chipotle burrito,” “I ate today’s planned dinner,” “what have I eaten today?”, or corrections and deletions to prior food-log entries.
---

# Log Food

Maintain actual consumption in the dedicated `Food Consumption Log` Google Sheet. Resolve every Drive asset through the authoritative `Health Data Registry` before use. Reuse the weekly meal plan, preferred-food map, and canonical nutrition CSV so planned and actual nutrition stay numerically compatible.

Never write `Food Log` rows to `Pantry & Fridge Inventory Tracker`. The pantry tracker is a read-only planning or reconciliation source unless the user separately and explicitly asks to update remaining inventory.

## Read the contract

Read [references/sources-and-schema.md](references/sources-and-schema.md) before every operation. Use `scripts/food_log_compiler.py` for every new or revised entry that contains nutrition.

## Choose the operation

### Add consumed food

1. Resolve the consumed local date and time in `America/Los_Angeles`. Interpret “today,” “yesterday,” and meal dayparts in that timezone.
2. Resolve and verify the required assets from the registry by exact asset key and Drive ID. Verify the dedicated `food-log` asset has Drive ID `12Exzl-EZWxkiN0cd9XafE9R7a_MBoNiZuio46deANnQ`.
3. Read the dedicated spreadsheet metadata before reading or writing. Verify `Food Log`, `Daily Summary`, `Saved Orders`, and `Source Registry` against the schema reference. Write consumption rows only to `Food Log`.
4. Resolve the food source:
   - If the user says they ate a planned meal, fetch the validated `compiled_plan.json` covering that date and copy its exact item quantities, row IDs, and nutrition. Apply stated substitutions or partial portions before compiling.
   - If the user names a restaurant or chain, read [references/restaurant-lookup.md](references/restaurant-lookup.md) and follow it. Reuse confirmed builds from `Saved Orders`; use current first-party nutrition for the actual configured order, not a generic database proxy.
   - Otherwise fetch the live preferred-food map and current canonical nutrition CSV. Use a preferred mapped row ID whenever applicable.
   - For an unmatched packaged product, read [references/openfoodfacts-lookup.md](references/openfoodfacts-lookup.md), fetch the compact indexed source from Drive, and run `scripts/openfoodfacts_lookup.py`. Prefer exact barcode lookup; accept a text result only when the script marks it `resolved`.
   - Use user-supplied package-label nutrition when the canonical database lacks the exact product.
   - If nutrition cannot be resolved without guessing, log the item with blank nutrition and disclose the gap. Ask one targeted quantity or product question only when it would materially improve the entry and the user did not request a quick log.
5. Build one entry JSON object using the schema reference. Give the meal one stable `entry_id`; give each component a unique `item_id`.
6. Run:

```bash
python scripts/food_log_compiler.py entry.json \
  --nutrition-csv nutrition_corrected.csv \
  --output compiled_entry.json
```

Resolve the script relative to this skill directory when the working directory differs.
7. Append the compiler’s `sheet_rows` only to the dedicated sheet’s `Food Log` tab. Preserve all existing rows. Before appending, search the bounded `Entry ID` and `Item ID` columns:
   - exact duplicates: do not append;
   - a correction to an existing entry: replace only that entry’s rows;
   - a new entry: append after the last populated row.
8. Re-read the written rows and verify entry IDs, dates, items, quantities, nutrition values, and source metadata. When `Daily Summary` is formula-backed, also verify the affected date recalculated; never append item rows to it.
9. Do not change pantry inventory merely because food was logged. Reconcile pantry quantities only when the user explicitly states the remaining amount; then follow the pantry skill’s reconciliation rules as a separate operation.

### Review totals

Resolve and verify the `food-log` asset, then read the bounded populated region of its `Food Log` tab. Aggregate item rows by `Entry ID` before presenting meals, and sum nutrients by the user’s requested local-date window. Treat blank nutrition as unknown, not zero, and identify affected entries. Use `Daily Summary` only when its values reconcile to the underlying active rows.

### Correct or remove an entry

Resolve and verify the `food-log` asset. Resolve the exact entry from date, meal, description, and item rows. Show the intended target when more than one entry plausibly matches. Replace a corrected entry by recompiling it; delete rows only when the user explicitly asks to remove the entry. Never search for or modify consumption rows in the pantry tracker.

## Input rules

- Prefer exact quantities. Preserve the user’s original wording in `Description` and normalized quantities in item columns.
- Track dry grains and pasta as dry grams when copied from the meal plan. Do not reinterpret a cooked portion as dry weight.
- Use drained edible weight for brined or jarred foods unless its mapping says otherwise.
- For count items, require an explicit edible-gram conversion before CSV-backed nutrition is calculated.
- Never invent a product, row ID, serving size, or label value.
- Never treat a configurable restaurant item such as a burrito, bowl, sandwich, pizza, or salad as nutritionally complete without its selected components or an official configured total.
- Mark every proxy or estimate clearly. Keep unresolved nutrition cells blank.
- Do not log supplements, medications, or water as food unless the user explicitly requests it.

## Response

After a successful write, confirm the meal, local time, calories, protein, carbohydrates, and fat. Mention unresolved items or proxies in one concise sentence. For a simple successful entry, do not dump the underlying rows.
