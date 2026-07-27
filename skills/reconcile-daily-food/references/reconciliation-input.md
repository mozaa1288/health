# Reconciliation Input Contract

Use this contract to prepare deterministic inputs for `scripts/reconcile_food_log.py`.

## Candidate file

The candidate file is a JSON object:

```json
{
  "target_date": "2026-07-26",
  "candidates": [
    {
      "candidate_id": "conversation-2026-07-26T12:15:00-0700-lunch",
      "source_message_ref": "conversation timestamp or stable reference",
      "source_timestamp": "2026-07-26T12:15:00-07:00",
      "explicit_consumption": true,
      "consumed_local_date": "2026-07-26",
      "meal": "Lunch",
      "description": "Baked tofu, brown rice, and red bell pepper",
      "original_text": "for lunch i had 200 g baked tofu, 1 cup cooked brown rice, and 1 red bell pepper",
      "requires_configuration": false,
      "configuration_complete": true,
      "items": [
        {"item": "baked tofu", "quantity": 200, "unit": "g"},
        {"item": "cooked brown rice", "quantity": 1, "unit": "cup"},
        {"item": "red bell pepper", "quantity": 1, "unit": "count"}
      ]
    }
  ]
}
```

Requirements:

- `target_date` and `consumed_local_date` use `YYYY-MM-DD`.
- `candidate_id` is stable across retries. Prefer an available conversation/message reference;
  otherwise derive it from the source timestamp, target date, meal, and normalized original text.
- Provide at least one of `source_message_ref` or `source_timestamp`. When present,
  `source_timestamp` is an ISO-8601 timestamp with an offset.
- `explicit_consumption` is true only for direct user-authored consumption evidence.
- `meal` is `Breakfast`, `Lunch`, `Dinner`, `Snack`, or `Other`.
- `description` is a concise event description. `original_text` preserves the user's words.
- Each item has a nonblank identity, positive numeric quantity, and nonblank unit before it can be
  automatically logged.
- Set `requires_configuration` for configurable restaurant or assembled menu items. Set
  `configuration_complete` only when the build is sufficiently known for `log-food`.
- Do not include nutrition values. `log-food` resolves nutrition after reconciliation.

Represent insufficient detail explicitly rather than inventing it:

```json
{"item": "eggs", "quantity": null, "unit": null}
```

The script will classify that candidate as `needs_clarification`.

## Food-log rows file

The rows file is either a JSON array of objects or an object with a `rows` array. Each object uses
the exact `Food Log` headers as keys. Include the complete bounded range after converting every
nonblank row to an object.

```json
{
  "rows": [
    {
      "Entry ID": "2026-07-26T12:15:00-07:00-lunch",
      "Item ID": "baked-tofu",
      "Local Date": "2026-07-26",
      "Meal": "Lunch",
      "Description": "Baked tofu and rice",
      "Item": "baked tofu",
      "Quantity": 200,
      "Unit": "g",
      "Original Text": "for lunch i had 200 g baked tofu and rice",
      "Status": "Active"
    }
  ]
}
```

Include all 27 fields when available. The script requires these fields:

- `Entry ID`
- `Item ID`
- `Local Date`
- `Meal`
- `Description`
- `Item`
- `Quantity`
- `Unit`
- `Original Text`
- `Status`

Rows with `Status: Deleted` remain historical evidence. They do not count as active logged food,
but an exact match is classified as `ambiguous_match` so a previously removed entry is not silently
recreated.

## Output

The output contains:

```json
{
  "schema": "food-log-reconciliation-plan/v1",
  "target_date": "2026-07-26",
  "summary": {
    "already_logged": 1,
    "missing": 0,
    "needs_clarification": 0,
    "ambiguous_match": 0,
    "ignored": 0
  },
  "results": [
    {
      "candidate_id": "candidate-id",
      "classification": "already_logged",
      "reason": "original text matches an active entry",
      "possible_entry_ids": ["existing-entry-id"],
      "candidate": {}
    }
  ]
}
```

Only `missing` candidates are safe to pass automatically to `log-food`. Treat
`needs_clarification` and `ambiguous_match` as write blockers.
