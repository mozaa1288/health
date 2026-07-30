---
name: update-pantry
description: Update the registered Pantry & Fridge Inventory Tracker from receipts, typed lists, photos, or explicit on-hand corrections. Use for grocery additions, pantry audits, mark-outs, and remaining-quantity updates.
---

# Update Pantry

Update the live pantry tracker conservatively from what the user directly provides. Do not infer pantry changes from daily JSONL food logs.

## Workflow

1. Resolve `pantry-tracker` through the live Health Data Registry and verify the spreadsheet. Resolve `food-evidence` only when images or receipts need to be preserved.
2. Read the populated `Pantry Inventory` range, `Rules & Lists`, and the formulas or validation near any rows that may change.
3. Interpret the input:
   - receipt or “I bought”: add the stated quantities;
   - ordinary pantry photos: add only clearly visible items and quantities;
   - explicit inventory snapshot: replace quantities only for items covered by the snapshot;
   - “I’m out of X”: set that item to Out;
   - explicit remaining quantity: replace that item's confirmed amount.
4. Preserve brands, varieties, package sizes, storage locations, and units when provided. Unknown quantity remains unknown, not one package.
5. Match an existing row by exact item name, nutrition-map key, or one clear product synonym. Ask one concise question when two rows are plausible or the unit cannot be chosen safely.
6. For existing rows, update only the relevant values and append concise source notes. For new rows, copy the neighboring formatting, validation, and row-relative formula in column G before entering values.
7. Never overwrite column G with a literal, alter `Reserved Current Plan` without an explicit request, or edit `Weekly Ledger` for a normal pantry capture.
8. When several photos overlap, inspect them together and count the same physical item once. Open, hidden, or partly used packages have unknown remaining quantity unless it is clearly visible.
9. Apply related changes in one Sheets batch, then read every changed row back and verify quantities, statuses, dates, formulas, validation, and notes.
10. Preserve supplied receipt or photo evidence in the registered `food-evidence` folder using a unique dated filename. Typed lists do not require an evidence file.

## Safety rules

- A receipt proves a purchase, not necessarily a complete current inventory.
- An unpictured item is not Out unless the user says the images are a complete audit.
- Ask before a broad destructive reconciliation that would discard recent confirmed quantities.
- Preserve existing nutrition-map keys and prior notes.

## Response

Report items updated, items added, unknown quantities, skipped or ambiguous items, and the pantry tracker link.
