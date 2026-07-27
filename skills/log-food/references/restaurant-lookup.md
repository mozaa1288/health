# Restaurant Nutrition Lookup

Use this workflow whenever the user names a restaurant, chain, menu item, takeout order, or configurable prepared meal.

## Resolve the order

1. Identify the restaurant and menu item from the user’s exact words.
2. Resolve and verify the dedicated `food-log` asset, then search `Saved Orders` for an active exact restaurant-and-item match:
   - If one saved build clearly matches, ask one short question: `Same build as [concise saved build]?`
   - Otherwise ask the user to paste the order or list its components. Keep it to one question.
3. Accept an order description, receipt, screenshot, or explicitly requested order-history/email lookup. Do not access email or another account unless the user asks.
4. For Chipotle burritos and bowls, request or extract: format/tortilla, rice, beans, protein or sofritas, fajita vegetables, salsa, cheese, sour cream, guacamole, queso, lettuce, and extras. Do not assume omitted components.
5. If the user requests a quick log without details, write one unresolved restaurant item with blank nutrition. Do not insert a “typical” burrito.

## Retrieve nutrition

1. Browse for the restaurant’s current official nutrition calculator, nutrition page, or first-party nutrition PDF. Current first-party data is mandatory because menus and formulations change.
2. Prefer sources in this order:
   - official configured-order calculator total;
   - official per-component nutrition;
   - official fixed-menu-item nutrition;
   - nutrition values printed on the user’s receipt or supplied restaurant material.
3. Do not use search snippets, blogs, delivery apps, crowd-sourced databases, or generic food rows as exact restaurant nutrition. If first-party data is unavailable, leave nutrition unresolved or use a clearly identified user-supplied label.
4. Match the restaurant’s serving definition exactly. Do not infer grams, portion multipliers, omitted ingredients, regional availability, or preparation choices.
5. Record the direct official source URL and local access date on every restaurant row. For PDFs, also record the relevant page or table in the note.

## Compile the entry

- Use one item per official component when component values are available.
- Use one configured-meal item when only an official calculator total is available.
- Set `nutrition_match_type` to `official`.
- Set `source` to `Official Restaurant`.
- Put the consumed-value nutrients in `official_nutrition`.
- Set confidence:
  - `High` when the exact user build maps directly to current official data;
  - `Medium` when the restaurant reports a range or the user confirms a close prior build;
  - `Low` only for an explicitly accepted approximation, with the uncertainty described.
- Never combine an official restaurant total with its component rows in the same entry; that would double-count nutrition.
- Write the consumption rows only to the dedicated `Food Log` tab. After a complete build is confirmed, upsert the reusable build in `Saved Orders` using its existing schema. Refresh official nutrition on each future consumption; do not treat saved nutrition as permanently current.

## Example interaction

User: `I ate a Chipotle burrito.`

Ask: `What was in it? Paste the order, or list the rice, beans, protein/sofritas, fajita vegetables, salsa, cheese, sour cream, guac, queso, lettuce, and extras.`

After the answer, calculate the configured order from current official Chipotle nutrition and write the sourced rows.
