#!/usr/bin/env python3
"""Compile a food-log entry into validated Google Sheet rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

NUTRIENT_COLUMNS = {
    "calories": ("calories",),
    "protein_g": ("protein [g]",),
    "carbs_g": ("carbohydrate [g]",),
    "fat_g": ("fat [g]", "total_fat [g]"),
    "fiber_g": ("fiber [g]",),
    "sodium_mg": ("sodium [mg]",),
}
NUTRIENTS = tuple(NUTRIENT_COLUMNS)
MATCH_LABELS = {
    "exact": "Exact",
    "proxy": "Proxy",
    "label": "Label",
    "official": "Official",
    "open_food_facts": "Open Food Facts",
    "unresolved": "Unresolved",
}
ALLOWED_MEALS = {"Breakfast", "Lunch", "Dinner", "Snack", "Other"}
ALLOWED_CONFIDENCE = {"High", "Medium", "Low"}
ALLOWED_SOURCES = {
    "Planned Meal",
    "Canonical CSV",
    "Package Label",
    "Official Restaurant",
    "Open Food Facts",
    "Unresolved",
}
LOCAL_ZONE = ZoneInfo("America/Los_Angeles")


class CompileError(ValueError):
    pass


def decimal(value: Any, label: str) -> Decimal:
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CompileError(f"{label} must be numeric") from exc


def parse_numeric(value: Any, label: str) -> Decimal:
    text = "" if value is None else str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        raise CompileError(f"blank nutrition value for {label}")
    try:
        return Decimal(text)
    except InvalidOperation:
        match = re.fullmatch(r"\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*[a-zA-Z%]*\s*", text)
        if not match:
            raise CompileError(f"nonnumeric nutrition value for {label}: {value!r}")
        return Decimal(match.group(1))


def clean(value: Decimal, places: int = 2) -> int | float:
    if value == value.to_integral():
        return int(value)
    quant = Decimal("1").scaleb(-places)
    rounded = value.quantize(quant)
    return int(rounded) if rounded == rounded.to_integral() else float(rounded)


@dataclass(frozen=True)
class NutritionRecord:
    row_id: str
    name: str
    serving_g: Decimal
    nutrients: dict[str, Decimal]


@dataclass(frozen=True)
class NutritionDatabase:
    sha256: str
    row_count: int
    by_id: dict[str, NutritionRecord]
    by_name: dict[str, list[NutritionRecord]]


def select_column(fieldnames: list[str], candidates: tuple[str, ...], label: str) -> str:
    for candidate in candidates:
        if candidate in fieldnames:
            return candidate
    raise CompileError(f"nutrition CSV missing {label}; expected one of {candidates}")


def load_database(path: Path, config: dict[str, Any]) -> NutritionDatabase:
    raw = path.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()
    expected = str(config.get("expected_sha256", "")).strip().lower()
    if expected and expected != sha256:
        raise CompileError(f"nutrition CSV hash mismatch: expected {expected}, got {sha256}")

    reader = csv.DictReader(raw.decode("utf-8-sig").splitlines())
    fieldnames = list(reader.fieldnames or [])
    if not fieldnames:
        raise CompileError("nutrition CSV has no header")
    id_col = str(config.get("id_column", "Unnamed: 0"))
    name_col = str(config.get("name_column", "name"))
    serving_col = str(config.get("serving_column", "serving_size [g]"))
    for required in (id_col, name_col, serving_col):
        if required not in fieldnames:
            raise CompileError(f"nutrition CSV missing required column {required!r}")
    nutrient_cols = {
        key: select_column(fieldnames, candidates, key)
        for key, candidates in NUTRIENT_COLUMNS.items()
    }

    by_id: dict[str, NutritionRecord] = {}
    by_name: dict[str, list[NutritionRecord]] = defaultdict(list)
    count = 0
    for row in reader:
        count += 1
        row_id = str(row.get(id_col, "")).strip()
        name = str(row.get(name_col, "")).strip()
        if not row_id or not name:
            raise CompileError(f"nutrition CSV row {count + 1} lacks ID or name")
        if row_id in by_id:
            raise CompileError(f"duplicate nutrition row ID {row_id}")
        serving = parse_numeric(row.get(serving_col), f"{name} serving")
        if serving <= 0:
            raise CompileError(f"{name} has a nonpositive serving size")
        nutrients = {
            key: parse_numeric(row.get(column), f"{name} {key}")
            for key, column in nutrient_cols.items()
        }
        record = NutritionRecord(row_id, name, serving, nutrients)
        by_id[row_id] = record
        by_name[name.casefold()].append(record)
    if not count:
        raise CompileError("nutrition CSV contains no data")
    return NutritionDatabase(sha256, count, by_id, dict(by_name))


def resolve_record(item: dict[str, Any], db: NutritionDatabase) -> NutritionRecord:
    raw_id = item.get("nutrition_row_id")
    raw_name = item.get("nutrition_name")
    if raw_id is None and raw_name is None:
        raise CompileError(f"{item.get('item')!r} needs a nutrition row ID or name")
    by_id = db.by_id.get(str(raw_id).strip()) if raw_id is not None else None
    if raw_id is not None and by_id is None:
        raise CompileError(f"{item.get('item')!r} references a missing nutrition row")
    by_name = None
    if raw_name is not None:
        matches = db.by_name.get(str(raw_name).strip().casefold(), [])
        if len(matches) != 1:
            raise CompileError(f"{item.get('item')!r} nutrition name is missing or ambiguous")
        by_name = matches[0]
    if by_id and by_name and by_id.row_id != by_name.row_id:
        raise CompileError(f"{item.get('item')!r} row ID and name disagree")
    return by_id or by_name  # type: ignore[return-value]


def supplied_nutrition(values: Any, label: str) -> dict[str, Any]:
    if not isinstance(values, dict):
        raise CompileError(f"{label} requires a nutrition object")
    nutrients: dict[str, Any] = {}
    for key in NUTRIENTS:
        value = values.get(key)
        if key in {"fiber_g", "sodium_mg"} and value is None:
            nutrients[key] = None
        else:
            parsed = decimal(value, f"{label} {key}")
            if parsed < 0:
                raise CompileError(f"{label} {key} cannot be negative")
            nutrients[key] = clean(parsed)
    return nutrients


def valid_official_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def item_nutrition(item: dict[str, Any], db: NutritionDatabase) -> tuple[dict[str, Any], str, str]:
    match_type = str(item.get("nutrition_match_type", "exact")).strip().lower()
    if match_type not in MATCH_LABELS:
        raise CompileError(f"unsupported nutrition_match_type {match_type!r}")
    note = str(item.get("nutrition_match_note", "")).strip()
    if match_type in {"proxy", "unresolved"} and not note:
        raise CompileError(f"{match_type} item requires nutrition_match_note")
    has_csv_reference = item.get("nutrition_row_id") is not None or item.get("nutrition_name") is not None
    has_label = item.get("label_nutrition") is not None
    has_official = item.get("official_nutrition") is not None
    has_open_food_facts = item.get("open_food_facts_nutrition") is not None

    if match_type == "unresolved":
        if has_csv_reference or has_label or has_official or has_open_food_facts:
            raise CompileError("unresolved item cannot also contain resolved nutrition")
        return ({key: None for key in NUTRIENTS}, "", MATCH_LABELS[match_type])

    if match_type == "label":
        if has_csv_reference or has_official or has_open_food_facts:
            raise CompileError("label item cannot also contain CSV or official nutrition")
        return supplied_nutrition(item.get("label_nutrition"), "label"), "", MATCH_LABELS[match_type]

    if match_type == "official":
        if has_csv_reference or has_label or has_open_food_facts:
            raise CompileError("official item cannot also contain CSV or label nutrition")
        return (
            supplied_nutrition(item.get("official_nutrition"), "official"),
            "",
            MATCH_LABELS[match_type],
        )

    if match_type == "open_food_facts":
        if has_label or has_official or item.get("nutrition_name") is not None:
            raise CompileError("Open Food Facts item cannot also contain CSV, label, or official nutrition")
        barcode = str(item.get("nutrition_row_id", "")).strip()
        if not barcode or not barcode.isdigit():
            raise CompileError("Open Food Facts item requires a numeric barcode as nutrition_row_id")
        return (
            supplied_nutrition(item.get("open_food_facts_nutrition"), "Open Food Facts"),
            barcode,
            MATCH_LABELS[match_type],
        )

    if has_label or has_official or has_open_food_facts:
        raise CompileError("CSV-backed item cannot also contain supplied nutrition")
    record = resolve_record(item, db)
    grams = decimal(item.get("nutrition_grams_total"), "nutrition_grams_total")
    if grams < 0:
        raise CompileError("nutrition_grams_total cannot be negative")
    factor = grams / record.serving_g
    nutrients = {key: clean(value * factor) for key, value in record.nutrients.items()}
    return nutrients, record.row_id, MATCH_LABELS[match_type]


def compile_entry(entry: dict[str, Any], db: NutritionDatabase) -> dict[str, Any]:
    entry_id = str(entry.get("entry_id", "")).strip()
    logged_at = str(entry.get("logged_at", "")).strip()
    local_date = str(entry.get("local_date", "")).strip()
    meal = str(entry.get("meal", "")).strip().title()
    description = str(entry.get("description", "")).strip()
    original_text = str(entry.get("original_text", "")).strip()
    planned_meal_id = str(entry.get("planned_meal_id") or "").strip()
    if not all((entry_id, logged_at, local_date, description, original_text)):
        raise CompileError("entry requires ID, timestamp, local date, description, and original text")
    try:
        parsed_time = datetime.fromisoformat(logged_at)
        parsed_date = datetime.strptime(local_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise CompileError("logged_at or local_date is not valid ISO format") from exc
    if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
        raise CompileError("logged_at must include a UTC offset")
    if parsed_time.date() != parsed_date:
        raise CompileError("logged_at date and local_date disagree")
    los_angeles_time = parsed_time.astimezone(LOCAL_ZONE)
    if (
        los_angeles_time.replace(tzinfo=None) != parsed_time.replace(tzinfo=None)
        or los_angeles_time.utcoffset() != parsed_time.utcoffset()
    ):
        raise CompileError("logged_at must represent local America/Los_Angeles time")
    if meal not in ALLOWED_MEALS:
        raise CompileError(f"meal must be one of {sorted(ALLOWED_MEALS)}")
    items = entry.get("items")
    if not isinstance(items, list) or not items:
        raise CompileError("entry requires at least one item")

    rows: list[list[Any]] = []
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    totals = {key: Decimal("0") for key in NUTRIENTS}
    incomplete: list[str] = []
    updated = str(entry.get("last_updated") or logged_at)

    for raw in items:
        if not isinstance(raw, dict):
            raise CompileError("every item must be an object")
        item_id = str(raw.get("item_id", "")).strip()
        name = str(raw.get("item", "")).strip()
        unit = str(raw.get("unit", "")).strip()
        quantity = decimal(raw.get("quantity"), f"{name or 'item'} quantity")
        confidence = str(raw.get("confidence", "")).strip().title()
        source = str(raw.get("source", "")).strip()
        source_url = str(raw.get("source_url", "")).strip()
        source_accessed = str(raw.get("source_accessed", "")).strip()
        if not all((item_id, name, unit, confidence, source)):
            raise CompileError("every item needs ID, name, unit, confidence, and source")
        if item_id in seen_ids:
            raise CompileError(f"duplicate item_id {item_id!r}")
        seen_ids.add(item_id)
        if quantity < 0:
            raise CompileError("quantity cannot be negative")
        if confidence not in ALLOWED_CONFIDENCE:
            raise CompileError(f"confidence must be one of {sorted(ALLOWED_CONFIDENCE)}")
        if source not in ALLOWED_SOURCES:
            raise CompileError(f"source must be one of {sorted(ALLOWED_SOURCES)}")
        match_type = str(raw.get("nutrition_match_type", "exact")).strip().lower()
        if match_type == "label" and source != "Package Label":
            raise CompileError("label nutrition requires Source = Package Label")
        if match_type == "official" and source != "Official Restaurant":
            raise CompileError("official nutrition requires Source = Official Restaurant")
        if match_type == "open_food_facts" and source != "Open Food Facts":
            raise CompileError("Open Food Facts nutrition requires Source = Open Food Facts")
        if match_type == "unresolved" and source != "Unresolved":
            raise CompileError("unresolved nutrition requires Source = Unresolved")
        if match_type in {"exact", "proxy"} and source not in {"Planned Meal", "Canonical CSV"}:
            raise CompileError("CSV-backed nutrition requires Source = Planned Meal or Canonical CSV")
        if source in {"Official Restaurant", "Open Food Facts"}:
            if not valid_official_url(source_url):
                raise CompileError(f"{source} nutrition requires an HTTPS source_url")
            try:
                datetime.strptime(source_accessed, "%Y-%m-%d")
            except ValueError as exc:
                raise CompileError(f"{source} nutrition requires source_accessed YYYY-MM-DD") from exc
        elif source_url or source_accessed:
            raise CompileError(
                "source_url and source_accessed are reserved for Official Restaurant or Open Food Facts"
            )
        nutrients, row_id, match_label = item_nutrition(raw, db)
        grams_raw = raw.get("nutrition_grams_total")
        grams = clean(decimal(grams_raw, "nutrition_grams_total"), 3) if grams_raw is not None else None
        note = str(raw.get("nutrition_match_note", "")).strip()
        if any(nutrients[key] is None for key in ("calories", "protein_g", "carbs_g", "fat_g")):
            incomplete.append(name)
        for key, value in nutrients.items():
            if value is not None:
                totals[key] += decimal(value, key)
        rows.append([
            entry_id, item_id, logged_at, local_date, meal, description, name,
            clean(quantity, 3), unit, grams, nutrients["calories"], nutrients["protein_g"],
            nutrients["carbs_g"], nutrients["fat_g"], nutrients["fiber_g"],
            nutrients["sodium_mg"], row_id, match_label, source, planned_meal_id,
            confidence, original_text, note, updated, "Active", source_url, source_accessed,
        ])
        normalized.append({
            "item_id": item_id,
            "item": name,
            "quantity": clean(quantity, 3),
            "unit": unit,
            "edible_grams": grams,
            "nutrition": nutrients,
            "nutrition_row_id": row_id or None,
            "nutrition_match": match_label,
            "source": source,
            "confidence": confidence,
            "note": note or None,
            "source_url": source_url or None,
            "source_accessed": source_accessed or None,
        })

    return {
        "status": "validated" if not incomplete else "logged_with_gaps",
        "entry_id": entry_id,
        "logged_at": logged_at,
        "local_date": local_date,
        "meal": meal,
        "description": description,
        "planned_meal_id": planned_meal_id or None,
        "items": normalized,
        "totals": {
            key: (None if incomplete else clean(value))
            for key, value in totals.items()
        },
        "known_nutrition_subtotal": {
            key: clean(value) for key, value in totals.items()
        },
        "nutrition_incomplete_for": incomplete,
        "nutrition_database": {
            "sha256": db.sha256,
            "row_count": db.row_count,
        },
        "sheet_rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("entry_json", type=Path)
    parser.add_argument("--nutrition-csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        entry = json.loads(args.entry_json.read_text(encoding="utf-8"))
        if not isinstance(entry, dict):
            raise CompileError("entry JSON must be an object")
        config = entry.get("nutrition_database") or {}
        if not isinstance(config, dict):
            raise CompileError("nutrition_database must be an object")
        database = load_database(args.nutrition_csv, config)
        compiled = compile_entry(entry, database)
        args.output.write_text(json.dumps(compiled, indent=2) + "\n", encoding="utf-8")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, CompileError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
