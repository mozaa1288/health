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
2. `search_files` the folder for `food-log-<date>.jsonl`. No file means an empty day — say so and stop. Then fetch it:
   - **Try `read_file_content` first.** Logs written as `text/plain` come back as plain text, no base64. It markdown-escapes the body (`entry\_id`, `protein\_g`, `\[`) — read straight through that; never hand it to a JSON parser.
   - **Fall back to `download_file_content`** if that errors on mime type. Legacy logs are `application/x-ndjson` and only work this way, returning base64.
3. Read and interpret the body yourself, record by record. Do **not** write it to a file, pipe it into bash, or call a script — a real log runs several KB and will truncate or break shell quoting. There is no channel between Drive output and bash except retyping it, and retyping is the failure.
4. Revision resolution: per `entry_id` keep only the highest `revision`; drop the entry entirely if that revision has `status == "Deleted"`.
5. Render the table below. Sum unrounded per-meal `totals`; round once for display.

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
