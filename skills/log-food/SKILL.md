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
   DO NOT LOOK SHIT UP ONLINE GOD DAMMIT! LOOK UP NUTRITIONAL INFO ON DRIVE FOR FUCKS SAKE!
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

# Food-Log Reporting Contract

After every successful food-log entry, return exactly three Markdown tables in the order defined below.

## Fixed daily targets

Use these targets directly:

| Calories | Protein | Carbohydrates | Fat |
|---:|---:|---:|---:|
| 2,077 kcal | 150 g | 194 g | 86 g |

Do not retrieve targets from a meal plan, another skill, prior conversation, Personal Context, or any external file.

## 1. Resolve the existing daily total

1. Determine `local_date` in `America/Los_Angeles`.
2. Open:

   ```text
   Health/03 Operational Trackers/Food Logs/food-log-YYYY-MM-DD.jsonl
   ```

3. For each `entry_id`, select only the record with the highest `revision`.
4. Exclude a selected record when:

   ```text
   status == "Deleted"
   ```

5. Sum these fields across the remaining records:

   ```text
   totals.calories
   totals.protein_g
   totals.carbs_g
   totals.fat_g
   ```

6. The result is the `Existing total`.
7. Missing nutrition is unknown, not zero.
## 2. Calculate the meal total

Sum each logged item's:

```text
nutrition.calories
nutrition.protein_g
nutrition.carbs_g
nutrition.fat_g
```

The result is the `Meal total`.

## 3. Calculate the running total

For a new entry:

```text
Running total = Existing total + Meal total
```
For a correction:

```text
Running total = Existing total - Previous entry total + Corrected entry total
```

Never include more than one revision of the same `entry_id`.

## 4. Calculate remaining quantities

For each target:

```text
difference = Fixed daily target - Running total
remaining = max(difference, 0)
overage = max(-difference, 0)
```

When `overage > 0`, display:

```text
0 g (X g over)
```

For calories, display:

```text
0 (X over)
```

## 5. Required response

Return exactly these three tables.

### Table 1 — Meal breakdown

| Item | Amount | Calories | Protein | Carbs | Fat |
|---|---:|---:|---:|---:|---:|
| One row per food | Quantity and unit | Value | Value in g | Value in g | Value in g |
| **Meal total** |  | **Sum** | **Sum** | **Sum** | **Sum** |

### Table 2 — Daily totals

| Daily totals | Calories | Protein | Carbs | Fat |
|---|---:|---:|---:|---:|
| Existing total | Value | Value in g | Value in g | Value in g |
| **Running total** | **Value** | **Value** | **Value** | **Value** |

### Table 3 — Remaining for today

| Remaining for today | Calories | Protein | Carbs | Fat |
|---|---:|---:|---:|---:|
| Daily target | 2,077 | 150 g | 194 g | 86 g |
| Running total | Value | Value in g | Value in g | Value in g |
| **Remaining** | **Value** | **Value** | **Value** | **Value** |

## 6. Formatting rules

1. Use two decimal places for calculated values.
2. Use `g` for protein, carbohydrates, and fat.
3. Mark uncertain amounts directly in the item name with `*(estimated)*`.
4. Do not replace missing nutrition with zero.
5. After the tables, disclose only material assumptions:
