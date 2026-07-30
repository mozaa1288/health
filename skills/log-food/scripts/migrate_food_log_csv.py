#!/usr/bin/env python3
"""Migrate a legacy food-log CSV export into daily JSONL files."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

from food_log_jsonl import ALL_NUTRIENTS, SCHEMA_VERSION, validate_record
from unit_conversions import ConversionError, base_quantity

LEGACY_HEADERS = (
    "Entry ID",
    "Item ID",
    "Logged At",
    "Local Date",
    "Meal",
    "Description",
    "Item",
    "Quantity",
    "Unit",
    "Edible Grams",
    "Calories",
    "Protein g",
    "Carbs g",
    "Fat g",
    "Fiber g",
    "Sodium mg",
    "Nutrition Row ID",
    "Nutrition Match",
    "Source",
    "Planned Meal ID",
    "Confidence",
    "Original Text",
    "Notes",
    "Last Updated",
    "Status",
    "Source URL",
    "Source Accessed",
)
NUTRIENT_HEADERS = {
    "calories": "Calories",
    "protein_g": "Protein g",
    "carbs_g": "Carbs g",
    "fat_g": "Fat g",
    "fiber_g": "Fiber g",
    "sodium_mg": "Sodium mg",
}


class MigrationError(ValueError):
    pass


def value_number(value: Any) -> int | float | None:
    text = str(value or "").strip()
    if not text:
        return None
    number = float(text)
    return int(number) if number.is_integer() else number


def migrate_group(rows: list[dict[str, str]]) -> dict[str, Any]:
    first = rows[0]
    local_date = first["Local Date"].strip()
    entry_id = first["Entry ID"].strip()
    if not local_date or not entry_id:
        raise MigrationError("legacy rows require Local Date and Entry ID")

    items: list[dict[str, Any]] = []
    subtotal = {name: 0.0 for name in ALL_NUTRIENTS}
    incomplete_core = False
    for row in rows:
        quantity = value_number(row["Quantity"])
        unit = row["Unit"].strip()
        if quantity is None or not unit:
            raise MigrationError(f"{entry_id}: item lacks quantity or unit")
        try:
            amount, base_unit = base_quantity(quantity, unit)
        except ConversionError as exc:
            raise MigrationError(f"{entry_id}: {exc}") from exc
        nutrition = {
            field: value_number(row[header])
            for field, header in NUTRIENT_HEADERS.items()
        }
        if any(nutrition[name] is None for name in ("calories", "protein_g", "carbs_g", "fat_g")):
            incomplete_core = True
        for field, value in nutrition.items():
            if value is not None:
                subtotal[field] += float(value)
        items.append(
            {
                "item_id": row["Item ID"].strip(),
                "item": row["Item"].strip(),
                "quantity": quantity,
                "unit": unit,
                "base_quantity": {
                    "amount": int(amount) if amount == amount.to_integral() else float(amount),
                    "unit": base_unit,
                },
                "edible_grams": value_number(row["Edible Grams"]),
                "nutrition": nutrition,
                "nutrition_row_id": row["Nutrition Row ID"].strip() or None,
                "nutrition_match": row["Nutrition Match"].strip() or "Unresolved",
                "source": row["Source"].strip() or "Unresolved",
                "confidence": row["Confidence"].strip() or "Low",
                "note": row["Notes"].strip() or None,
                "source_url": row["Source URL"].strip() or None,
                "source_accessed": row["Source Accessed"].strip() or None,
            }
        )

    rounded_subtotal = {
        field: round(value, 2) for field, value in subtotal.items()
    }
    statuses = {row["Status"].strip() or "Active" for row in rows}
    status = "Deleted" if statuses == {"Deleted"} else "Active"
    updated = max(
        (row["Last Updated"].strip() for row in rows if row["Last Updated"].strip()),
        default=first["Logged At"].strip(),
    )
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "meal",
        "entry_id": entry_id,
        "revision": 1,
        "status": status,
        "logged_at": first["Logged At"].strip(),
        "local_date": local_date,
        "meal": first["Meal"].strip().title(),
        "description": first["Description"].strip(),
        "original_text": first["Original Text"].strip() or first["Description"].strip(),
        "planned_meal_id": first["Planned Meal ID"].strip() or None,
        "last_updated": updated,
        "items": items,
        "totals": {
            field: (
                None
                if incomplete_core
                else rounded_subtotal[field]
            )
            for field in ALL_NUTRIENTS
        },
        "known_nutrition_subtotal": rounded_subtotal,
        "nutrition_incomplete_for": [
            item["item"]
            for item in items
            if any(item["nutrition"][name] is None for name in ("calories", "protein_g", "carbs_g", "fat_g"))
        ],
        "nutrition_database": {"sha256": None, "row_count": None},
        "validation": {
            "state": "migrated_with_gaps" if incomplete_core else "migrated",
            "source": "legacy Food Consumption Log CSV",
        },
    }
    return validate_record(record, local_date)


def migrate(input_csv: Path, output_dir: Path, force: bool = False) -> dict[str, int]:
    with input_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != LEGACY_HEADERS:
            raise MigrationError("legacy CSV does not have the expected 27 headers")
        groups: OrderedDict[tuple[str, str], list[dict[str, str]]] = OrderedDict()
        for row in reader:
            key = (row["Local Date"].strip(), row["Entry ID"].strip())
            groups.setdefault(key, []).append(row)

    by_date: dict[str, list[dict[str, Any]]] = {}
    for rows in groups.values():
        record = migrate_group(rows)
        by_date.setdefault(record["local_date"], []).append(record)

    output_dir.mkdir(parents=True, exist_ok=True)
    records_written = 0
    for local_date, records in sorted(by_date.items()):
        destination = output_dir / f"food-log-{local_date}.jsonl"
        if destination.exists() and not force:
            raise MigrationError(f"destination exists: {destination}")
        records.sort(key=lambda row: (row["logged_at"], row["entry_id"]))
        text = "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            + "\n"
            for record in records
        )
        destination.write_text(text, encoding="utf-8")
        records_written += len(records)
    return {"files_written": len(by_date), "records_written": records_written}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("legacy_csv", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        result = migrate(args.legacy_csv, args.output_dir, args.force)
        print(json.dumps(result, indent=2))
    except (OSError, UnicodeDecodeError, ValueError, MigrationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
