#!/usr/bin/env python3
"""Validate and rank next-meal options against a planned daily nutrition baseline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

LOCAL_ZONE = ZoneInfo("America/Los_Angeles")
NUTRIENT_COLUMNS = {
    "calories": ("calories",),
    "protein_g": ("protein [g]",),
    "carbs_g": ("carbohydrate [g]",),
    "fat_g": ("fat [g]", "total_fat [g]"),
    "fiber_g": ("fiber [g]",),
    "sodium_mg": ("sodium [mg]",),
}
NUTRIENTS = tuple(NUTRIENT_COLUMNS)
CORE_NUTRIENTS = ("calories", "protein_g", "carbs_g", "fat_g")
ALLOWED_AVAILABILITY = {
    "planned": 0,
    "confirmed_pantry": 1,
    "projected_pantry": 8,
    "purchase_required": 20,
}
ALLOWED_KINDS = {"planned_meal", "adjusted_planned_meal", "pantry_meal", "snack"}


class RecommendationError(ValueError):
    pass


def D(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RecommendationError(f"{label} must be numeric") from exc
    if not result.is_finite():
        raise RecommendationError(f"{label} must be finite")
    return result


def clean(value: Decimal, places: int = 2) -> int | float:
    quant = Decimal("1").scaleb(-places)
    rounded = value.quantize(quant)
    return int(rounded) if rounded == rounded.to_integral() else float(rounded)


def nonnegative_nutrients(raw: Any, label: str) -> dict[str, Decimal]:
    if not isinstance(raw, dict):
        raise RecommendationError(f"{label} must be an object")
    result: dict[str, Decimal] = {}
    for nutrient in NUTRIENTS:
        value = D(raw.get(nutrient), f"{label}.{nutrient}")
        if value < 0:
            raise RecommendationError(f"{label}.{nutrient} cannot be negative")
        result[nutrient] = value
    return result


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
    raise RecommendationError(f"nutrition CSV missing {label}; expected one of {candidates}")


def parse_csv_number(value: Any, label: str) -> Decimal:
    text = "" if value is None else str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        raise RecommendationError(f"blank nutrition value for {label}")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise RecommendationError(f"nonnumeric nutrition value for {label}: {value!r}") from exc


def load_database(path: Path, config: dict[str, Any]) -> NutritionDatabase:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    expected = str(config.get("expected_sha256", "")).strip().lower()
    if expected and expected != digest:
        raise RecommendationError(
            f"nutrition CSV hash mismatch: expected {expected}, got {digest}"
        )
    reader = csv.DictReader(raw.decode("utf-8-sig").splitlines())
    fieldnames = list(reader.fieldnames or [])
    if not fieldnames:
        raise RecommendationError("nutrition CSV has no header")
    id_col = str(config.get("id_column", "Unnamed: 0"))
    name_col = str(config.get("name_column", "name"))
    serving_col = str(config.get("serving_column", "serving_size [g]"))
    for required in (id_col, name_col, serving_col):
        if required not in fieldnames:
            raise RecommendationError(f"nutrition CSV missing required column {required!r}")
    nutrient_cols = {
        key: select_column(fieldnames, candidates, key)
        for key, candidates in NUTRIENT_COLUMNS.items()
    }
    by_id: dict[str, NutritionRecord] = {}
    by_name: dict[str, list[NutritionRecord]] = defaultdict(list)
    count = 0
    for row_number, row in enumerate(reader, start=2):
        count += 1
        row_id = str(row.get(id_col, "")).strip()
        name = str(row.get(name_col, "")).strip()
        if not row_id or not name:
            raise RecommendationError(f"nutrition CSV row {row_number} lacks ID or name")
        if row_id in by_id:
            raise RecommendationError(f"duplicate nutrition row ID {row_id}")
        serving = parse_csv_number(row.get(serving_col), f"{name} serving")
        if serving <= 0:
            raise RecommendationError(f"{name} has a nonpositive serving size")
        nutrients = {
            nutrient: parse_csv_number(row.get(column), f"{name} {nutrient}")
            for nutrient, column in nutrient_cols.items()
        }
        record = NutritionRecord(row_id, name, serving, nutrients)
        by_id[row_id] = record
        by_name[name.casefold()].append(record)
    if not count:
        raise RecommendationError("nutrition CSV contains no rows")
    return NutritionDatabase(digest, count, by_id, dict(by_name))


def resolve_record(item: dict[str, Any], db: NutritionDatabase) -> NutritionRecord:
    raw_id = item.get("nutrition_row_id")
    raw_name = item.get("nutrition_name")
    if raw_id is None and raw_name is None:
        raise RecommendationError(
            f"ingredient {item.get('ingredient')!r} needs nutrition_row_id or nutrition_name"
        )
    by_id = db.by_id.get(str(raw_id).strip()) if raw_id is not None else None
    if raw_id is not None and by_id is None:
        raise RecommendationError(
            f"ingredient {item.get('ingredient')!r} references missing nutrition row {raw_id!r}"
        )
    by_name = None
    if raw_name is not None:
        matches = db.by_name.get(str(raw_name).strip().casefold(), [])
        if len(matches) != 1:
            raise RecommendationError(
                f"ingredient {item.get('ingredient')!r} nutrition name is missing or ambiguous"
            )
        by_name = matches[0]
    if by_id and by_name and by_id.row_id != by_name.row_id:
        raise RecommendationError(
            f"ingredient {item.get('ingredient')!r} row ID and name disagree"
        )
    return by_id or by_name  # type: ignore[return-value]


def validate_local_date(local_date: str, as_of_local: str) -> None:
    try:
        target_date = datetime.strptime(local_date, "%Y-%m-%d").date()
        timestamp = datetime.fromisoformat(as_of_local)
    except ValueError as exc:
        raise RecommendationError("local_date or as_of_local is not valid ISO format") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise RecommendationError("as_of_local must include a UTC offset")
    local_timestamp = timestamp.astimezone(LOCAL_ZONE)
    if local_timestamp.date() != target_date:
        raise RecommendationError(
            "as_of_local does not resolve to local_date in America/Los_Angeles"
        )


def compile_option(option: dict[str, Any], db: NutritionDatabase) -> dict[str, Any]:
    option_id = str(option.get("id", "")).strip()
    name = str(option.get("name", "")).strip()
    kind = str(option.get("kind", "")).strip().lower()
    availability = str(option.get("availability", "")).strip().lower()
    preparation = str(option.get("preparation", "")).strip()
    if not all((option_id, name, kind, availability, preparation)):
        raise RecommendationError(
            "every option needs id, name, kind, availability, and preparation"
        )
    if kind not in ALLOWED_KINDS:
        raise RecommendationError(f"unsupported option kind {kind!r}")
    if availability not in ALLOWED_AVAILABILITY:
        raise RecommendationError(f"unsupported availability {availability!r}")
    planned_meal_id = str(option.get("planned_meal_id") or "").strip()
    if availability == "planned" and not planned_meal_id:
        raise RecommendationError("planned availability requires planned_meal_id")
    ingredients = option.get("ingredients")
    if not isinstance(ingredients, list) or not ingredients:
        raise RecommendationError(f"option {option_id!r} requires ingredients")

    totals = {nutrient: Decimal("0") for nutrient in NUTRIENTS}
    normalized: list[dict[str, Any]] = []
    proxy_count = 0
    for item in ingredients:
        if not isinstance(item, dict):
            raise RecommendationError(f"option {option_id!r} has a non-object ingredient")
        ingredient = str(item.get("ingredient", "")).strip()
        unit = str(item.get("unit", "")).strip()
        quantity = D(item.get("quantity"), f"{ingredient or 'ingredient'} quantity")
        grams = D(
            item.get("nutrition_grams_total"),
            f"{ingredient or 'ingredient'} nutrition_grams_total",
        )
        match_type = str(item.get("nutrition_match_type", "exact")).strip().lower()
        match_note = str(item.get("nutrition_match_note") or "").strip()
        if not ingredient or not unit:
            raise RecommendationError("every ingredient needs ingredient and unit")
        if quantity <= 0 or grams <= 0:
            raise RecommendationError(f"ingredient {ingredient!r} quantities must be positive")
        if match_type not in {"exact", "proxy"}:
            raise RecommendationError(
                f"ingredient {ingredient!r} nutrition_match_type must be exact or proxy"
            )
        if match_type == "proxy" and not match_note:
            raise RecommendationError(f"proxy ingredient {ingredient!r} requires a note")
        if match_type == "proxy":
            proxy_count += 1
        record = resolve_record(item, db)
        factor = grams / record.serving_g
        nutrients = {key: value * factor for key, value in record.nutrients.items()}
        for key, value in nutrients.items():
            totals[key] += value
        normalized.append(
            {
                "ingredient": ingredient,
                "quantity": clean(quantity, 3),
                "unit": unit,
                "edible_grams": clean(grams, 3),
                "nutrition_row_id": record.row_id,
                "nutrition_name": record.name,
                "nutrition_match_type": match_type,
                "nutrition_match_note": match_note or None,
                "nutrition": {key: clean(value) for key, value in nutrients.items()},
            }
        )

    return {
        "id": option_id,
        "name": name,
        "kind": kind,
        "availability": availability,
        "planned_meal_id": planned_meal_id or None,
        "preparation": preparation,
        "ingredients": normalized,
        "nutrition_decimal": totals,
        "nutrition": {key: clean(value) for key, value in totals.items()},
        "proxy_count": proxy_count,
    }


def ratio(value: Decimal, denominator: Decimal) -> Decimal:
    return value / max(denominator, Decimal("1"))


def score_option(
    option: dict[str, Any],
    baseline: dict[str, Decimal],
    known: dict[str, Decimal],
) -> dict[str, Any]:
    option_nutrition: dict[str, Decimal] = option["nutrition_decimal"]
    projected = {key: known[key] + option_nutrition[key] for key in NUTRIENTS}
    remaining = {key: baseline[key] - projected[key] for key in NUTRIENTS}

    calorie_gap = abs(remaining["calories"])
    protein_under = max(remaining["protein_g"], Decimal("0"))
    protein_over = max(-remaining["protein_g"], Decimal("0"))
    carb_gap = abs(remaining["carbs_g"])
    fat_under = max(remaining["fat_g"], Decimal("0"))
    fat_over = max(-remaining["fat_g"], Decimal("0"))
    fiber_under = max(remaining["fiber_g"], Decimal("0"))
    sodium_over = max(-remaining["sodium_mg"], Decimal("0"))

    score = (
        ratio(calorie_gap, baseline["calories"]) * Decimal("30")
        + ratio(protein_under, baseline["protein_g"]) * Decimal("38")
        + ratio(protein_over, baseline["protein_g"]) * Decimal("4")
        + ratio(carb_gap, baseline["carbs_g"]) * Decimal("12")
        + ratio(fat_under, baseline["fat_g"]) * Decimal("3")
        + ratio(fat_over, baseline["fat_g"]) * Decimal("12")
        + ratio(fiber_under, baseline["fiber_g"]) * Decimal("8")
        + ratio(sodium_over, baseline["sodium_mg"]) * Decimal("8")
        + Decimal(ALLOWED_AVAILABILITY[option["availability"]])
        + Decimal(option["proxy_count"]) * Decimal("1.5")
    )

    result = {key: value for key, value in option.items() if key != "nutrition_decimal"}
    result.update(
        {
            "score": clean(score, 3),
            "projected_known_daily_total": {
                key: clean(value) for key, value in projected.items()
            },
            "remaining_vs_plan": {
                key: clean(value) for key, value in remaining.items()
            },
            "fiber_floor_gap": clean(fiber_under),
            "sodium_above_plan_reference": clean(sodium_over),
        }
    )
    return result


def compile_recommendation(payload: dict[str, Any], db: NutritionDatabase) -> dict[str, Any]:
    local_date = str(payload.get("local_date", "")).strip()
    as_of_local = str(payload.get("as_of_local", "")).strip()
    if not local_date or not as_of_local:
        raise RecommendationError("local_date and as_of_local are required")
    validate_local_date(local_date, as_of_local)

    target_source = payload.get("target_source")
    if not isinstance(target_source, dict):
        raise RecommendationError("target_source must be an object")
    required_source_fields = (
        "week_start",
        "compiled_plan_name",
        "compiled_plan_drive_id",
        "nutrition_csv_drive_id",
    )
    missing_source = [field for field in required_source_fields if not str(target_source.get(field, "")).strip()]
    if missing_source:
        raise RecommendationError(f"target_source missing fields: {missing_source}")

    baseline = nonnegative_nutrients(payload.get("planned_baseline"), "planned_baseline")
    for nutrient in ("calories", "protein_g", "carbs_g", "fat_g"):
        if baseline[nutrient] <= 0:
            raise RecommendationError(f"planned_baseline.{nutrient} must be positive")

    logged = payload.get("logged")
    if not isinstance(logged, dict):
        raise RecommendationError("logged must be an object")
    known = nonnegative_nutrients(logged.get("known_nutrition"), "logged.known_nutrition")
    unknown_items = logged.get("unknown_items", [])
    if not isinstance(unknown_items, list) or any(not isinstance(item, dict) for item in unknown_items):
        raise RecommendationError("logged.unknown_items must be a list of objects")
    for item in unknown_items:
        if not str(item.get("item", "")).strip() or not str(item.get("reason", "")).strip():
            raise RecommendationError("every unknown item needs item and reason")

    raw_options = payload.get("options")
    if not isinstance(raw_options, list) or not 1 <= len(raw_options) <= 3:
        raise RecommendationError("options must contain one to three entries")
    compiled_options = [compile_option(option, db) for option in raw_options]
    option_ids = [option["id"] for option in compiled_options]
    if len(option_ids) != len(set(option_ids)):
        raise RecommendationError("option IDs must be unique")

    ranked = sorted(
        (score_option(option, baseline, known) for option in compiled_options),
        key=lambda option: (Decimal(str(option["score"])), option["id"]),
    )
    current_remaining = {key: baseline[key] - known[key] for key in NUTRIENTS}
    status = "advisory_with_unknowns" if unknown_items else "validated"

    return {
        "status": status,
        "local_date": local_date,
        "as_of_local": as_of_local,
        "target_source": target_source,
        "planned_baseline": {key: clean(value) for key, value in baseline.items()},
        "logged_known_nutrition": {key: clean(value) for key, value in known.items()},
        "current_remaining_vs_plan": {
            key: clean(value) for key, value in current_remaining.items()
        },
        "unknown_items": unknown_items,
        "totals_are_lower_bounds": bool(unknown_items),
        "recommended_option_id": ranked[0]["id"],
        "ranked_options": ranked,
        "nutrition_database": {
            "sha256": db.sha256,
            "row_count": db.row_count,
            "drive_file_id": target_source["nutrition_csv_drive_id"],
        },
        "interpretation": {
            "fiber": "floor; values above plan are not penalized",
            "sodium": "upward reference only; values below plan are not a deficit",
            "medical_diagnosis": False,
            "authorizes_food_log_write": False,
            "authorizes_pantry_write": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--nutrition-csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.input_json.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RecommendationError("input JSON must be an object")
        config = payload.get("nutrition_database") or {}
        if not isinstance(config, dict):
            raise RecommendationError("nutrition_database must be an object")
        database = load_database(args.nutrition_csv, config)
        result = compile_recommendation(payload, database)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecommendationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
