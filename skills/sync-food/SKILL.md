---
name: sync-food
description: Check recent consumption statements against daily JSONL food logs in Google Drive and add only clear missing meals through the log-food workflow.
---

# Sync Food

Compare direct user statements about consumed food with the matching daily JSONL log in Google Drive folder `13E1t9q2JQrCliQyO8xecHNcDdUyhMjaI`. Default to the current `America/Los_Angeles` date unless another date is specified.

## Workflow

1. Search Personal Context for user-authored, first-person statements about food or drinks consumed on the target date.
2. Keep only direct evidence such as “I ate,” “I had,” or “I drank.” Exclude plans, recommendations, shopping, recipes, assistant summaries, and third-party statements.
3. Preserve the user's original wording and available timestamp. Combine statements only when they clearly describe the same eating event.
4. Fetch the exact `food-log-YYYY-MM-DD.jsonl` filename from Drive folder `13E1t9q2JQrCliQyO8xecHNcDdUyhMjaI` and run `../log-food/scripts/food_log_jsonl.py read --all-history`.
5. Compare each consumption statement with existing meals using date, meal, description, items, quantities, and timing.
6. Classify each statement directly:
   - clearly already logged: do nothing;
   - clearly missing with enough detail: send it through `../log-food/SKILL.md`;
   - unclear quantity, uncertain event identity, or ambiguous match: do not write and ask one concise question;
   - not actual consumption: ignore it.
7. Upload a missing daily file or replace the existing Drive file bytes in place, then verify the date, items, quantities, revision, status, filename, and parent folder.

## Rules

- Never create an entry from a plan or recommendation.
- Never duplicate an existing or previously deleted `entry_id`; the last revision wins.
- Nutrition uncertainty alone does not block logging when the consumed item and quantity are clear; `log-food` may leave nutrients blank.
- Never alter pantry inventory during reconciliation.
- Do not use assistant memory as consumption evidence.

## Response

- Scheduled run with nothing missing: stay silent.
- Manual run with nothing missing: say the date is reconciled.
- Added entries: report them concisely.
- Ambiguous evidence: ask at most one grouped clarification question.
