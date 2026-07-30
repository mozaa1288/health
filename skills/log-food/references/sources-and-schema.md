# Food Log Storage and Schema

## Storage

```text
Health/03 Operational Trackers/Food Logs/food-log-YYYY-MM-DD.jsonl
```

Folder ID: `13E1t9q2JQrCliQyO8xecHNcDdUyhMjaI`.

Use one file per `America/Los_Angeles` date and one complete meal revision per line. Fetch the exact file, run the bundled scripts locally, then upload a new file or replace the existing bytes in place.

## Record

Schema version: `food_log.meal.v1`.

Each record contains:

- stable `entry_id`, `revision`, and `status`;
- `logged_at`, `local_date`, and `last_updated`;
- meal name, description, and the user's original wording;
- item quantities, normalized units, nutrition, and source metadata;
- meal totals and the subtotal of known nutrition.

## History

- New meal: append revision 1.
- Identical retry: no-op.
- Correction: append the full corrected record with the same `entry_id` and next revision.
- Removal: append a `Deleted` revision.
- Current view: the final revision for each `entry_id` wins; omit final deleted records.

## Units

- Normalize mass to grams, US food volume to milliliters, and discrete items to count.
- Scale nutrition from edible grams.
- Volume or count needs a sourced conversion or explicit edible grams.
- Reject conflicting conversions.
- Keep estimates and conversion sources in the item note.
