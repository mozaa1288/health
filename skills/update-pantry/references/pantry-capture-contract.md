# Pantry Capture Contract

## Purpose

This contract separates probabilistic extraction from deterministic inventory mutation. The agent interprets the receipt, list, or images; `scripts/plan_updates.py` validates the proposed observations and computes a safe Sheet update plan.

## Capture document

The planner input is JSON:

```json
{
  "capture": {
    "capture_id": "cap-20260726-a1b2c3d4",
    "source_type": "receipt",
    "mode": "additive",
    "captured_at": "2026-07-26T16:30:00-07:00",
    "merchant": "Example Market",
    "evidence_ids": ["drive-file-id"],
    "observations": []
  },
  "inventory": {
    "as_of": "2026-07-26",
    "rows": []
  }
}
```

Required capture fields:

- `capture_id`: stable identifier, 8–120 characters, reused for every image in one capture.
- `source_type`: `receipt`, `list`, `photo`, or `statement`.
- `mode`: `additive` or `snapshot`.
- `captured_at`: ISO-8601 timestamp.
- `observations`: one object per distinct physical item or combined receipt line.

`evidence_ids` contains immutable Drive IDs for supplied images. Omit or use an empty list for typed-only captures.

## Inventory rows

Each current row uses:

```json
{
  "row_number": 10,
  "item": "Eggs",
  "category": "Dairy & eggs",
  "storage": "Fridge",
  "canonical_unit": "count",
  "confirmed_on_hand": 6,
  "reserved_current_plan": 0,
  "typical_staple": "Yes",
  "status": "Confirmed",
  "last_confirmed": "2026-07-24",
  "use_first_by": null,
  "nutrition_map_key": "eggs",
  "package_notes": "",
  "notes": ""
}
```

Read values from columns `A:F` and `H:N`. Column `G` is derived and must not be supplied as writable data.

## Observation fields

```json
{
  "observation_id": "line-01",
  "dedupe_key": "shelf2-red-bag-rice",
  "observed_name": "Forbidden rice",
  "quantity_state": "exact",
  "quantity": 2,
  "unit": "lb",
  "target_row": 16,
  "allow_new": false,
  "category": "Dry grains",
  "storage": "Pantry",
  "canonical_unit": "g",
  "typical_staple": "Yes",
  "nutrition_map_key": "forbidden_rice_dry",
  "package_notes": "One 2 lb bag",
  "use_first_by": null,
  "confidence": 0.98,
  "evidence_refs": ["drive-file-id#image-1"],
  "match_reason": "Exact product label and existing item"
}
```

Required fields:

- `observation_id`: unique inside the capture.
- `observed_name`: non-empty item name.
- `quantity_state`: `exact`, `unknown`, or `out`.
- `confidence`: number from 0 through 1.

For `exact`, `quantity` must be non-negative and `unit` must be present. For `unknown`, quantity is omitted. For `out`, mode must be `snapshot`.

Matching fields:

- `target_row`: preferred when the agent has matched an existing live row.
- `allow_new`: true only when a no-match observation is confidently a distinct item.
- `match_candidates`: optional list of plausible existing row numbers. More than one candidate is an error until clarified.
- `match_reason`: concise evidence for the match.

New rows require `category`, `storage`, and `canonical_unit`. `nutrition_map_key` may be blank. Use `typical_staple: "No"` unless the user establishes a recurring staple.

## Units

Canonical units are:

- mass: `g`
- volume: `ml`
- discrete items: `count`

Accepted convertible input units:

- mass: `mg`, `g`, `kg`, `oz`, `lb`
- volume: `ml`, `l`, `fl oz`, `cup`, `tbsp`, `tsp`
- discrete: `count`, `each`, `ea`

Do not convert mass to volume or count to mass without item-specific measured evidence. Package count is not edible grams. Round converted grams and milliliters to three decimal places; preserve integer counts when integral.

## Merge semantics

### Additive exact

- If an existing row is `Confirmed` and `last_confirmed` is no more than 14 days before `inventory.as_of`, add the observed quantity to the existing quantity.
- Otherwise set the confirmed quantity to the newly observed amount and annotate it as a confirmed minimum; older or unknown stock is not silently guessed.
- Set status to `Confirmed` and `last_confirmed` to `inventory.as_of`.

### Snapshot exact

Replace the item's confirmed quantity with the observed amount. Set status to `Confirmed` and refresh `last_confirmed`.

### Unknown

- New rows become `Quantity unknown` with zero confirmed quantity.
- Additive observations do not downgrade a recent confirmed row. Preserve its quantity/status and append the new evidence note.
- A declared snapshot may set the row to `Quantity unknown` and zero confirmed quantity.

### Out

Only a snapshot assertion may mark an item `Out`. Set confirmed quantity to zero and refresh the observation date.

## Overlap and duplicate protection

Observations with the same non-empty `dedupe_key` represent the same physical item seen more than once. They must agree on item, quantity state, quantity, and unit; the planner combines their evidence and applies them once. Conflicts are errors.

If `[capture:<capture_id>]` already appears in any current pantry note or package note, the entire capture is a duplicate and must not be applied again.

## Output plan

The script emits:

```json
{
  "capture_id": "cap-20260726-a1b2c3d4",
  "status": "ready",
  "operations": [
    {
      "action": "update",
      "row_number": 16,
      "item": "Forbidden rice",
      "write_cells": {
        "E": 907.185,
        "I": "Confirmed",
        "J": "2026-07-26",
        "M": "One 2 lb bag",
        "N": "Existing note. [capture:cap-20260726-a1b2c3d4] receipt; exact; Exact product label and existing item"
      }
    }
  ],
  "summary": {
    "updated": 1,
    "added": 0,
    "quantity_unknown": 0
  },
  "warnings": []
}
```

Allowed writable columns are `A:F` and `H:N`. The planner never emits `G`.

## Evidence and provenance

Use concise provenance:

`[capture:<capture_id>] <source_type>; <quantity_state>; <match_reason>`

Preserve existing notes. A receipt or photo file is immutable raw evidence in the registered `food-evidence` folder. The Sheet is the operational state, not the image archive.

