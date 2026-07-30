---
name: list-food
description: Read back what has already been eaten on a given day from the Google Drive Food Logs folder and show it as one table. Read-only — use for "what have I eaten today", "show my log", daily totals. Never logs, edits, or adds food; use log-food for that.
---

# List Food

Read-only. This skill never writes to Drive.

Drive folder ID: `13E1t9q2JQrCliQyO8xecHNcDdUyhMjaI`
File: `food-log-YYYY-MM-DD.jsonl`

## Algorithm

1. Resolve the date in `America/Los_Angeles`. Default: today.
2. `search_files` the folder for `food-log-<date>.jsonl`, then `download_file_content`. No file means an empty day — say so and stop.
3. Decode the base64 body and parse one JSON record per line.
4. Revision resolution: for each `entry_id` keep only the highest `revision`; drop it entirely if that revision has `status == "Deleted"`.
5. Render the table below. Sum from unrounded `totals`; round only for display.

## Output

One table, meals in chronological order by `logged_at`.

| Meal | Item | Cal | Protein | Carbs | Fat |
|---|---|---:|---:|---:|---:|
| Breakfast | Fage yogurt with blueberries | 525 | 35 g | 27 g | 33 g |
| Lunch | Kale and avocado salad | 430 | 23 g | 27 g | 29 g |
| **Total** | | **955** | **58 g** | **54 g** | **62 g** |

- Use each record's `description` for Item.
- Calories are whole numbers; macros round to the nearest gram with a `g` suffix.
- A missing nutrient renders `—`, and makes Total a lower bound (`≥ 955`). Never substitute zero.
- Nothing else — no commentary, no assumptions list, no advice unless asked.

If the user asks how the day compares to targets, use the Food-Log Reporting Contract in `log-food` rather than inventing targets here.
