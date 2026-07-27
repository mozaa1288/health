# Open Food Facts Product Lookup

Use this workflow for packaged foods that are not already resolved by a planned
meal or the preferred-food map. It is a fast candidate finder, not a substitute
for a current package label.

## Indexed source

Resolve the exact `openfoodfacts-index` row from the live `Health Data Registry`.
Open the source by the row’s Drive ID and verify its identity and status before
fetching bytes. Verify the same asset key and Drive ID in the dedicated
workbook’s `Source Registry`.

- Search file: `openfoodfacts_search.sqlite.gz`
- Snapshot date: `2019-09-19`
- Search fields: product name, generic name, brand, and categories
- Exact keys: barcode and leading-zero-insensitive barcode

Fetch the search file as raw bytes with Google Drive and save it to a temporary
working path. Use the registry row or its referenced manifest for the snapshot
date; verify rather than assume the documented legacy date. Do not fetch the 101
lossless TSV shards unless a field absent from the compact index is required.

## Run the lookup

Prefer a barcode whenever the user provides one:

```bash
python scripts/openfoodfacts_lookup.py openfoodfacts_search.sqlite.gz \
  --barcode 638031612154 --grams 92 \
  --source-url "https://drive.google.com/file/d/RESOLVED_DRIVE_ID/view" \
  --snapshot-date YYYY-MM-DD --output product_match.json
```

Otherwise search the user's exact product wording:

```bash
python scripts/openfoodfacts_lookup.py openfoodfacts_search.sqlite.gz \
  --search "Field Roast Italian" --grams 92 \
  --source-url "https://drive.google.com/file/d/RESOLVED_DRIVE_ID/view" \
  --snapshot-date YYYY-MM-DD --output product_match.json
```

The script safely decompresses and caches the SQLite file, performs an exact
barcode lookup or ranked FTS search, scales nutrition to `--grams` (or the parsed
serving size), and emits one of these states:

- `resolved`: exact barcode, or a unique full-token text match with complete
  core nutrition;
- `ambiguous`: missing query tokens, similarly strong candidates, or incomplete
  nutrition;
- `not_found`: no usable candidate.

## Confidence and fallback

1. Treat a barcode match as product identity evidence, but keep nutrition
   confidence `Medium` because the database snapshot is dated.
2. For `ambiguous`, verify the product against a current barcode or current
   manufacturer/retailer package image. If the user can see the package, one
   barcode or label question is preferable to guessing.
3. If a current label differs from the snapshot, use the package label and set
   Source to `Package Label`; do not average the values.
4. If text search returns several variants, do not choose based only on rank.
5. If unresolved after one useful clarification, log blank nutrition and explain
   the gap.

When `compiler_item` is present in the lookup result, merge those fields into the
entry item and add the ordinary `item_id`, `item`, `quantity`, and `unit` fields.
Do not use `compiler_item` from an `ambiguous` result.

The lookup output uses the barcode as `nutrition_row_id`, Source
`Open Food Facts`, Nutrition Match `Open Food Facts`, and records the
registry-verified index URL plus snapshot date as provenance. The command-line
defaults preserve legacy behavior for standalone use, but this skill must pass
the live registry-derived URL and verified snapshot date.
