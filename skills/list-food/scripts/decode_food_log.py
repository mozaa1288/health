#!/usr/bin/env python3
"""Decode a base64 food-log JSONL body into the current, display-ready meal rows.

Input: base64 content as produced by Google Drive `download_file_content`
(read from --base64-file, or stdin if omitted).

Output: JSON on stdout —
{
  "meals": [
    {"meal": "...", "description": "...", "logged_at": "...",
     "calories": 525 | null, "protein_g": 35 | null, "carbs_g": 27 | null, "fat_g": 33 | null}
  ],
  "totals": {"calories": 955 | null, "protein_g": 58 | null, "carbs_g": 54 | null, "fat_g": 62 | null},
  "lower_bound": true | false
}

Revision resolution: for each entry_id keep only the highest revision; drop it
entirely if that revision's status is "Deleted". Totals sum the unrounded
per-meal values and round only for display; any meal missing a nutrient makes
that nutrient's total a lower bound (never treated as zero).
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from typing import Any

NUTRIENTS = ("calories", "protein_g", "carbs_g", "fat_g")


class DecodeError(ValueError):
    pass


def current_meals(raw_text: str) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for line_number, raw in enumerate(raw_text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DecodeError(f"invalid JSON on line {line_number}: {exc}") from exc
        entry_id = record.get("entry_id")
        if not entry_id:
            raise DecodeError(f"missing entry_id on line {line_number}")
        prior = latest.get(entry_id)
        if prior is None:
            order.append(entry_id)
            latest[entry_id] = record
        elif record.get("revision", 0) >= prior.get("revision", 0):
            latest[entry_id] = record
    return [
        latest[entry_id]
        for entry_id in order
        if latest[entry_id].get("status") != "Deleted"
    ]


def build_output(raw_text: str) -> dict[str, Any]:
    meals = current_meals(raw_text)
    meals.sort(key=lambda r: r.get("logged_at") or "")

    rows: list[dict[str, Any]] = []
    totals: dict[str, float] = {n: 0.0 for n in NUTRIENTS}
    missing: set[str] = set()

    for record in meals:
        record_totals = record.get("totals") or {}
        row = {
            "meal": record.get("meal"),
            "description": record.get("description"),
            "logged_at": record.get("logged_at"),
        }
        for nutrient in NUTRIENTS:
            value = record_totals.get(nutrient)
            row[nutrient] = value
            if value is None:
                missing.add(nutrient)
            else:
                totals[nutrient] += float(value)
        rows.append(row)

    display_totals = {
        n: (None if n in missing else round(totals[n]) if n == "calories" else round(totals[n]))
        for n in NUTRIENTS
    }

    return {
        "meals": rows,
        "totals": display_totals,
        "lower_bound": bool(missing),
        "missing_nutrients": sorted(missing),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base64-file",
        help="Path to a file containing the base64 body. Reads stdin if omitted.",
    )
    args = parser.parse_args()

    if args.base64_file:
        with open(args.base64_file, "r", encoding="utf-8") as fh:
            encoded = fh.read()
    else:
        encoded = sys.stdin.read()

    try:
        raw_bytes = base64.b64decode(encoded.strip(), validate=False)
    except Exception as exc:  # noqa: BLE001 - surface any decode failure uniformly
        print(f"ERROR: could not base64-decode input: {exc}", file=sys.stderr)
        return 2

    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        print(f"ERROR: decoded bytes are not valid UTF-8: {exc}", file=sys.stderr)
        return 2

    try:
        result = build_output(raw_text)
    except DecodeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
