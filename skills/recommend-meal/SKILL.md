---
name: recommend-meal
description: Recommend the next practical meal or snack using today's Library JSONL food log, current validated meal plan, and available pantry items.
---

# Recommend Meal

Give one practical recommendation for the user's next meal or snack. This workflow is read-only: do not log food or change pantry inventory.

## Where the data lives

Today's consumption comes from ChatGPT Library:

```text
food-log-YYYY-MM-DD.jsonl
```

Resolve the pantry tracker and weekly plans through their existing registry workflow.

## Workflow

1. Resolve the current date and time in `America/Los_Angeles`.
2. Prepare today's Library JSONL file and run `../log-food/scripts/food_log_jsonl.py read`. A missing file means no meals are logged yet.
3. Read the validated weekly plan covering today (the `*_compiled_plan.json` for the relevant week has per-meal macros including sodium).
4. Read enough of the registered pantry tracker to confirm likely ingredient availability.
5. Compare today's known intake with the planned meals and daily totals.
6. Prefer the next unconsumed planned meal when it still makes sense. Otherwise make a simple adjustment or suggest an easy pantry-based alternative.
7. Use the weekly plan or canonical nutrition source for approximate macros. Null food-log nutrition is unknown, not zero.
8. Treat fiber as a floor and sodium as an upper guardrail. Do not recommend food merely to increase sodium.

Follow the user's standing meal-plan preferences: one person, vegetarian base, no mushrooms or cucumber, and practical ingredients they commonly eat.

## Response format

Return plain markdown only. Do not use visualization tools, HTML, or rendered widgets — the output must paste cleanly into any chat client.

Use this exact structure.

### Heading

`## Meal recommendation — <Day Mon D, h:mm AM/PM>`

### Table 1 — Today so far

| Metric | Logged | Plan target | Status |
|---|---:|---:|---|
| Calories | | | |
| Protein | | | |
| Carbs | | | |
| Fat | | | |
| Fiber | | — | |
| Sodium | | — | |

Rules:
- Logged values come from the current JSONL meal revisions; plan targets come from the validated weekly plan.
- Use `—` when no plan target exists for that metric.
- Status is a short phrase: a percentage, `Met`, `Running high`, or `Unknown`.
- Never print `0` for an unknown value. Print `Unknown`.

### Table 2 — Options

Two columns: the recommendation first (prefixed `✅`), one alternative second (prefixed `⚠️`). Omit the second column when only one option is sensible.

| | ✅ <option name> | ⚠️ <option name> |
|---|---|---|
| **Type** | | |
| **Portion** | | |
| **Calories** | | |
| **Protein** | | |
| **Carbs** | | |
| **Fat** | | |
| **Day total after** | | |
| **Sodium impact** | | |
| **Prep** | | |
| **Availability** | | |

Rules:
- `Type` is one of `Planned`, `Pantry-based`, or `Requires purchase`.
- `Portion` gives explicit one-person quantities. Use `<br>` to break long ingredient lists.
- `Day total after` is today's logged calories plus the option's calories.
- `Availability` states confirmed-on-hand versus unconfirmed items by name.

### Closing line

One short paragraph beginning `**Recommendation:**` that names the pick and gives one reason it fits the day.

### Prohibited

- No scoring systems, no ranked lists, no optimizing tiny macro differences.
- Do not describe a one-day gap as a medical deficiency.
- No prose paragraphs between the two tables.

A recommendation is not evidence of consumption. Use `../log-food/SKILL.md` only after the user says what they actually ate.
