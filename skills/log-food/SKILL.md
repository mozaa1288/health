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

Read [references/sources-and-schema.md](references/sources-and-schema.md) for the record rules. Read [references/lookup-workflow.md](references/lookup-workflow.md) only when the food is ambiguous.

## Algorithm

1. Resolve the consumed date and time in `America/Los_Angeles`.
2. Fetch that date's exact JSONL file from the folder above. Missing means an empty day. Run `scripts/food_log_jsonl.py read`.
3. Parse the consumed items and quantities. Reuse an exact prior match or resolve nutrition from a label, barcode, canonical source, restaurant source, or `scripts/food_lookup.py`. Ask one short question only for a material ambiguity.
4. Run `scripts/food_log_compiler.py` to create one meal record with standardized units and nutrients.
5. Run `scripts/food_log_jsonl.py append`, then `validate`. An identical retry is a no-op; corrections append the next revision; removals append a deleted revision.
6. Upload a missing file or replace the existing file bytes in place. Verify the filename and parent folder.
7. Report the meal, local time, calories, protein, carbohydrates, and fat. Label estimates or unknown nutrition briefly.

## Rules

- The user authorizes creating or replacing `food-log-YYYY-MM-DD.jsonl` files in this folder without repeated confirmation.
- Do not use a spreadsheet for food logs.
- Do not log plans, recommendations, purchases, medications, supplements, or water unless explicitly requested.
- Do not change pantry inventory from consumption.
- Do not invent food identity, quantity, serving conversion, or nutrition. Unknown is not zero.
- Do not delete, move, share, or change permissions without explicit authorization.
- Honor any platform-required approval; do not bypass it.
