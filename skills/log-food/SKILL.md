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

## Hard constraint — nutrition data never comes from the internet

Read this before anything else. It is the one rule in this skill with no exception, no override, and no judgment call.

**Banned, unconditionally:**

- `web_search`, `web_fetch`, browsing, or any network call made to obtain nutrition data
- Nutrition numbers recalled from your own training data
- "Typical values" for a category of food
- A brand's published figures you remember but cannot locate on Drive

**The only legitimate sources are on Drive:** the canonical nutrition CSV, the preferred-food map, the Open Food Facts index, and prior daily JSONL history. If a number is not in one of those four, you do not have that number.

**Why this outranks being helpful.** This log is a longitudinal health record. A fabricated 400 kcal entry does not surface later as an error — it surfaces as data, and it silently corrupts every trend, target, and decision built on top of it for months afterward. A missing value is visible and fixable. A confident wrong value is neither. No amount of "close enough" beats `null` here.

**When Drive does not have it:** log the item with null nutrition and say so plainly, or ask one short question. Never guess. Never estimate from memory. Never fill the gap just this once because the user seems to be in a hurry.

**If you find yourself reaching for the web, stop.** That impulse is precisely the failure this rule exists to catch. Log the null and move on.

## Algorithm

1. Resolve the consumed date and time in `America/Los_Angeles`. The consumed date is `local_date`; every later step and the reporting contract use that value, not the current date.
2. Fetch the exact JSONL file for `local_date`. Missing means an empty day. Run `scripts/food_log_jsonl.py read` before writing, and hold the parsed records — the reporting contract reuses this read rather than opening the file again.
3. Resolve every food. **The hard constraint above governs this step; Drive only, no exceptions.**
   - Use an exact current label, exact barcode, or one unambiguous high-confidence prior match directly.
   - Otherwise, run `scripts/food_lookup.py search` before compiling. Pass useful separate search terms plus recent daily JSONL history, the preferred-food map, canonical nutrition CSV, and Open Food Facts index when relevant.
   - Automatically select only an exact barcode or one unambiguous prior match with the same brand, product, flavor, and serving basis. Otherwise show the numbered candidates, ask the user to choose, then run `scripts/food_lookup.py select`.
   - If no safe match exists, ask one short question for material ambiguity. A clearly consumed item may be logged with null nutrition when only its nutrition is unresolved.
4. Run `scripts/food_log_compiler.py` to create one `food_log.meal.v1` record with standardized units and nutrients.
5. Run `scripts/food_log_jsonl.py append`, then `validate`. An identical retry is a no-op; corrections append the next revision; removals append a deleted revision.
6. Upload a missing file or replace the existing file bytes in place. Verify the filename and parent folder. **Always write with `contentMimeType: text/plain` and `disableConversionToGoogleType: true`** — content stays JSONL, but `application/x-ndjson` is unreadable by `read_file_content`, forcing consumers into base64. Keep the `.jsonl` extension; the mime type is what matters.
7. Report per the Food-Log Reporting Contract below.

## Record rules

- Store one complete meal revision per JSONL line.
- Include stable `entry_id`, `revision`, `status`, timestamps, local date, meal, description, original wording, item quantities, normalized units, nutrition, sources, and totals.
- **Revision resolution:** for each `entry_id`, the highest `revision` wins; omit any entry whose winning revision has `status == "Deleted"`. Every total in this file uses this rule.
- Normalize mass to grams, US food volume to milliliters, and discrete items to count.
- Scale nutrition from edible grams. Volume or count requires a sourced conversion or explicit edible grams. Reject conflicting conversions.
- Record the Drive source for every nutrition figure. A figure with no recordable Drive source is not eligible to be logged as a number.

## Rules

- Nutrition comes from Drive or it does not come at all. See the hard constraint above.
- The user authorizes creating or replacing `food-log-YYYY-MM-DD.jsonl` files in this folder without repeated confirmation.
- Do not use a spreadsheet for food logs.
- Do not log plans, recommendations, purchases, medications, supplements, or water unless explicitly requested.
- Do not change pantry inventory from consumption.
- Do not invent food identity, quantity, serving conversion, or nutrition. Unknown is not zero.
- Removing a logged meal means appending a deleted revision. Never delete, move, share, or reassign permissions on Drive files without explicit authorization.
- Honor any platform-required approval; do not bypass it.

# Food-Log Reporting Contract

## Fixed daily targets

Hard-coded. Never read targets from a meal plan, another skill, prior conversation, Personal Context, or any external file.

| Calories | Protein | Carbohydrates | Fat |
|---:|---:|---:|---:|
| 2,077 kcal | 150 g | 194 g | 86 g |

## When this applies

Render both tables after every successful append — new entry, correction, or removal. A read-only review renders Table 2 only.

## Computing the numbers

1. Use the `local_date` resolved in Algorithm step 1 and the records already read in step 2.
2. Apply the revision-resolution rule from Record rules.
3. `Existing total` = sum of `totals.calories`, `totals.protein_g`, `totals.carbs_g`, `totals.fat_g` across the surviving records, computed *before* this operation's append.
4. `Entry delta`:
   - New entry → `+ entry total`
   - Correction → `corrected total − previous revision total`
   - Removal → `− previous revision total`
5. `Running total = Existing total + Entry delta`
6. `Remaining = target − Running total`. Signed: negative means over.
7. `% of target = Running total ÷ target`, rounded to a whole percent.

Never include more than one revision of the same `entry_id`.

## Required output

One caption line — meal and local time — then the tables.

### Table 1 — Entry breakdown

Rows in the order the user stated them. Omit this table for a removal; name the removed description in the caption instead.

**Lunch — 12:40 PM**

| Item | Amount | Calories | Protein | Carbs | Fat |
|---|---:|---:|---:|---:|---:|
| Grilled salmon fillet | 140 g | 290 | 30 g | 0 g | 18 g |
| Steamed jasmine rice *(estimated)* | 158 g | 222 | 4 g | 48 g | 1 g |
| **Entry total** | | **512** | **34 g** | **48 g** | **19 g** |

### Table 2 — Day

| Day | Calories | Protein | Carbs | Fat |
|---|---:|---:|---:|---:|
| Before this entry | 1,190 | 88 g | 102 g | 51 g |
| This entry | +512 | +34 g | +48 g | +19 g |
| **Running total** | **1,702** | **122 g** | **150 g** | **70 g** |
| Target | 2,077 | 150 g | 194 g | 86 g |
| **Remaining** | **375** | **28 g** | **44 g** | **16 g** |
| % of target | 82% | 81% | 77% | 81% |

For a correction, insert a `Previous revision` row above `This entry` carrying the negated prior total. For a removal, label the delta row `Removed`.

## Formatting rules

1. Calories are whole numbers. Macros round to the nearest gram and carry a `g` suffix. Compute every sum from unrounded values; round only for display.
2. Thousands separators on all four-digit values.
3. Signed deltas in the `This entry`, `Previous revision`, and `Removed` rows. `Remaining` goes negative when over target — never the `0 (X over)` form.
4. Mark uncertain amounts in the item name with `*(estimated)*`.

## Unknown values

Never substitute zero for unknown nutrition.

- An unknown cell in Table 1 renders as `—`.
- Any unknown component makes the affected `Entry total`, `Running total`, and `Remaining` a lower bound: `≥ 1,702`.
- Add one footnote naming the item and the missing nutrients.
- State the reason once: the item was not found in the Drive sources. Do not offer to look it up online.

## Assumptions note

After the tables, at most three single-line bullets, and only for quantity estimates, product substitutions, or volume/count-to-gram conversions. No bullets if none apply.
