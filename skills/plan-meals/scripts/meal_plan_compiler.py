#!/usr/bin/env python3
"""Deterministic nutrition-backed meal-plan and grocery-list compiler.

The compiler fails closed. It calculates meal nutrition only from quantified recipe
ingredients joined to an explicit row in a supplied nutrition CSV, then derives the
grocery list from the same ingredient records. Confirmed pantry inventory is
subtracted before package rounding. Manual meal macro estimates are not accepted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Any, Iterable

MASS_TO_G = {
    "g": Decimal("1"),
    "kg": Decimal("1000"),
    "oz": Decimal("28.349523125"),
    "lb": Decimal("453.59237"),
}
VOLUME_TO_ML = {
    "ml": Decimal("1"),
    "l": Decimal("1000"),
    "tsp": Decimal("4.92892159375"),
    "tbsp": Decimal("14.78676478125"),
    "cup": Decimal("236.5882365"),
}
COUNT_UNITS = {"count", "each", "can", "package", "slice", "scoop"}

NUTRIENT_COLUMNS = {
    "calories": ("calories",),
    "protein_g": ("protein [g]",),
    "carbs_g": ("carbohydrate [g]",),
    "fat_g": ("fat [g]", "total_fat [g]"),
    "fiber_g": ("fiber [g]",),
    "sodium_mg": ("sodium [mg]",),
}
PRIMARY_MACROS = ("calories", "protein_g", "carbs_g", "fat_g")
ALL_NUTRIENTS = tuple(NUTRIENT_COLUMNS)


class CompileError(ValueError):
    """Raised when the plan cannot be reconciled without guessing."""


def D(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise CompileError(f"Invalid numeric value: {value!r}") from exc


def parse_numeric(value: Any, *, field: str, row_label: str) -> Decimal:
    """Parse a numeric CSV cell, tolerating simple unit suffixes such as '6.2g'."""
    if value is None:
        raise CompileError(f"Nutrition row {row_label!r} is missing {field!r}")
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        raise CompileError(f"Nutrition row {row_label!r} has blank {field!r}")
    try:
        return Decimal(text)
    except InvalidOperation:
        match = re.fullmatch(r"\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*[a-zA-Z%]*\s*", text)
        if not match:
            raise CompileError(
                f"Nutrition row {row_label!r} has nonnumeric {field!r}: {value!r}"
            )
        return Decimal(match.group(1))


def clean_decimal(value: Decimal, places: int = 2) -> int | float:
    if value == value.to_integral():
        return int(value)
    quant = Decimal("1").scaleb(-places)
    out = value.quantize(quant)
    return int(out) if out == out.to_integral() else float(out)


def ceil_to_multiple(value: Decimal, multiple: Decimal) -> Decimal:
    if multiple <= 0:
        raise CompileError("Package size must be greater than zero")
    packs = (value / multiple).to_integral_value(rounding=ROUND_CEILING)
    return packs * multiple


@dataclass(frozen=True)
class CanonicalQuantity:
    amount: Decimal
    unit: str


@dataclass(frozen=True)
class NutritionRecord:
    row_id: str
    name: str
    serving_g: Decimal
    nutrients_per_serving: dict[str, Decimal]


@dataclass(frozen=True)
class NutritionDatabase:
    path: str
    sha256: str
    row_count: int
    id_column: str
    name_column: str
    serving_column: str
    by_id: dict[str, NutritionRecord]
    by_name: dict[str, list[NutritionRecord]]


def canonicalize_quantity(item: dict[str, Any]) -> CanonicalQuantity:
    """Convert one grocery quantity to g, ml, or count without inferred density."""
    if "quantity" not in item or "unit" not in item:
        raise CompileError("Every ingredient requires quantity and unit")
    amount = D(item["quantity"])
    unit = str(item["unit"]).strip().lower()
    if amount < 0:
        raise CompileError(f"Negative ingredient quantity for {item.get('ingredient')}")

    explicit_amount = item.get("canonical_amount_per_unit")
    explicit_unit = item.get("canonical_unit")
    if explicit_amount is not None or explicit_unit is not None:
        if explicit_amount is None or explicit_unit is None:
            raise CompileError(
                f"Both canonical_amount_per_unit and canonical_unit are required for "
                f"{item.get('ingredient')}"
            )
        canonical_unit = str(explicit_unit).strip().lower()
        if canonical_unit not in {"g", "ml", "count"}:
            raise CompileError(f"Unsupported canonical unit {canonical_unit!r}")
        return CanonicalQuantity(amount * D(explicit_amount), canonical_unit)

    if unit in MASS_TO_G:
        return CanonicalQuantity(amount * MASS_TO_G[unit], "g")
    if unit in VOLUME_TO_ML:
        return CanonicalQuantity(amount * VOLUME_TO_ML[unit], "ml")
    if unit in COUNT_UNITS:
        return CanonicalQuantity(amount, "count")
    raise CompileError(
        f"Unsupported or ambiguous unit {unit!r} for {item.get('ingredient')}. "
        "Provide canonical_amount_per_unit and canonical_unit."
    )


def nutrition_grams(item: dict[str, Any], grocery_qty: CanonicalQuantity) -> Decimal:
    """Return edible grams used for nutrient scaling; never infer density or piece mass."""
    if "nutrition_grams_total" in item:
        grams = D(item["nutrition_grams_total"])
    elif grocery_qty.unit == "g":
        grams = grocery_qty.amount
    elif "nutrition_grams_per_canonical_unit" in item:
        grams = grocery_qty.amount * D(item["nutrition_grams_per_canonical_unit"])
    else:
        raise CompileError(
            f"Ingredient {item.get('ingredient')!r} is measured in {grocery_qty.unit!r}; "
            "provide nutrition_grams_total or nutrition_grams_per_canonical_unit."
        )
    if grams < 0:
        raise CompileError(f"Negative nutrition grams for {item.get('ingredient')}")
    return grams


def canonical_name(item: dict[str, Any]) -> str:
    display = str(item.get("ingredient", "")).strip()
    canonical = str(item.get("canonical_name", display)).strip().lower()
    if not canonical:
        raise CompileError("Ingredient name cannot be empty")
    return canonical


def select_column(fieldnames: list[str], candidates: tuple[str, ...], label: str) -> str:
    for candidate in candidates:
        if candidate in fieldnames:
            return candidate
    raise CompileError(f"Nutrition CSV missing required {label} column; expected one of {candidates}")


def load_nutrition_database(path: Path, plan: dict[str, Any]) -> NutritionDatabase:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CompileError(f"Cannot read nutrition CSV: {path}") from exc
    sha256 = hashlib.sha256(raw).hexdigest()

    cfg = plan.get("nutrition_database", {})
    if cfg is not None and not isinstance(cfg, dict):
        raise CompileError("nutrition_database must be an object")
    cfg = cfg or {}
    expected_sha = str(cfg.get("expected_sha256", "")).strip().lower()
    if expected_sha and expected_sha != sha256:
        raise CompileError(
            f"Nutrition CSV SHA-256 mismatch: expected {expected_sha}, got {sha256}"
        )

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CompileError("Nutrition CSV must be UTF-8 or UTF-8 with BOM") from exc

    reader = csv.DictReader(text.splitlines())
    fieldnames = list(reader.fieldnames or [])
    if not fieldnames:
        raise CompileError("Nutrition CSV has no header")

    id_column = str(cfg.get("id_column", "Unnamed: 0"))
    name_column = str(cfg.get("name_column", "name"))
    serving_column = str(cfg.get("serving_column", "serving_size [g]"))
    for required in (id_column, name_column, serving_column):
        if required not in fieldnames:
            raise CompileError(f"Nutrition CSV missing required column: {required}")

    resolved_columns = {
        nutrient: select_column(fieldnames, candidates, nutrient)
        for nutrient, candidates in NUTRIENT_COLUMNS.items()
    }

    by_id: dict[str, NutritionRecord] = {}
    by_name: dict[str, list[NutritionRecord]] = defaultdict(list)
    row_count = 0
    for row in reader:
        row_count += 1
        row_id = str(row.get(id_column, "")).strip()
        name = str(row.get(name_column, "")).strip()
        if not row_id:
            raise CompileError(f"Nutrition CSV row {row_count + 1} has blank ID")
        if not name:
            raise CompileError(f"Nutrition CSV row ID {row_id} has blank name")
        if row_id in by_id:
            raise CompileError(f"Duplicate nutrition row ID: {row_id}")
        serving_g = parse_numeric(row.get(serving_column), field=serving_column, row_label=name)
        if serving_g <= 0:
            raise CompileError(f"Nutrition row {name!r} has nonpositive serving size")
        nutrients = {
            nutrient: parse_numeric(row.get(column), field=column, row_label=name)
            for nutrient, column in resolved_columns.items()
        }
        record = NutritionRecord(row_id, name, serving_g, nutrients)
        by_id[row_id] = record
        by_name[name.casefold()].append(record)

    if not row_count:
        raise CompileError("Nutrition CSV contains no data rows")

    return NutritionDatabase(
        path=str(path),
        sha256=sha256,
        row_count=row_count,
        id_column=id_column,
        name_column=name_column,
        serving_column=serving_column,
        by_id=by_id,
        by_name=dict(by_name),
    )


def resolve_nutrition_record(item: dict[str, Any], db: NutritionDatabase) -> NutritionRecord:
    raw_id = item.get("nutrition_row_id")
    raw_name = item.get("nutrition_name")
    if raw_id is None and raw_name is None:
        raise CompileError(
            f"Ingredient {item.get('ingredient')!r} requires nutrition_row_id or nutrition_name"
        )

    by_id: NutritionRecord | None = None
    by_name: NutritionRecord | None = None
    if raw_id is not None:
        row_id = str(raw_id).strip()
        by_id = db.by_id.get(row_id)
        if by_id is None:
            raise CompileError(
                f"Ingredient {item.get('ingredient')!r} references missing nutrition row ID {row_id!r}"
            )
    if raw_name is not None:
        name = str(raw_name).strip()
        matches = db.by_name.get(name.casefold(), [])
        if not matches:
            raise CompileError(
                f"Ingredient {item.get('ingredient')!r} references missing nutrition name {name!r}"
            )
        if len(matches) > 1:
            raise CompileError(
                f"Nutrition name {name!r} is not unique; use nutrition_row_id instead"
            )
        by_name = matches[0]
    if by_id is not None and by_name is not None and by_id.row_id != by_name.row_id:
        raise CompileError(
            f"Ingredient {item.get('ingredient')!r} nutrition_row_id and nutrition_name resolve "
            "to different rows"
        )
    return by_id or by_name  # type: ignore[return-value]


def validate_match_metadata(item: dict[str, Any]) -> tuple[str, str | None]:
    match_type = str(item.get("nutrition_match_type", "exact")).strip().lower()
    if match_type not in {"exact", "proxy"}:
        raise CompileError(
            f"Ingredient {item.get('ingredient')!r} nutrition_match_type must be exact or proxy"
        )
    note_raw = item.get("nutrition_match_note")
    note = str(note_raw).strip() if note_raw is not None else None
    if match_type == "proxy" and not note:
        raise CompileError(
            f"Ingredient {item.get('ingredient')!r} uses a nutrition proxy and requires "
            "nutrition_match_note"
        )
    return match_type, note


def scale_nutrients(record: NutritionRecord, grams: Decimal) -> dict[str, Decimal]:
    factor = grams / record.serving_g
    return {key: value * factor for key, value in record.nutrients_per_serving.items()}


def validate_top_level(plan: dict[str, Any]) -> None:
    if not isinstance(plan.get("meals"), list) or not plan["meals"]:
        raise CompileError("Plan must contain a non-empty meals list")
    if not isinstance(plan.get("packages", {}), dict):
        raise CompileError("packages must be an object keyed by canonical ingredient name")
    if not isinstance(plan.get("inventory", {}), dict):
        raise CompileError("inventory must be an object keyed by canonical ingredient name")


def compile_plan(plan: dict[str, Any], nutrition_db: NutritionDatabase) -> dict[str, Any]:
    validate_top_level(plan)

    meal_ids: set[str] = set()
    usage: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    ingredient_sources: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    daily_nutrients: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {nutrient: Decimal("0") for nutrient in ALL_NUTRIENTS}
    )
    meal_rows: list[dict[str, Any]] = []
    pantry_keys: set[tuple[str, str]] = set()
    proxy_matches: list[dict[str, Any]] = []

    for meal in plan["meals"]:
        if not isinstance(meal, dict):
            raise CompileError("Every meal must be an object")
        meal_id = str(meal.get("id", "")).strip()
        if not meal_id:
            raise CompileError("Every meal requires a unique id")
        if meal_id in meal_ids:
            raise CompileError(f"Duplicate meal id: {meal_id}")
        meal_ids.add(meal_id)

        date = str(meal.get("date", "")).strip()
        meal_name = str(meal.get("name", "")).strip()
        if not date or not meal_name:
            raise CompileError(f"Meal {meal_id} requires date and name")
        if "macros" in meal:
            raise CompileError(
                f"Meal {meal_id} contains manual macros. Nutrition must be computed from the CSV."
            )

        ingredients = meal.get("ingredients")
        if not isinstance(ingredients, list) or not ingredients:
            raise CompileError(f"Meal {meal_id} requires quantified ingredients")

        meal_nutrients = {nutrient: Decimal("0") for nutrient in ALL_NUTRIENTS}
        normalized_ingredients: list[dict[str, Any]] = []

        for item in ingredients:
            if not isinstance(item, dict):
                raise CompileError(f"Meal {meal_id}: every ingredient must be an object")
            name = canonical_name(item)
            display_name = str(item.get("ingredient", name)).strip()
            qty = canonicalize_quantity(item)
            grams = nutrition_grams(item, qty)
            record = resolve_nutrition_record(item, nutrition_db)
            match_type, match_note = validate_match_metadata(item)
            nutrients = scale_nutrients(record, grams)
            for nutrient, value in nutrients.items():
                meal_nutrients[nutrient] += value

            key = (name, qty.unit)
            pantry = bool(item.get("pantry_on_hand", False))
            if pantry:
                pantry_keys.add(key)
            else:
                usage[key] += qty.amount
                ingredient_sources[key].append(
                    {
                        "meal_id": meal_id,
                        "date": date,
                        "meal": meal_name,
                        "amount": clean_decimal(qty.amount, 3),
                    }
                )

            nutrition_source = {
                "row_id": record.row_id,
                "name": record.name,
                "match_type": match_type,
                "match_note": match_note,
                "grams_used": clean_decimal(grams, 3),
                "nutrients": {
                    key: clean_decimal(value, 2) for key, value in nutrients.items()
                },
            }
            if match_type == "proxy":
                proxy_matches.append(
                    {
                        "ingredient": display_name,
                        "canonical_name": name,
                        "nutrition_row_id": record.row_id,
                        "nutrition_name": record.name,
                        "note": match_note,
                    }
                )

            normalized_ingredients.append(
                {
                    "ingredient": display_name,
                    "canonical_name": name,
                    "planned_amount": clean_decimal(qty.amount, 3),
                    "unit": qty.unit,
                    "pantry_on_hand": pantry,
                    "nutrition_source": nutrition_source,
                }
            )

        for nutrient, value in meal_nutrients.items():
            daily_nutrients[date][nutrient] += value

        meal_rows.append(
            {
                "id": meal_id,
                "date": date,
                "name": meal_name,
                "nutrition": {
                    key: clean_decimal(value, 1) for key, value in meal_nutrients.items()
                },
                "ingredients": normalized_ingredients,
            }
        )

    packages = plan.get("packages", {})
    inventory_cfg = plan.get("inventory", {})
    inventory: dict[tuple[str, str], Decimal] = {}
    inventory_metadata: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_name, raw_config in inventory_cfg.items():
        if not isinstance(raw_config, dict):
            raise CompileError(f"Inventory entry for {raw_name!r} must be an object")
        name = str(raw_name).strip().lower()
        if not name:
            raise CompileError("Inventory ingredient name cannot be blank")
        unit = str(raw_config.get("canonical_unit", "")).strip().lower()
        if unit not in {"g", "ml", "count"}:
            raise CompileError(f"Inventory {name!r} has unsupported canonical unit {unit!r}")
        status = str(raw_config.get("status", "confirmed")).strip().lower()
        amount = D(raw_config.get("available_amount", raw_config.get("amount", 0)))
        if amount < 0:
            raise CompileError(f"Inventory {name!r} cannot be negative")
        if status not in {"confirmed", "projected"} and amount != 0:
            raise CompileError(
                f"Inventory {name!r} has {amount} {unit} but status is {status!r}; "
                "only confirmed or explicitly projected inventory may be subtracted"
            )
        key = (name, unit)
        if key in inventory:
            raise CompileError(f"Duplicate inventory entry for {name} in {unit}")
        inventory[key] = amount if status in {"confirmed", "projected"} else Decimal("0")
        inventory_metadata[key] = {
            "status": status,
            "last_confirmed": raw_config.get("last_confirmed"),
            "source": raw_config.get("source"),
        }

    produce_buffer_pct = D(plan.get("produce_buffer_pct", 0))
    if produce_buffer_pct < 0 or produce_buffer_pct > 5:
        raise CompileError("produce_buffer_pct must be between 0 and 5")

    grocery_rows: list[dict[str, Any]] = []
    inventory_rows: list[dict[str, Any]] = []
    for key in sorted(usage):
        name, unit = key
        exact = usage[key]
        available = inventory.get(key, Decimal("0"))
        inventory_used = min(exact, available)
        net_required = exact - inventory_used
        buy_amount = Decimal("0")
        pack_count = Decimal("0")
        package_size: Decimal | None = None
        buffer_pct = Decimal("0")
        category = "Other"
        purchase_label = name

        config = packages.get(name)
        if net_required > 0:
            if not isinstance(config, dict):
                raise CompileError(
                    f"Missing package metadata for grocery shortfall: {name} "
                    f"({clean_decimal(net_required, 3)} {unit})"
                )
            package_unit = str(config.get("canonical_unit", "")).strip().lower()
            if package_unit != unit:
                raise CompileError(
                    f"Package unit mismatch for {name}: recipes use {unit}, "
                    f"package uses {package_unit}"
                )
            package_size = D(config.get("package_size"))
            category = str(config.get("category", "Other")).strip() or "Other"
            purchase_label = str(config.get("purchase_label", name)).strip() or name
            is_loose_produce = bool(config.get("loose_produce", False))
            buffer_pct = produce_buffer_pct if is_loose_produce else Decimal("0")
            buffered_shortfall = net_required * (
                Decimal("1") + buffer_pct / Decimal("100")
            )
            buy_amount = ceil_to_multiple(buffered_shortfall, package_size)
            pack_count = buy_amount / package_size
            grocery_rows.append(
                {
                    "ingredient": name,
                    "purchase_label": purchase_label,
                    "category": category,
                    "unit": unit,
                    "planned_usage": clean_decimal(exact, 3),
                    "inventory_used": clean_decimal(inventory_used, 3),
                    "net_requirement": clean_decimal(net_required, 3),
                    "buffer_pct": clean_decimal(buffer_pct, 2),
                    "package_size": clean_decimal(package_size, 3),
                    "packages_to_buy": clean_decimal(pack_count, 0),
                    "amount_to_buy": clean_decimal(buy_amount, 3),
                    "package_excess_after_shortfall": clean_decimal(
                        buy_amount - net_required, 3
                    ),
                    "projected_inventory_after": clean_decimal(
                        available + buy_amount - exact, 3
                    ),
                    "used_in": ingredient_sources[key],
                }
            )

        projected_after = available + buy_amount - exact
        if projected_after < 0:
            raise CompileError(f"Inventory projection became negative for {name}")
        inventory_rows.append(
            {
                "ingredient": name,
                "unit": unit,
                "opening_confirmed": clean_decimal(available, 3),
                "planned_use": clean_decimal(exact, 3),
                "inventory_used": clean_decimal(inventory_used, 3),
                "planned_purchase": clean_decimal(buy_amount, 3),
                "projected_ending": clean_decimal(projected_after, 3),
                "inventory_metadata": inventory_metadata.get(key, {}),
                "used_in": ingredient_sources[key],
            }
        )

    for key in usage:
        recomputed = sum(
            (D(source["amount"]) for source in ingredient_sources[key]), Decimal("0")
        )
        if recomputed != usage[key]:
            raise CompileError(f"Internal reconciliation failed for {key[0]}")

    grocery_keys = {(row["ingredient"], row["unit"]) for row in grocery_rows}
    usage_keys = set(usage)
    if not grocery_keys.issubset(usage_keys):
        raise CompileError(f"Unmapped grocery items: {grocery_keys - usage_keys}")

    allocation_keys = {(row["ingredient"], row["unit"]) for row in inventory_rows}
    if allocation_keys != usage_keys:
        raise CompileError(
            f"Inventory allocation mismatch. Missing={usage_keys - allocation_keys}, "
            f"extra={allocation_keys - usage_keys}"
        )

    daily_totals = {
        date: {key: clean_decimal(value, 1) for key, value in nutrients.items()}
        for date, nutrients in sorted(daily_nutrients.items())
    }

    return {
        "status": "validated",
        "nutrition_database": {
            "path": nutrition_db.path,
            "sha256": nutrition_db.sha256,
            "row_count": nutrition_db.row_count,
            "drive_file_id": (plan.get("nutrition_database") or {}).get("drive_file_id"),
            "title": (plan.get("nutrition_database") or {}).get("title"),
            "serving_basis": "per row serving_size [g], scaled by explicit edible grams",
        },
        "meal_count": len(meal_rows),
        "meals": meal_rows,
        "daily_totals": daily_totals,
        "grocery_list": grocery_rows,
        "inventory_allocation": inventory_rows,
        "nutrition_proxy_matches": proxy_matches,
        "pantry_items_excluded": [
            {"ingredient": name, "unit": unit} for name, unit in sorted(pantry_keys)
        ],
        "validation": {
            "all_meals_have_quantified_ingredients": True,
            "all_ingredients_resolved_to_nutrition_csv": True,
            "all_meal_nutrition_computed_from_csv": True,
            "all_recipe_ingredients_reconciled": True,
            "no_unmapped_grocery_items": True,
            "inventory_subtracted_before_package_rounding": True,
            "inventory_usage_reconciled": True,
            "inventory_statuses_disclosed": True,
            "package_rounding_applied_after_exact_aggregation": True,
        },
    }


def render_markdown(compiled: dict[str, Any]) -> str:
    db = compiled["nutrition_database"]
    lines = [
        "# Validated Meal Plan Nutrition and Grocery Audit",
        "",
        f"Status: **{compiled['status']}**  ",
        f"Meals compiled: **{compiled['meal_count']}**  ",
        f"Nutrition rows available: **{db['row_count']}**  ",
        f"Nutrition CSV SHA-256: `{db['sha256']}`",
        "",
        "## Daily nutrition totals",
        "",
        "| Date | Calories | Protein (g) | Carbs (g) | Fat (g) | Fiber (g) | Sodium (mg) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for date, nutrients in compiled["daily_totals"].items():
        lines.append(
            f"| {date} | {nutrients['calories']} | {nutrients['protein_g']} | "
            f"{nutrients['carbs_g']} | {nutrients['fat_g']} | {nutrients['fiber_g']} | "
            f"{nutrients['sodium_mg']} |"
        )

    lines.extend(
        [
            "",
            "## Grocery list",
            "",
            "| Category | Purchase item | Recipe use | From inventory | Net need | Amount to buy | Projected ending |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in sorted(compiled["grocery_list"], key=lambda r: (r["category"], r["purchase_label"])):
        lines.append(
            f"| {row['category']} | {row['purchase_label']} | "
            f"{row['planned_usage']} {row['unit']} | {row['inventory_used']} {row['unit']} | "
            f"{row['net_requirement']} {row['unit']} | {row['amount_to_buy']} {row['unit']} | "
            f"{row['projected_inventory_after']} {row['unit']} |"
        )

    lines.extend(["", "## Pantry allocation", "",
        "| Ingredient | Opening | Planned use | Planned purchase | Projected ending |",
        "|---|---:|---:|---:|---:|"
    ])
    for row in compiled["inventory_allocation"]:
        lines.append(
            f"| {row['ingredient']} | {row['opening_confirmed']} {row['unit']} | "
            f"{row['planned_use']} {row['unit']} | {row['planned_purchase']} {row['unit']} | "
            f"{row['projected_ending']} {row['unit']} |"
        )

    lines.extend(["", "## Grocery trace", ""])
    for row in compiled["grocery_list"]:
        uses = ", ".join(
            f"{source['date']} {source['meal']} ({source['amount']} {row['unit']})"
            for source in row["used_in"]
        )
        lines.append(
            f"- **{row['purchase_label']}**: {row['planned_usage']} {row['unit']} total — {uses}."
        )

    if compiled["nutrition_proxy_matches"]:
        lines.extend(["", "## Nutrition proxy disclosures", ""])
        for proxy in compiled["nutrition_proxy_matches"]:
            lines.append(
                f"- **{proxy['ingredient']}** uses CSV row {proxy['nutrition_row_id']} "
                f"({proxy['nutrition_name']}): {proxy['note']}"
            )
    return "\n".join(lines) + "\n"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--nutrition-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-markdown", type=Path)
    args = parser.parse_args(argv)

    try:
        plan = json.loads(args.input_json.read_text(encoding="utf-8"))
        nutrition_db = load_nutrition_database(args.nutrition_csv, plan)
        compiled = compile_plan(plan, nutrition_db)
    except (OSError, json.JSONDecodeError, CompileError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    json_text = json.dumps(compiled, indent=2, ensure_ascii=False)
    markdown_text = render_markdown(compiled)
    if args.output_json:
        args.output_json.write_text(json_text + "\n", encoding="utf-8")
    else:
        print(json_text)
    if args.output_markdown:
        args.output_markdown.write_text(markdown_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
