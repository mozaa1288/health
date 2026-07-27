#!/usr/bin/env python3
"""Build a conservative reconciliation plan for food-consumption evidence."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "food-log-reconciliation-plan/v1"
MEALS = {"Breakfast", "Lunch", "Dinner", "Snack", "Other"}
REQUIRED_ROW_FIELDS = {
    "Entry ID",
    "Item ID",
    "Local Date",
    "Meal",
    "Description",
    "Item",
    "Quantity",
    "Unit",
    "Original Text",
    "Status",
}
TOKEN_RE = re.compile(r"[a-z0-9]+")


class ReconciliationError(ValueError):
    """Raised when reconciliation input violates the contract."""


def require_string(value: Any, field: str, *, allow_blank: bool = False) -> str:
    if not isinstance(value, str):
        raise ReconciliationError(f"{field} must be a string")
    if not allow_blank and not value.strip():
        raise ReconciliationError(f"{field} must be nonblank")
    return value


def parse_date(value: Any, field: str) -> str:
    text = require_string(value, field)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ReconciliationError(f"{field} must use YYYY-MM-DD") from exc
    if parsed.isoformat() != text:
        raise ReconciliationError(f"{field} must use YYYY-MM-DD")
    return text


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return " ".join(TOKEN_RE.findall(text))


def normalized_tokens(*values: Any) -> set[str]:
    return set(TOKEN_RE.findall(" ".join(normalize_text(value) for value in values)))


def normalize_quantity(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number <= 0:
        return None
    rendered = format(number.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def item_signature(items: list[dict[str, Any]]) -> tuple[tuple[str, str, str], ...] | None:
    signature: list[tuple[str, str, str]] = []
    for item in items:
        name = normalize_text(item.get("item"))
        quantity = normalize_quantity(item.get("quantity"))
        unit = normalize_text(item.get("unit"))
        if not name or quantity is None or not unit:
            return None
        signature.append((name, quantity, unit))
    if not signature:
        return None
    return tuple(sorted(signature))


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconciliationError(f"cannot read valid JSON from {path}") from exc


def validate_candidates(source: Any) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(source, dict):
        raise ReconciliationError("candidate input must be an object")
    target_date = parse_date(source.get("target_date"), "target_date")
    candidates = source.get("candidates")
    if not isinstance(candidates, list):
        raise ReconciliationError("candidates must be an array")

    seen_ids: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        field = f"candidates[{index}]"
        if not isinstance(candidate, dict):
            raise ReconciliationError(f"{field} must be an object")
        candidate_id = require_string(candidate.get("candidate_id"), f"{field}.candidate_id")
        if candidate_id in seen_ids:
            raise ReconciliationError(f"duplicate candidate_id {candidate_id!r}")
        seen_ids.add(candidate_id)
        if not isinstance(candidate.get("explicit_consumption"), bool):
            raise ReconciliationError(f"{field}.explicit_consumption must be a boolean")
        parse_date(candidate.get("consumed_local_date"), f"{field}.consumed_local_date")
        meal = require_string(candidate.get("meal"), f"{field}.meal")
        if meal not in MEALS:
            raise ReconciliationError(f"{field}.meal must be one of {sorted(MEALS)}")
        require_string(candidate.get("description"), f"{field}.description", allow_blank=True)
        require_string(candidate.get("original_text"), f"{field}.original_text", allow_blank=True)
        source_message_ref = candidate.get("source_message_ref")
        if source_message_ref not in (None, ""):
            require_string(source_message_ref, f"{field}.source_message_ref")
        source_timestamp = candidate.get("source_timestamp")
        if source_timestamp not in (None, ""):
            timestamp = require_string(source_timestamp, f"{field}.source_timestamp")
            try:
                parsed_timestamp = datetime.fromisoformat(
                    timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
                )
            except ValueError as exc:
                raise ReconciliationError(
                    f"{field}.source_timestamp must be ISO-8601"
                ) from exc
            if parsed_timestamp.utcoffset() is None:
                raise ReconciliationError(
                    f"{field}.source_timestamp must include a UTC offset"
                )
        if source_message_ref in (None, "") and source_timestamp in (None, ""):
            raise ReconciliationError(
                f"{field} requires source_message_ref or source_timestamp"
            )
        for flag in ("requires_configuration", "configuration_complete"):
            if not isinstance(candidate.get(flag), bool):
                raise ReconciliationError(f"{field}.{flag} must be a boolean")
        items = candidate.get("items")
        if not isinstance(items, list):
            raise ReconciliationError(f"{field}.items must be an array")
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ReconciliationError(
                    f"{field}.items[{item_index}] must be an object"
                )
        validated.append(candidate)
    return target_date, validated


def validate_rows(source: Any) -> list[dict[str, Any]]:
    rows = source.get("rows") if isinstance(source, dict) else source
    if not isinstance(rows, list):
        raise ReconciliationError("food-log rows must be an array or an object with rows")
    validated: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ReconciliationError(f"food-log row {index} must be an object")
        missing = REQUIRED_ROW_FIELDS - set(row)
        if missing:
            raise ReconciliationError(
                f"food-log row {index} is missing fields: {', '.join(sorted(missing))}"
            )
        require_string(row["Entry ID"], f"food-log row {index}.Entry ID")
        parse_date(row["Local Date"], f"food-log row {index}.Local Date")
        status = require_string(row["Status"], f"food-log row {index}.Status")
        if status not in {"Active", "Deleted"}:
            raise ReconciliationError(
                f"food-log row {index}.Status must be Active or Deleted"
            )
        validated.append(row)
    return validated


def group_entries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["Entry ID"])].append(row)

    entries: list[dict[str, Any]] = []
    for entry_id, entry_rows in grouped.items():
        first = entry_rows[0]
        statuses = {str(row["Status"]) for row in entry_rows}
        if len(statuses) != 1:
            raise ReconciliationError(
                f"entry {entry_id!r} mixes Active and Deleted rows"
            )
        items = [
            {
                "item": row["Item"],
                "quantity": row["Quantity"],
                "unit": row["Unit"],
            }
            for row in entry_rows
        ]
        entries.append(
            {
                "entry_id": entry_id,
                "status": statuses.pop(),
                "local_date": str(first["Local Date"]),
                "meal": str(first["Meal"]),
                "description": str(first["Description"]),
                "original_texts": {
                    normalize_text(row["Original Text"])
                    for row in entry_rows
                    if normalize_text(row["Original Text"])
                },
                "item_signature": item_signature(items),
                "tokens": normalized_tokens(
                    first["Description"],
                    *(row["Item"] for row in entry_rows),
                    *(row["Original Text"] for row in entry_rows),
                ),
            }
        )
    return entries


def classify_candidate(
    candidate: dict[str, Any],
    target_date: str,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate_id = candidate["candidate_id"]
    base = {
        "candidate_id": candidate_id,
        "classification": "",
        "reason": "",
        "possible_entry_ids": [],
        "candidate": candidate,
    }

    if not candidate["explicit_consumption"]:
        return {
            **base,
            "classification": "ignored",
            "reason": "not direct user-authored consumption evidence",
        }
    if candidate["consumed_local_date"] != target_date:
        return {
            **base,
            "classification": "ignored",
            "reason": "consumption date is outside the target date",
        }

    description = normalize_text(candidate["description"])
    original_text = normalize_text(candidate["original_text"])
    signature = item_signature(candidate["items"])
    if not description or not original_text:
        return {
            **base,
            "classification": "needs_clarification",
            "reason": "description or original consumption wording is missing",
        }
    if candidate["requires_configuration"] and not candidate["configuration_complete"]:
        return {
            **base,
            "classification": "needs_clarification",
            "reason": "configurable food build is incomplete",
        }
    if signature is None:
        return {
            **base,
            "classification": "needs_clarification",
            "reason": "one or more items lack a positive quantity or unit",
        }

    same_date = [entry for entry in entries if entry["local_date"] == target_date]
    active_same_date = [entry for entry in same_date if entry["status"] == "Active"]
    deleted_same_date = [entry for entry in same_date if entry["status"] == "Deleted"]
    original_matches = [
        entry for entry in active_same_date if original_text in entry["original_texts"]
    ]
    if original_matches:
        return {
            **base,
            "classification": "already_logged",
            "reason": "original text matches an active entry",
            "possible_entry_ids": sorted(entry["entry_id"] for entry in original_matches),
        }

    exact_signature_matches = [
        entry
        for entry in active_same_date
        if entry["meal"] == candidate["meal"] and entry["item_signature"] == signature
    ]
    if exact_signature_matches:
        return {
            **base,
            "classification": "already_logged",
            "reason": "meal and complete item signature match an active entry",
            "possible_entry_ids": sorted(
                entry["entry_id"] for entry in exact_signature_matches
            ),
        }

    deleted_matches = [
        entry
        for entry in deleted_same_date
        if original_text in entry["original_texts"]
        or (
            entry["meal"] == candidate["meal"]
            and entry["item_signature"] == signature
        )
    ]
    if deleted_matches:
        return {
            **base,
            "classification": "ambiguous_match",
            "reason": "an exact matching historical entry is marked Deleted",
            "possible_entry_ids": sorted(
                entry["entry_id"] for entry in deleted_matches
            ),
        }

    candidate_tokens = normalized_tokens(
        candidate["description"],
        candidate["original_text"],
        *(item["item"] for item in candidate["items"]),
    )
    possible: list[str] = []
    for entry in active_same_date:
        if entry["meal"] != candidate["meal"]:
            continue
        if normalize_text(entry["description"]) == description:
            possible.append(entry["entry_id"])
            continue
        union = candidate_tokens | entry["tokens"]
        overlap = len(candidate_tokens & entry["tokens"]) / len(union) if union else 0.0
        if overlap >= 0.5:
            possible.append(entry["entry_id"])
    if possible:
        return {
            **base,
            "classification": "ambiguous_match",
            "reason": "a similar active entry exists but the evidence is not an exact match",
            "possible_entry_ids": sorted(set(possible)),
        }

    return {
        **base,
        "classification": "missing",
        "reason": "no matching active entry exists on the target date",
    }


def build_plan(candidate_source: Any, row_source: Any) -> dict[str, Any]:
    target_date, candidates = validate_candidates(candidate_source)
    rows = validate_rows(row_source)
    entries = group_entries(rows)
    results = [
        classify_candidate(candidate, target_date, entries) for candidate in candidates
    ]
    counts = Counter(result["classification"] for result in results)
    summary = {
        classification: counts.get(classification, 0)
        for classification in (
            "already_logged",
            "missing",
            "needs_clarification",
            "ambiguous_match",
            "ignored",
        )
    }
    return {
        "schema": SCHEMA_VERSION,
        "target_date": target_date,
        "summary": summary,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify food evidence against active Food Log entries."
    )
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--food-log-rows", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    try:
        plan = build_plan(load_json(args.candidates), load_json(args.food_log_rows))
        encoded = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
        json.loads(encoded)
        args.output.write_text(encoded, encoding="utf-8")
        with args.output.open("r", encoding="utf-8") as handle:
            written = json.load(handle)
        if written.get("schema") != SCHEMA_VERSION:
            raise ReconciliationError("written output failed schema verification")
    except ReconciliationError as exc:
        parser.error(str(exc))

    print(json.dumps({"status": "ok", **plan["summary"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
