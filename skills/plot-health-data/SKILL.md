---
name: plot-health-data
description: Plot health trends from Drive-backed Food Log JSONL and Garmin daily archives. Use for requests to graph or compare calories eaten, total or active energy burned, energy balance, steps, exercise events, protein/carbs/fat, sleep, or resting heart rate across days or weeks.
---

# Plot Health Data

Create one responsive in-chat health visualization from canonical food logs and Garmin archives.

## Sources

- Food Logs: Drive folder `13E1t9q2JQrCliQyO8xecHNcDdUyhMjaI`, files `food-log-YYYY-MM-DD.jsonl`.
- Garmin archives: Drive folder `1PRhI2z03g_HwHXNJpfjQ7ff5Ijnk0786`, files `garmin_YYYY-MM-DD.json`.
- Interpret dates in `America/Los_Angeles`.

Download source files to disk. Do not paste large Garmin archives into context.

## Workflow

1. Resolve the range. Treat “last week” as the latest seven local dates ending today unless the user says “previous calendar week.”
2. Fetch the exact files for every date with one scoped Drive search per folder. Pick the newest Garmin archive per date by `pulled_at`.
3. Download files to disk. Missing files remain missing; never create zero-valued days.
4. Validate Garmin files with the installed `pull-garmin-data` reader when available. Reject suspected truncated reads.
5. Run:

   ```bash
   python scripts/build_health_plot.py \
     --start YYYY-MM-DD --end YYYY-MM-DD \
     --food-log food-log-YYYY-MM-DD.jsonl \
     --garmin garmin_YYYY-MM-DD.json \
     --output /workspace/health-data-YYYY-MM-DD-to-YYYY-MM-DD.html
   ```

   Repeat `--food-log` and `--garmin` for every available file.
6. Read the fragment, check that it contains literal HTML rather than escaped `\\n` or `\\"`, and syntax-check its script.
7. Emit only this reference on its own line:

   ```text
   visualize{"path":"/workspace/health-data-YYYY-MM-DD-to-YYYY-MM-DD.html"}
   ```

8. State only material gaps or one concise takeaway outside the visual.

## Accounting rules

- Resolve Food Log revisions by `entry_id`; exclude a winning `Deleted` revision.
- Sum food from `known_nutrition_subtotal`. Mark a lower bound when any active meal has `nutrition_incomplete_for`.
- Use `stats.totalKilocalories` for total expenditure, `stats.activeKilocalories` for movement and exercise energy, and `stats.bmrKilocalories` for resting expenditure.
- Active energy is already included in total expenditure. Never add `activities[].calories` to active or total burn; use activities only as event annotations and breakdowns.
- Compute exact energy balance only when food nutrition and the Garmin day are complete.
- Mark a Garmin archive partial when `stats.wellnessEndTimeLocal` has not passed the local date.
- Missing, null, empty, failed, and partial values are not zero.

## Default panels

Show energy intake versus total expenditure, active/resting burn composition, steps with exercise annotations, macro target coverage, sleep hours, and resting heart rate. Omit an entirely unavailable panel rather than filling it with zeros.
