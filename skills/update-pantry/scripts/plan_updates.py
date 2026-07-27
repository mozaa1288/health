#!/usr/bin/env python3
"""Validate pantry observations and produce a deterministic Sheets update plan."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any


VALID_SOURCES = {"receipt", "list", "photo", "statement"}
VALID_MODES = {"additive", "snapshot"}
VALID_STATES = {"exact", "unknown", "out"}
VALID_STATUSES = {"Confirmed", "Quantity unknown", "Unconfirmed", "Out", "Stale"}
ALLOWED_COLUMNS = set("ABCDEFHIJKLMN")
UNIT_DEFS = {
    "mg": ("mass", 0.001),
    "g": ("mass", 1.0),
    "kg": ("mass", 1000.0),
    "oz": ("mass", 28.349523125),
    "lb": ("mass", 453.59237),
    "ml": ("volume", 1.0),
    "l": ("volume", 1000.0),
    "fl oz": ("volume", 29.5735295625),
    "cup": ("volume", 236.5882365),
    "tbsp": ("volume", 14.78676478125),
    "tsp": ("volume", 4.92892159375),
    "count": ("count", 1.0),
    "each": ("count", 1.0),
    "ea": ("count", 1.0),
}


class PlanError(ValueError):
    """A user-resolvable validation error."""


def normalize_name(value: str) -> str:
    value = re.sub(r"[_\W]+", " ", value.casefold(), flags=re.UNICODE)
    return " ".join(value.split())


def normalized_unit(value: str) -> str:
    unit = value.strip().casefold().replace(".", "")
    aliases = {
        "grams": "g",
        "gram": "g",
        "kilograms": "kg",
        "kilogram": "kg",
        "ounces": "oz",
        "ounce": "oz",
        "pounds": "lb",
        "pound": "lb",
        "milliliters": "ml",
        "milliliter": "ml",
        "liters": "l",
        "liter": "l",
        "fluid ounce": "fl oz",
        "fluid ounces": "fl oz",
        "fl ounces": "fl oz",
        "cups": "cup",
        "tablespoon": "tbsp",
        "tablespoons": "tbsp",
        "teaspoon": "tsp",
        "teaspoons": "tsp",
        "counts": "count",
    }
    return aliases.get(unit, unit)


def convert_quantity(quantity: Any, source_unit: str, canonical_unit: str) -> float | int:
    if isinstance(quantity, bool) or not isinstance(quantity, (int, float)):
        raise PlanError("Exact quantity must be numeric")
    if not math.isfinite(float(quantity)) or quantity < 0:
        raise PlanError("Exact quantity must be finite and non-negative")
    source = normalized_unit(source_unit)
    target = normalized_unit(canonical_unit)
    if source not in UNIT_DEFS or target not in UNIT_DEFS:
        raise PlanError(f"Unsupported unit conversion: {source_unit!r} to {canonical_unit!r}")
    source_dimension, source_factor = UNIT_DEFS[source]
    target_dimension, target_factor = UNIT_DEFS[target]
    if source_dimension != target_dimension:
        raise PlanError(
            f"Incompatible unit dimensions: {source_unit!r} cannot convert to {canonical_unit!r}"
        )
    converted = round(float(quantity) * source_factor / target_factor, 3)
    if target_dimension == "count":
        if not converted.is_integer():
            raise PlanError("Count quantities must resolve to a whole number")
        return int(converted)
    return converted


def parse_iso_date(value: Any, label: str) -> date:
    if not isinstance(value, str) or not value:
        raise PlanError(f"{label} must be an ISO date string")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise PlanError(f"{label} must be an ISO date string") from exc


def append_text(existing: Any, addition: str) -> str:
    base = str(existing or "").strip()
    return f"{base} {addition}".strip()


def is_recent_confirmed(row: dict[str, Any], as_of: date) -> bool:
    if row.get("status") != "Confirmed":
        return False
    quantity = row.get("confirmed_on_hand")
    if isinstance(quantity, bool) or not isinstance(quantity, (int, float)):
        return False
    try:
        confirmed = parse_iso_date(row.get("last_confirmed"), "last_confirmed")
    except PlanError:
        return False
    age = (as_of - confirmed).days
    return 0 <= age <= 14


def validate_inventory(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    by_row: dict[int, dict[str, Any]] = {}
    for row in rows:
        number = row.get("row_number")
        if not isinstance(number, int) or number < 10:
            raise PlanError("Each inventory row must have an integer row_number of at least 10")
        if number in by_row:
            raise PlanError(f"Duplicate inventory row_number: {number}")
        if not str(row.get("item") or "").strip():
            raise PlanError(f"Inventory row {number} is missing item")
        if row.get("status") not in VALID_STATUSES:
            raise PlanError(f"Inventory row {number} has invalid status")
        by_row[number] = deepcopy(row)
    return by_row


def dedupe_observations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_ids: set[str] = set()
    keyed: dict[str, dict[str, Any]] = {}
    output: list[dict[str, Any]] = []
    for raw in observations:
        observation = deepcopy(raw)
        observation_id = str(observation.get("observation_id") or "").strip()
        if not observation_id or observation_id in seen_ids:
            raise PlanError("Each observation_id must be non-empty and unique")
        seen_ids.add(observation_id)
        key = str(observation.get("dedupe_key") or "").strip()
        if not key:
            output.append(observation)
            continue
        if key not in keyed:
            keyed[key] = observation
            output.append(observation)
            continue
        prior = keyed[key]
        comparable = ("observed_name", "quantity_state", "quantity", "unit", "target_row")
        if any(prior.get(field) != observation.get(field) for field in comparable):
            raise PlanError(f"Conflicting overlapping observations for dedupe_key {key!r}")
        refs = list(dict.fromkeys((prior.get("evidence_refs") or []) + (observation.get("evidence_refs") or [])))
        prior["evidence_refs"] = refs
    return output


def find_target(
    observation: dict[str, Any],
    rows_by_number: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    candidates = observation.get("match_candidates") or []
    if len(candidates) > 1:
        raise PlanError(
            f"Observation {observation['observation_id']} has ambiguous match candidates: {candidates}"
        )
    target_row = observation.get("target_row")
    if target_row is not None:
        if not isinstance(target_row, int) or target_row not in rows_by_number:
            raise PlanError(f"Target row {target_row!r} does not exist")
        if candidates and candidates[0] != target_row:
            raise PlanError("target_row conflicts with match_candidates")
        return rows_by_number[target_row]
    if len(candidates) == 1:
        candidate = candidates[0]
        if candidate not in rows_by_number:
            raise PlanError(f"Match candidate row {candidate!r} does not exist")
        return rows_by_number[candidate]

    wanted = normalize_name(str(observation["observed_name"]))
    matches = [
        row
        for row in rows_by_number.values()
        if wanted in {
            normalize_name(str(row.get("item") or "")),
            normalize_name(str(row.get("nutrition_map_key") or "")),
        }
    ]
    if len(matches) > 1:
        raise PlanError(
            f"Observation {observation['observation_id']} matches multiple inventory rows"
        )
    if matches:
        return matches[0]
    if observation.get("allow_new") is True:
        return None
    raise PlanError(
        f"Observation {observation['observation_id']} did not match an existing row; "
        "set allow_new only after confirming it is distinct"
    )


def provenance(capture: dict[str, Any], observation: dict[str, Any]) -> str:
    reason = str(observation.get("match_reason") or "captured observation").strip()
    return (
        f"[capture:{capture['capture_id']}] {capture['source_type']}; "
        f"{observation['quantity_state']}; {reason}"
    )


def plan_existing(
    capture: dict[str, Any],
    observation: dict[str, Any],
    row: dict[str, Any],
    as_of: date,
) -> tuple[dict[str, Any], list[str]]:
    state = observation["quantity_state"]
    mode = capture["mode"]
    write: dict[str, Any] = {}
    warnings: list[str] = []
    package = str(observation.get("package_notes") or "").strip()
    if package:
        write["M"] = append_text(row.get("package_notes"), package)
    note = provenance(capture, observation)

    if state == "exact":
        canonical = str(row.get("canonical_unit") or "").strip()
        if not canonical:
            raise PlanError(f"Inventory row {row['row_number']} has no canonical unit")
        amount = convert_quantity(observation.get("quantity"), str(observation.get("unit") or ""), canonical)
        if mode == "additive" and is_recent_confirmed(row, as_of):
            amount = round(float(row.get("confirmed_on_hand", 0)) + float(amount), 3)
            if normalized_unit(canonical) == "count":
                amount = int(amount)
        elif mode == "additive":
            note += "; confirmed minimum—prior unconfirmed or stale stock excluded"
            warnings.append(f"{row['item']}: confirmed minimum from additive capture")
        write.update({"E": amount, "I": "Confirmed", "J": as_of.isoformat()})
    elif state == "unknown":
        if mode == "snapshot":
            write.update({"E": 0, "I": "Quantity unknown", "J": None})
        elif is_recent_confirmed(row, as_of):
            warnings.append(f"{row['item']}: kept recent confirmed quantity; new amount unknown")
        else:
            write.update({"E": 0, "I": "Quantity unknown", "J": None})
    elif state == "out":
        if mode != "snapshot":
            raise PlanError("Out observations require snapshot mode")
        write.update({"E": 0, "I": "Out", "J": as_of.isoformat()})

    if observation.get("use_first_by"):
        parse_iso_date(observation["use_first_by"], "use_first_by")
        write["K"] = observation["use_first_by"]
    write["N"] = append_text(row.get("notes"), note)
    if "G" in write or not set(write).issubset(ALLOWED_COLUMNS):
        raise PlanError("Planner attempted to write a protected or unsupported column")
    return {
        "action": "update",
        "row_number": row["row_number"],
        "item": row["item"],
        "write_cells": write,
    }, warnings


def plan_new(
    capture: dict[str, Any],
    observation: dict[str, Any],
    row_number: int,
    as_of: date,
) -> tuple[dict[str, Any], list[str]]:
    for field in ("category", "storage", "canonical_unit"):
        if not str(observation.get(field) or "").strip():
            raise PlanError(f"New item {observation['observed_name']!r} requires {field}")
    state = observation["quantity_state"]
    if state == "out":
        raise PlanError("Do not create a new inventory row only to mark it out")
    canonical = normalized_unit(str(observation["canonical_unit"]))
    if canonical not in {"g", "ml", "count"}:
        raise PlanError("New item canonical_unit must be g, ml, or count")
    if state == "exact":
        amount = convert_quantity(observation.get("quantity"), str(observation.get("unit") or ""), canonical)
        status = "Confirmed"
        confirmed_date: str | None = as_of.isoformat()
    else:
        amount = 0
        status = "Quantity unknown"
        confirmed_date = None
    note = provenance(capture, observation)
    if not str(observation.get("nutrition_map_key") or "").strip():
        note += "; nutrition map unmapped"
    write = {
        "A": str(observation["observed_name"]).strip(),
        "B": str(observation["category"]).strip(),
        "C": str(observation["storage"]).strip(),
        "D": canonical,
        "E": amount,
        "F": 0,
        "H": str(observation.get("typical_staple") or "No").strip(),
        "I": status,
        "J": confirmed_date,
        "K": observation.get("use_first_by"),
        "L": str(observation.get("nutrition_map_key") or "").strip(),
        "M": str(observation.get("package_notes") or "").strip(),
        "N": note,
    }
    if write["K"]:
        parse_iso_date(write["K"], "use_first_by")
    if "G" in write or not set(write).issubset(ALLOWED_COLUMNS):
        raise PlanError("Planner attempted to write a protected or unsupported column")
    warnings = []
    if state == "unknown":
        warnings.append(f"{write['A']}: added with quantity unknown")
    return {
        "action": "add",
        "row_number": row_number,
        "item": write["A"],
        "write_cells": write,
        "formula_g": (
            f'=IF(AND(I{row_number}="Confirmed",J{row_number}<>"",'
            f"TODAY()-J{row_number}<=14),MAX(E{row_number}-F{row_number},0),0)"
        ),
    }, warnings


def build_plan(document: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise PlanError("Input must be a JSON object")
    capture = document.get("capture")
    inventory = document.get("inventory")
    if not isinstance(capture, dict) or not isinstance(inventory, dict):
        raise PlanError("Input requires capture and inventory objects")
    capture_id = str(capture.get("capture_id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,119}", capture_id):
        raise PlanError("capture_id must be 8-120 safe characters")
    if capture.get("source_type") not in VALID_SOURCES:
        raise PlanError(f"source_type must be one of {sorted(VALID_SOURCES)}")
    if capture.get("mode") not in VALID_MODES:
        raise PlanError(f"mode must be one of {sorted(VALID_MODES)}")
    try:
        datetime.fromisoformat(str(capture.get("captured_at") or ""))
    except ValueError as exc:
        raise PlanError("captured_at must be an ISO-8601 timestamp") from exc
    as_of = parse_iso_date(inventory.get("as_of"), "inventory.as_of")
    rows = inventory.get("rows")
    if not isinstance(rows, list):
        raise PlanError("inventory.rows must be a list")
    rows_by_number = validate_inventory(rows)
    marker = f"[capture:{capture_id}]"
    for row in rows_by_number.values():
        if marker in str(row.get("notes") or "") or marker in str(row.get("package_notes") or ""):
            raise PlanError(f"Duplicate capture_id already applied: {capture_id}")

    observations = capture.get("observations")
    if not isinstance(observations, list) or not observations:
        raise PlanError("capture.observations must be a non-empty list")
    observations = dedupe_observations(observations)
    next_row = max(rows_by_number, default=9) + 1
    operations: list[dict[str, Any]] = []
    warnings: list[str] = []
    targeted_rows: set[int] = set()

    for observation in observations:
        name = str(observation.get("observed_name") or "").strip()
        if not name:
            raise PlanError("Each observation requires observed_name")
        state = observation.get("quantity_state")
        if state not in VALID_STATES:
            raise PlanError(f"Invalid quantity_state for {name!r}")
        confidence = observation.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise PlanError(f"Observation {name!r} requires numeric confidence")
        if not 0 <= float(confidence) <= 1:
            raise PlanError(f"Observation {name!r} confidence must be from 0 through 1")
        if float(confidence) < 0.75:
            raise PlanError(f"Observation {name!r} is below the 0.75 confidence threshold")
        if state == "exact" and ("quantity" not in observation or not observation.get("unit")):
            raise PlanError(f"Exact observation {name!r} requires quantity and unit")
        target = find_target(observation, rows_by_number)
        if target is not None:
            if target["row_number"] in targeted_rows:
                raise PlanError(
                    f"Multiple observations target row {target['row_number']}; combine them before planning"
                )
            targeted_rows.add(target["row_number"])
            operation, op_warnings = plan_existing(capture, observation, target, as_of)
        else:
            operation, op_warnings = plan_new(capture, observation, next_row, as_of)
            next_row += 1
        operations.append(operation)
        warnings.extend(op_warnings)

    summary = {
        "updated": sum(op["action"] == "update" for op in operations),
        "added": sum(op["action"] == "add" for op in operations),
        "quantity_unknown": sum(
            op["write_cells"].get("I") == "Quantity unknown" for op in operations
        ),
    }
    return {
        "capture_id": capture_id,
        "status": "ready",
        "operations": operations,
        "summary": summary,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Capture and current-inventory JSON")
    parser.add_argument("--output", type=Path, help="Write the plan to this JSON file")
    args = parser.parse_args()
    try:
        document = json.loads(args.input.read_text(encoding="utf-8"))
        plan = build_plan(document)
    except (OSError, json.JSONDecodeError, PlanError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    rendered = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
