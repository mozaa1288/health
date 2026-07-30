# Ranked food lookup

Use ranked lookup when wording can identify more than one product or canonical food. Skip it for an exact current label, exact barcode, exact validated planned component, or one unambiguous high-confidence prior match with the same serving basis.

## Prepare sources

- One or more recent `food-log-YYYY-MM-DD.jsonl` files from Google Drive folder `13E1t9q2JQrCliQyO8xecHNcDdUyhMjaI` for confirmed history.
- The current preferred-food map.
- The canonical nutrition CSV.
- The compact Open Food Facts index when packaged-food lookup is relevant.

The lookup script reads daily JSONL directly and uses only the last revision for each `entry_id`.

## Search

Supply separate useful terms:

```bash
python scripts/food_lookup.py search \
  --term optimum \
  --term "gold standard" \
  --term casein \
  --history food-log-2026-07-29.jsonl \
  --preferred preferred.json \
  --canonical-csv nutrition_corrected.csv \
  --openfoodfacts-index openfoodfacts_search.sqlite.gz \
  --limit 8 \
  --output candidates.json
```

Exact barcodes outrank name similarity. Automatic reuse is allowed only for an exact barcode or a single high-confidence prior match whose material terms, brand, product, flavor, and serving basis agree. Otherwise show the numbered candidates and ask for a choice.

After selection, run:

```bash
python scripts/food_lookup.py select \
  --candidates candidates.json \
  --choice 1 \
  --output selected_food.json
```

Preserve the selected source identity, serving basis, nutrition, and match note. Scale nutrition only after the consumed quantity and edible-gram conversion are known.

If no safe match exists, ask for a barcode, label, restaurant configuration, or clearer name. Clear consumption with unresolved nutrition may still be logged with null nutrients.
