---
name: reconcile-daily-food
description: Reconcile explicit food-consumption statements from recent ChatGPT conversations against the dedicated Google Drive Food Consumption Log, then add only genuinely missing entries through log-food. Use for end-of-day food-log catch-up, scheduled daily nutrition reconciliation, “did I forget to log anything?”, “sync what I ate today,” dry-run food-log audits, or reconciling a specified local date without duplicating existing meals.
---

# Reconcile Daily Food

Find missing consumption evidence, classify it deterministically, and route safe additions through
`log-food`. Default to the current `America/Los_Angeles` calendar date unless the user specifies a
different date.

Never treat plans, recommendations, purchases, recipes, third-party statements, or assistant
summaries as evidence that the user ate something.

## Choose the mode

- **Reconcile and write:** Default. Add safe missing entries and verify them.
- **Dry run:** When the user asks to preview, audit, check, or avoid changes, return the
  reconciliation plan without writing.
- **Scheduled run:** Reconcile and write. Stay silent when nothing is missing. Report additions or
  one concise clarification request.

## Workflow

### 1. Establish the target

Resolve the target local date in `America/Los_Angeles`. For a scheduled run, use the local date at
execution time. Interpret a statement's explicit date or relative wording before assigning it to
the target date; do not use the message-posting date when the user clearly describes another day.

### 2. Retrieve consumption evidence

Use Personal Context to search recent ChatGPT conversation history for user-authored,
first-person statements about food or drinks consumed on the target date.

Write a self-contained, date-bounded search request. Keep only direct user evidence such as
“I ate,” “I had,” or “I drank.” Exclude:

- assistant outputs and generated meal plans;
- email, calendar, files, or third-party statements unless the user explicitly asks to include
  that source;
- intentions, future meals, shopping, recipes, food preparation, and recommendations;
- vague context that does not establish consumption.

Preserve each statement's original text and available message timestamp or reference. Combine
multiple statements only when they clearly describe the same eating event.

### 3. Read the authoritative log

Resolve `food-log` through the live `Health Data Registry` by exact asset key. Require the
registered active Drive ID to equal `12Exzl-EZWxkiN0cd9XafE9R7a_MBoNiZuio46deANnQ`.

Read spreadsheet metadata and the complete bounded `Food Log` range. Require the 27-column schema
defined by `log-food`. Use active rows to determine what is currently logged. Retain deleted rows
as historical blockers so an exact previously removed entry is not silently recreated.

Do not read or write consumption rows in `Pantry & Fridge Inventory Tracker`.

### 4. Build and classify candidates

Read [references/reconciliation-input.md](references/reconciliation-input.md). Convert the evidence
and existing log rows into the documented JSON inputs, then run:

```bash
python scripts/reconcile_food_log.py \
  --candidates candidates.json \
  --food-log-rows food_log_rows.json \
  --output reconciliation_plan.json
```

Resolve the script relative to this skill directory. Do not manually override its classification.
The script is deliberately conservative:

- `already_logged`: take no action;
- `missing`: eligible for `log-food`;
- `needs_clarification`: do not write; ask for the essential missing detail;
- `ambiguous_match`: do not append or correct automatically;
- `ignored`: outside the target or not direct consumption evidence.

### 5. Write only safe missing entries

For every `missing` candidate, use `log-food` and follow its complete source-resolution,
compilation, deduplication, and verification contract. Preserve the evidence's original wording.
Use stable entry and item identifiers so retries are idempotent.

Nutrition uncertainty alone does not block logging: when the consumed item and quantity are clear
but nutrition cannot be resolved without guessing, let `log-food` write blank nutrition with an
unresolved disclosure. Missing quantity, incomplete configurable restaurant build, or uncertain
event identity does block automatic writing.

Never infer pantry depletion or alter pantry inventory during reconciliation.

### 6. Verify and respond

Re-read every affected `Food Log` entry and verify the local date, items, quantities, status, and
source metadata. Verify `Daily Summary` recalculates when practical.

- If entries were added, report what was added and any unresolved gap concisely.
- If clarification is required, ask at most one concise question that groups the essential gaps.
- If only ambiguous matches remain, identify them without writing.
- If a scheduled run finds nothing missing, do not notify the user.
- If a manual run finds nothing missing, say the target date is already reconciled.

## Failure rules

Stop before writing when the registry, workbook identity, schema, Personal Context source, or
reconciliation script cannot be verified. Never fall back to name-only Drive search, assistant
memory, or a newly created replacement workbook.
