---
name: update-pantry
description: Update the user's durable Google Drive Pantry & Fridge Inventory Tracker from grocery receipts, typed or pasted item lists, and photos of a pantry, refrigerator, freezer, counter, or groceries. Use when the user says what they bought or currently have, asks to scan a receipt, provides one or more inventory photos, or asks to add, reconcile, or mark pantry items out. Handles exact quantities, partial packages, overlapping photos, matching existing rows, new pantry rows, evidence provenance, and conservative confirmation.
---

# Update Pantry

## Overview

Turn receipts, lists, and inventory photos into a validated, auditable update to the registered pantry tracker. Extract observations with visual reasoning, then use `scripts/plan_updates.py` as the deterministic merge and safety gate before editing Google Sheets.

Read `references/pantry-capture-contract.md` before acting. Also use the connected Google Drive and Google Sheets skills and obey their live-read, write, and verification requirements.

## Resolve registered assets

Start from the Health Data Registry spreadsheet:

- Registry spreadsheet ID: `1AHvwyDzlhznRFvAry5Tqj37Ol9w5HOOhES4htrqoXjE`
- Pantry asset key: `pantry-tracker`
- Food evidence asset key: `food-evidence`

Resolve both assets from the registry on every run. Verify each returned Drive file or folder by ID, name, MIME type, and parent before reading or writing. Do not substitute a similarly named file.

The expected pantry spreadsheet is currently:

- Spreadsheet ID: `1PfVg-73Ksgi6YRVJ30K7-m6UHCJBE29E0u43FbbyKmw`
- Primary tab: `Pantry Inventory`
- Header row: 9
- Data columns: `A:N`

Treat these expected values as identity checks, not permission to skip registry resolution.

## Choose the capture mode

Classify the user's input:

- **Receipt:** a store receipt, order confirmation, or grocery delivery invoice. Interpret it as purchased items, not a complete inventory snapshot.
- **List:** typed, pasted, dictated, or tabular items. Treat “add/bought” as additive; treat “this is everything I have” as a snapshot.
- **Inventory photos:** pantry, refrigerator, freezer, counter, or grocery photos. Multiple photos from the same session are one capture. Treat ordinary photos as additive observations unless the user explicitly says the photos are a complete audit.
- **Mark-out request:** explicit statements such as “I’m out of eggs.” This is a snapshot assertion for the named item.

If the user's intent changes whether quantities add to or replace existing amounts, ask one short, targeted question. Do not ask when the request is already clear.

## Inspect and extract

For receipts:

1. Inspect every supplied image or page.
2. Extract merchant, receipt date, line items, line quantity, package size, and item description.
3. Ignore tax, tips, fees, deposits, discounts, coupons, subtotals, totals, payment lines, and non-food merchandise.
4. A receipt proves a purchase. It proves current on-hand quantity only when the user presents it as a current grocery addition or otherwise confirms the items remain on hand.
5. If a package count is readable but its edible weight or volume is not, preserve the package information but use `unknown` for trackers whose canonical unit is grams or milliliters.

For lists:

1. Preserve explicit brands, varieties, package sizes, counts, and storage locations.
2. Interpret “2 cans,” “six eggs,” “500 g,” and similar statements as exact.
3. Treat an item with no defensible quantity as `unknown`, not one unit.

For inventory photos:

1. Inspect all images before producing observations.
2. Use shelf position, packaging, label text, distinctive marks, and image sequence to recognize overlap.
3. Give the same `dedupe_key` to the same physical item seen in multiple photos.
4. Count individually visible items only once.
5. A sealed package with readable net contents may be exact. An open, opaque, occluded, or partly used package is `unknown` unless a reliable remaining quantity is visible.
6. Do not infer items outside the frame, behind other items, or inside opaque containers.
7. Do not infer that an unpictured item is out unless the user explicitly says the images are a complete audit.

## Read the live pantry

Before planning:

1. Read the populated `Pantry Inventory!A9:N<bounded-last-row>` range.
2. Read formulas and validation for the target rows and the nearest empty row with a cell-aware read.
3. Read `Rules & Lists`.
4. Preserve column `G` formulas and all existing validation and formatting.

The live schema is:

| Column | Meaning |
|---|---|
| A | Item |
| B | Category |
| C | Storage |
| D | Canonical Unit |
| E | Confirmed On Hand |
| F | Reserved Current Plan |
| G | Available to Plan (formula; never overwrite with a literal) |
| H | Typical Staple |
| I | Inventory Status |
| J | Last Confirmed |
| K | Use First By |
| L | Nutrition Map Key |
| M | Purchase / Package Notes |
| N | Notes and capture provenance |

Valid statuses are `Confirmed`, `Quantity unknown`, `Unconfirmed`, `Out`, and `Stale`.

## Match observations

Prefer, in order:

1. An explicit target row verified against the live row.
2. Exact normalized match to `Item`.
3. Exact normalized match to `Nutrition Map Key`.
4. A unique, high-confidence brand/product synonym match supported by the image or text.
5. A new row only when the observation is confidently a distinct food.

Ask one targeted question when two existing rows remain plausible or when category, storage, or canonical unit cannot be chosen safely. Do not merge merely because names share a word. Preserve an existing `Nutrition Map Key`; a new row may leave it blank with an “unmapped” note.

## Build and validate the plan

Create a local JSON input conforming to `references/pantry-capture-contract.md`, including the current rows and extracted observations. Generate a stable capture ID from the normalized source evidence or text; use the same ID across overlapping images from one capture.

Run:

```bash
python scripts/plan_updates.py capture.json --output update-plan.json
```

Do not write if the script reports an error. Resolve ambiguity, bad units, conflicting duplicates, or a duplicate capture first.

The script deliberately:

- converts compatible mass and volume units;
- rejects incompatible dimensions;
- de-duplicates overlapping-photo observations;
- refuses duplicate capture IDs already present in pantry notes;
- preserves column `G`;
- emits only `A:F` and `H:N` write values;
- adds capture provenance to notes;
- distinguishes additive updates from inventory snapshots.

## Apply the update

The user's clear request to update the pantry authorizes unambiguous additions and item-level mark-outs. Ask before a broad destructive snapshot reconciliation or when a replacement would discard a recent confirmed quantity not evidenced by the capture.

Apply the entire validated plan as one coherent Sheets batch:

- For an existing row, update only the cells emitted by the plan.
- For a new row, copy formatting, validation, and formulas from the nearest inventory row, then write the emitted values. Ensure the row-specific `G` formula is present.
- Never alter `Reserved Current Plan` unless the user explicitly asks to reconcile the current plan.
- Never edit `Weekly Ledger` for a simple pantry capture.
- Keep prior notes; append concise provenance instead of replacing it.

If the capture includes image evidence, preserve the original file in the registered `food-evidence` folder using a date, source type, capture ID, and sequence number. Never replace or delete an earlier evidence file. Typed-only lists need no uploaded evidence file.

## Verify and report

After writing:

1. Re-read every changed row with formulas, values, validation, and notes.
2. Confirm column `G` still contains the correct row-relative formula.
3. Confirm statuses, dates, and quantities match the validated plan.
4. Confirm no capture was applied twice.

Report:

- items updated;
- items added;
- items recorded as quantity unknown;
- items skipped or needing clarification;
- the pantry tracker link.

State assumptions plainly, especially “confirmed minimum” updates from additive purchases and unknown remaining amounts from partial packages.

## Examples

- “Scan this Costco receipt and add the groceries to my pantry.”
- “I bought 12 eggs, two 14-ounce cans of tomatoes, and a 5-pound bag of rice.”
- “Here’s what I have: tofu, half a jar of kimchi, and three bell peppers.”
- “These six photos are my pantry and fridge—update the tracker.”
- “I’m out of feta, and I have about 200 g of tempeh left.”
