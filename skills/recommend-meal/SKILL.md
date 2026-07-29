---
name: recommend-meal
description: Recommend the next practical meal or snack using today's Food Log, current validated meal plan, and available pantry items.
---

# Recommend Meal

Give one practical recommendation for the user's next meal or snack. This workflow is read-only: do not log food or change pantry inventory.

## Workflow

1. Resolve the current date and time in `America/Los_Angeles`.
2. Read today's active entries from the registered Food Consumption Log.
3. Read the validated weekly plan covering today, when one exists.
4. Read enough of the registered pantry tracker to confirm likely ingredient availability.
5. Compare today's known intake with the planned meals and daily totals.
6. Prefer the next unconsumed planned meal when it still makes sense. Otherwise make a simple adjustment or suggest an easy pantry-based alternative.
7. Use the weekly plan or canonical nutrition source for approximate macros. Blank food-log nutrition is unknown, not zero.
8. Treat fiber as a floor and sodium as an upper guardrail. Do not recommend food merely to increase sodium.

Follow the user's standing meal-plan preferences: one person, vegetarian base, no mushrooms or cucumber, and practical ingredients they commonly eat.

## Response

Return one recommendation and, when useful, one alternative. Include:

- meal or snack name;
- explicit one-person quantities;
- approximate calories, protein, carbohydrates, and fat;
- one short reason it fits the day;
- brief preparation guidance;
- whether it is planned, pantry-based, or requires a purchase.

Do not optimize tiny macro differences, create a scoring system, or describe a one-day gap as a medical deficiency.

A recommendation is not evidence of consumption. Use `../log-food/SKILL.md` only after the user says what they actually ate.
