# Ranked food lookup

Use ranked lookup when the user's wording can identify more than one product or canonical food. Skip it for an exact current package label, exact barcode, exact validated planned-meal component, or one unambiguous high-confidence prior match with the same serving basis.

## Prepare sources

Create bounded local inputs from the live registered assets:

- `history.json`: active Food Log component rows likely to match. Include the 27 Food Log headers as object keys. Prefer the most recent confirmed rows.
- `preferred.json`: the live preferred-food map when available.
- `nutrition_corrected.csv`: the live canonical nutrition CSV.
- `openfoodfacts_search.sqlite.gz`: the registered compact Open Food Facts index when packaged-food lookup is relevant.

Do not use assistant summaries or inferred foods as history.

## Search

Supply separate useful terms rather than one long conversational sentence:

```bash
python scripts/food_lookup.py search \
  --term optimum \
  --term "gold standard" \
  --term casein \
  --history history.json \
  --preferred preferred.json \
  --canonical-csv nutrition_corrected.csv \
  --openfoodfacts-index openfoodfacts_search.sqlite.gz \
  --limit 8 \
  --output candidates.json
```

The script searches prior confirmed Food Log rows first, then preferred mappings, Open Food Facts, and canonical foods. Exact barcodes always outrank name similarity.

## Decide

Automatic reuse is allowed only when `decision.mode` is `auto` and:

- the candidate is an exact barcode or high-confidence prior confirmed match;
- all material terms match;
- brand, product line, flavor when relevant, and serving basis agree; and
- the candidate is not contradicted by the user's photo or wording.

Otherwise show the numbered candidates. Include product, serving, calories, protein, source, and the concise match reason. Ask the user to reply with a number or provide a barcode/photo. Do not expose raw ranking scores unless requested.

## Select

After the user chooses:

```bash
python scripts/food_lookup.py select \
  --candidates candidates.json \
  --choice 1 \
  --output selected_food.json
```

Use only `selected_food.json` to build the entry item. Preserve its candidate ID, source identity, serving basis, nutrition, and match note. Scale nutrition only after the consumed quantity is known.

The new active Food Log row becomes reusable history on future runs; do not create a second alias store unless a registered asset and compatible write policy exist.

## No safe match

If none fits, ask for a barcode, package label, restaurant configuration, or clearer food name. If the food is clear but nutrition remains unavailable, log an unresolved component with blank nutrients rather than choosing a generic result silently.
