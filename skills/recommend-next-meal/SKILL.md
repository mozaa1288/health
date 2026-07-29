---
name: recommend-next-meal
description: Recommend what the user should eat next using today's food log, the current weekly meal plan, and pantry availability. Use for questions such as “what should I eat next?”, “what should I have for dinner?”, or “what snack fits today?”
---

# Recommend Next Meal

Give a practical recommendation for the user's next meal or snack. This is a read-only workflow: do not log food and do not modify pantry inventory.

## Workflow

1. Resolve the current date and time in `America/Los_Angeles`.
2. Read today's active entries from the registered Food Consumption Log.
3. Read the validated weekly meal plan covering today, when one exists.
4. Read enough of the registered pantry tracker to determine whether suggested ingredients are reasonably available.
5. Compare what has been logged with today's planned meals and totals.
6. Recommend the next unconsumed planned meal when it still makes sense. Otherwise suggest a simple adjustment or pantry-based alternative.

Prefer foods and constraints already defined by the weekly meal-plan workflow: one person, vegetarian base, no mushrooms or cucumber, and practical ingredients the user commonly eats.

## Response

Return one recommended option and, when useful, one alternative. Include:

- the meal or snack name;
- explicit one-person quantities;
- approximate calories, protein, carbohydrates, and fat using the validated plan or canonical nutrition sources;
- a short explanation of why it fits the day;
- a brief preparation note;
- whether it is planned, pantry-based, or requires purchasing anything.

Keep the recommendation practical. Do not optimize tiny macro differences or create elaborate scoring systems.

Blank or unresolved nutrition in the food log is unknown, not zero. Mention the uncertainty briefly rather than pretending the day's totals are exact.

A recommendation is not evidence that the food was eaten. Only use `../log-food/SKILL.md` after the user explicitly states what they consumed.
