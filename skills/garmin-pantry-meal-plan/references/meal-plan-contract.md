# Meal Plan Contract

## Scope and preferences

- Plan for one person and one week.
- Keep the base plan vegetarian.
- Allow salmon only as an optional pescatarian substitution. Exclude it from the base grocery list unless explicitly requested.
- Skip weekday breakfasts.
- Avoid mushrooms and cucumber.
- Favor practical meals using eggs, cheese, black beans, rice, yogurt, tempeh, tofu, Field Roast, fermented vegetables, and similar foods.
- Use Fage Total 5% plain Greek yogurt whenever plain Greek yogurt is called for.
- Prefer and rotate red bell pepper, onion, tomato, pepperoncini, water-packed olives, quinoa, forbidden rice, hulled barley, Fage Total 5%, Mama Lil's peppers, eggs, drunken goat cheese, goat cheese, feta, tempeh, Italian Field Roast sausage, kimchi, tofu, pico de gallo, Rao's arrabbiata sauce, pasta, hot sauce, and homemade fermented vegetables.
- Do not force every preferred food into every week.
- Optimize for gradual fat loss without compromising running recovery.

## Garmin adaptation

Set calorie targets and carbohydrate timing from 14-day averages, total training volume, recovery trends, and recurring day-of-week patterns.

- Use higher calories and carbohydrates on likely long or hard days.
- Use moderate intake on ordinary training days.
- Use a modest deficit on light or rest days.
- Keep protein relatively stable.
- Do not create deficits that are likely to impair recovery.
- Qualify decisions when relevant Garmin fields or dates are missing.

## Nutrition rules

- Use the canonical nutrition CSV as the sole numerical nutrition source.
- Use the preferred-food map's row ID, proxy disclosure, dry-weight convention, and multi-component instructions whenever a mapped item appears.
- Track dry grains and pasta as dry grams before cooking.
- Use explicit edible-gram conversions for count items.
- Use drained edible weight for brined or jarred foods unless the map specifies otherwise.
- Represent Mama Lil's peppers as separate pepper-solids and retained-oil components.
- Disclose every proxy.
- Do not enter manual meal macros in `plan.json`.

## Pantry eligibility

Determine usable opening inventory in this order:

1. Use `Available to Plan` from `Pantry Inventory` only when `Inventory Status` is `Confirmed`, `Confirmed On Hand` is numeric, and `Last Confirmed` is no more than 14 days old.
2. Otherwise, use the newest numeric `Actual Ending` from `Weekly Ledger` whose status is `Confirmed` or `Reconciled`.
3. Otherwise, use a numeric `Projected Ending` only from the immediately preceding weekly plan. Mark it `projected` and disclose that it assumes the prior plan was followed.
4. Treat all other inventory as zero for subtraction.

Never subtract inventory marked `Unconfirmed`, `Quantity unknown`, `Out`, or `Stale`. `Typical Staple` is a preference, not evidence of inventory.

Use canonical units:

- grams for dry foods and most solids;
- count for eggs;
- milliliters only for compatible liquids.

## Compiler guarantees

Publish only when the bundled compiler returns `status: validated` and every flag is true. It must guarantee:

- quantified ingredients for every meal;
- a valid nutrition row for every ingredient;
- nutrition calculated from explicit edible grams;
- complete recipe-to-grocery reconciliation;
- pantry subtraction before package rounding;
- no grocery item without recipe demand;
- nonnegative projected ending inventory;
- disclosed confirmed or projected inventory sources.

## Pantry ledger writeback

After successful compilation, write one row per `inventory_allocation` item with:

- Week Starting
- Ingredient
- Unit
- Opening Confirmed
- Planned Use
- Planned Purchase
- Projected Ending
- blank Actual Ending
- Record Status = `Projected`
- Last Updated = current local date
- note stating whether opening inventory was confirmed, projected, or zero

Replace projected rows for the same week rather than duplicating them. Do not overwrite `Confirmed On Hand` or `Last Confirmed` from a projected plan.

When the user later confirms leftovers, write `Actual Ending`, mark the ledger row `Reconciled`, and update the matching pantry row's confirmed quantity and date.
