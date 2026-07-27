# Registry, Sources, and Food Log Schema

## Authoritative registry

The authoritative registry is:

- Google Sheet: `Health Data Registry`
- Drive ID: `1AHvwyDzlhznRFvAry5Tqj37Ol9w5HOOhES4htrqoXjE`
- Canonical path: `Health/00 System & Governance/Health Data Registry`
- Tab: `Assets`
- Registry schema version: `health_drive_layout.v1`

Read `A:K` and require these exact headers in order:

`Asset Key`, `Name`, `Kind`, `Drive ID`, `Canonical Path`, `Schema Version`, `Primary Writer`, `Write Policy`, `Status`, `Last Verified`, `Notes`.

For every operation:

1. Read the live `Assets` rows.
2. Resolve each needed asset by its exact `Asset Key`.
3. Require one unique active row with a nonblank `Drive ID`.
4. Open the asset by that returned Drive ID, then verify its name/kind and relevant schema or structure. Do not substitute a title search result or stale hardcoded ID.
5. Honor `Write Policy` and `Primary Writer`. Stop rather than writing when the registry row conflicts with this skill’s intended access.

Required asset keys are:

| Asset key | Purpose |
|---|---|
| `food-log` | Dedicated `Food Consumption Log` Google Sheet |
| `pantry-tracker` | Pantry and fridge planning source; never a Food Log destination |
| `weekly-plans` | Validated compiled weekly plans |
| `preferred-food-map` | Preferred-food nutrition mappings |
| `canonical-nutrition` | Canonical nutrition CSV |
| `openfoodfacts-index` | Compact packaged-food lookup index and its provenance |
| `food-evidence` | Receipts, package images, and other food evidence when applicable |

The `food-log` row must resolve to Drive ID `12Exzl-EZWxkiN0cd9XafE9R7a_MBoNiZuio46deANnQ`. Treat any mismatch, duplicate row, inactive status, missing tab, or incompatible write policy as a blocker.

Fetch live sources for every add or correction. For a planned meal, use the latest validated `YYYY-MM-DD_compiled_plan.json` from the `weekly-plans` asset whose week covers the consumed date. Do not reconstruct a planned meal from pantry rows.

## Dedicated workbook

Actual consumption belongs only in the `food-log` asset. Never append, replace, migrate, or mirror `Food Log` rows into the `pantry-tracker` asset.

The dedicated `Food Consumption Log` workbook contains:

- `Food Log`: authoritative item-level consumption rows.
- `Daily Summary`: derived daily totals. Do not append item rows here.
- `Saved Orders`: reusable confirmed restaurant builds.
- `Source Registry`: workbook-local source lineage. Verify its existing entries against the live registry and source Drive IDs; do not treat it as a replacement for the `Health Data Registry`.

Read workbook metadata before every write. Preserve all four tabs and their existing structures. If `Food Log` is absent, create only that tab with the exact 27-column schema below. If another required tab is absent, stop and report the schema gap instead of inventing it.

## `Food Log` tab

Create the tab only in the dedicated `food-log` workbook when absent. Freeze row 1. Write these 27 headers in `A1:AA1`, in this exact order. If an existing `Food Log` has the earlier 25-column schema, append `Source URL` and `Source Accessed` as columns Z and AA without changing prior data.

| Column | Header | Meaning |
|---|---|---|
| A | Entry ID | Stable meal/event identifier |
| B | Item ID | Stable identifier unique within the entry |
| C | Logged At | ISO-8601 local timestamp with offset |
| D | Local Date | `YYYY-MM-DD` in America/Los_Angeles |
| E | Meal | Breakfast, Lunch, Dinner, Snack, or Other |
| F | Description | User-facing meal description |
| G | Item | Food or drink component |
| H | Quantity | Original numeric quantity |
| I | Unit | Original unit |
| J | Edible Grams | Grams used for nutrition scaling |
| K | Calories | Item calories |
| L | Protein g | Item protein |
| M | Carbs g | Item carbohydrate |
| N | Fat g | Item fat |
| O | Fiber g | Item fiber |
| P | Sodium mg | Item sodium |
| Q | Nutrition Row ID | Canonical CSV row or Open Food Facts barcode; blank for label/unresolved |
| R | Nutrition Match | Exact, Proxy, Label, Official, Open Food Facts, or Unresolved |
| S | Source | Planned Meal, Canonical CSV, Package Label, Official Restaurant, Open Food Facts, or Unresolved |
| T | Planned Meal ID | Companion-plan meal ID when applicable |
| U | Confidence | High, Medium, or Low |
| V | Original Text | User’s supplied wording |
| W | Notes | Proxy, conversion, correction, or gap disclosure |
| X | Last Updated | Current local ISO-8601 timestamp |
| Y | Status | Active or Deleted |
| Z | Source URL | Official restaurant URL or indexed-source Drive URL when applicable |
| AA | Source Accessed | `YYYY-MM-DD` source access or snapshot date |

Use one row per food component. Multiple rows for one meal share `Entry ID`, timestamp, date, meal, description, and planned meal ID.

## Entry JSON

```json
{
  "entry_id": "2026-07-26T12:30:00-07:00-lunch",
  "logged_at": "2026-07-26T12:30:00-07:00",
  "local_date": "2026-07-26",
  "meal": "Lunch",
  "description": "Two eggs and toast",
  "original_text": "log two eggs and a slice of toast for lunch",
  "planned_meal_id": null,
  "items": [
    {
      "item_id": "eggs",
      "item": "Eggs",
      "quantity": 2,
      "unit": "count",
      "nutrition_grams_total": 100,
      "nutrition_row_id": 123,
      "nutrition_match_type": "exact",
      "nutrition_match_note": "50 edible g per egg",
      "source": "Canonical CSV",
      "confidence": "High"
    }
  ]
}
```

Each item must use exactly one nutrition mode:

- CSV-backed: `nutrition_row_id` or unique `nutrition_name`, plus edible grams.
- Package label: `label_nutrition` containing calories, protein_g, carbs_g, fat_g, and optionally fiber_g and sodium_mg for the consumed quantity.
- Official restaurant: `official_nutrition` containing calories, protein_g, carbs_g, fat_g, and optionally fiber_g and sodium_mg for the configured component or complete order; also require `source_url` and `source_accessed`.
- Open Food Facts: `nutrition_match_type: "open_food_facts"`, numeric barcode in `nutrition_row_id`, and `open_food_facts_nutrition` containing the consumed-quantity nutrients; also require the indexed Drive `source_url` and snapshot date in `source_accessed`.
- Unresolved: `nutrition_match_type: "unresolved"` and a non-empty `nutrition_match_note`.

`entry_id` and `item_id` must be stable across retries. Use a short deterministic suffix when two entries would otherwise collide.

## Write behavior

- Before any write, re-check that the open spreadsheet Drive ID equals the verified `food-log` Drive ID.
- New entry: append rows after the last active or deleted row.
- Retry of identical entry and items: no-op.
- Correction: replace every row sharing the exact `Entry ID` in one coherent update.
- Removal: set `Status` to `Deleted`; do not erase history unless the user explicitly asks for permanent deletion.
- Never treat a blank nutrient cell as zero.
- Never write `Food Log` rows to `pantry-tracker`, `Pantry Inventory`, or `Weekly Ledger`.
- Never update pantry quantities from inferred consumption.

## Companion tabs

### `Saved Orders`

Read the bounded populated region and preserve its existing headers. Match reusable builds by normalized restaurant and menu-item identity, then require a single active exact match. Confirm the concise build with the user before reuse. After a user supplies or corrects a complete build, upsert it using the tab’s existing key and status columns so future logs can reuse it; do not add columns or guess missing required fields. A saved build supplies ingredients, not permanent nutrition: refresh current official nutrition when logging each consumption event.

### `Daily Summary`

Treat this tab as derived. Prefer formula or existing summary behavior and do not append item rows. When practical, verify the affected local date after a `Food Log` write. If its totals disagree with active `Food Log` rows, report the mismatch and use the item rows as authoritative.

### `Source Registry`

Use this tab as workbook-local lineage. For every nutrition or evidence asset used, verify that its asset key and Drive ID agree with the live `Assets` row. Do not silently create a second identity for the same source. The live `Health Data Registry` remains authoritative when the two disagree.
