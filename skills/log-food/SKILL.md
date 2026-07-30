---
name: log-food
description: Log, review, correct, or remove consumed food in daily JSONL files stored in the hard-coded Google Drive Food Logs folder. Use for meals, snacks, drinks, food photos, labels, barcodes, restaurant food, nutrition totals, and corrections.
---

# Log Food

Store actual consumption in:

```text
Health/03 Operational Trackers/Food Logs/food-log-YYYY-MM-DD.jsonl
```

Drive folder ID: `13E1t9q2JQrCliQyO8xecHNcDdUyhMjaI`.

## Algorithm

1. Resolve the consumed date and time in `America/Los_Angeles`.
2. Fetch that date's exact JSONL file from the folder above. Missing means an empty day. Run `scripts/food_log_jsonl.py read` before writing.
3. Resolve every food:
   - Use an exact current label, exact barcode, or one unambiguous high-confidence prior match directly.
   - Otherwise, run `scripts/food_lookup.py search` before compiling. Pass useful separate search terms plus recent daily JSONL history, the preferred-food map, canonical nutrition CSV, and Open Food Facts index when relevant.
   - Automatically select only an exact barcode or one unambiguous prior match with the same brand, product, flavor, and serving basis. Otherwise show the numbered candidates, ask the user to choose, then run `scripts/food_lookup.py select`.
   - If no safe match exists, ask one short question for material ambiguity. A clearly consumed item may be logged with null nutrition when only its nutrition is unresolved.
4. Run `scripts/food_log_compiler.py` to create one `food_log.meal.v1` record with standardized units and nutrients.
5. Run `scripts/food_log_jsonl.py append`, then `validate`. An identical retry is a no-op; corrections append the next revision; removals append a deleted revision.
6. Upload a missing file or replace the existing file bytes in place. Verify the filename and parent folder.
7. Report the meal, local time, calories, protein, carbohydrates, and fat. Briefly label estimates or unknown nutrition.

## Record rules

- Store one complete meal revision per JSONL line.
- Include stable `entry_id`, `revision`, `status`, timestamps, local date, meal, description, original wording, item quantities, normalized units, nutrition, sources, and totals.
- The final revision for each `entry_id` wins; omit entries whose final revision is `Deleted`.
- Normalize mass to grams, US food volume to milliliters, and discrete items to count.
- Scale nutrition from edible grams. Volume or count requires a sourced conversion or explicit edible grams. Reject conflicting conversions.

## Rules

- The user authorizes creating or replacing `food-log-YYYY-MM-DD.jsonl` files in this folder without repeated confirmation.
- Do not use a spreadsheet for food logs.
- Do not log plans, recommendations, purchases, medications, supplements, or water unless explicitly requested.
- Do not change pantry inventory from consumption.
- Do not invent food identity, quantity, serving conversion, or nutrition. Unknown is not zero.
- Do not delete, move, share, or change permissions without explicit authorization.
- Honor any platform-required approval; do not bypass it.
