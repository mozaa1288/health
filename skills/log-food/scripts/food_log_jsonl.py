#!/usr/bin/env python3
"""Append, read, summarize, and validate daily JSONL food logs."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "food_log.meal.v1"
FILE_NAME = re.compile(r"food-log-(\d{4}-\d{2}-\d{2})\.jsonl$")
CORE_NUTRIENTS = ("calories", "protein_g", "carbs_g", "fat_g")
ALL_NUTRIENTS = CORE_NUTRIENTS + ("fiber_g", "sodium_mg")


class FoodLogError(ValueError):
    pass


def _iso_timestamp(value: Any, label: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise FoodLogError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FoodLogError(f"{label} must include a UTC offset")
    return text


def validate_record(record: Any, expected_date: str | None = None) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise FoodLogError("every JSONL line must be a JSON object")
    if record.get("schema_version") != SCHEMA_VERSION:
        raise FoodLogError(f"schema_version must be {SCHEMA_VERSION!r}")
    if record.get("record_type") != "meal":
        raise FoodLogError("record_type must be 'meal'")

    entry_id = str(record.get("entry_id") or "").strip()
    local_date = str(record.get("local_date") or "").strip()
    if not entry_id:
        raise FoodLogError("entry_id cannot be blank")
    try:
        datetime.strptime(local_date, "%Y-%m-%d")
    except ValueError as exc:
        raise FoodLogError("local_date must be YYYY-MM-DD") from exc
    if expected_date and local_date != expected_date:
        raise FoodLogError(
            f"record date {local_date} does not match daily file date {expected_date}"
        )

    logged_at = _iso_timestamp(record.get("logged_at"), "logged_at")
    if datetime.fromisoformat(logged_at).date().isoformat() != local_date:
        raise FoodLogError("logged_at and local_date disagree")
    _iso_timestamp(record.get("last_updated"), "last_updated")

    revision = record.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise FoodLogError("revision must be a positive integer")
    status = record.get("status")
    if status not in {"Active", "Deleted"}:
        raise FoodLogError("status must be Active or Deleted")
    if record.get("meal") not in {"Breakfast", "Lunch", "Dinner", "Snack", "Other"}:
        raise FoodLogError("meal has an unsupported value")
    if not str(record.get("description") or "").strip():
        raise FoodLogError("description cannot be blank")

    items = record.get("items")
    if not isinstance(items, list) or not items:
        raise FoodLogError("items must be a non-empty list")
    item_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise FoodLogError("every item must be an object")
        item_id = str(item.get("item_id") or "").strip()
        if not item_id or item_id in item_ids:
            raise FoodLogError("item_id values must be nonblank and unique within a meal")
        item_ids.add(item_id)
        if not str(item.get("item") or "").strip():
            raise FoodLogError("item name cannot be blank")
        if item.get("quantity") is None or not str(item.get("unit") or "").strip():
            raise FoodLogError("every item needs quantity and unit")
        nutrition = item.get("nutrition")
        if not isinstance(nutrition, dict):
            raise FoodLogError("every item needs a nutrition object")
        for field in ALL_NUTRIENTS:
            value = nutrition.get(field)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
            ):
                raise FoodLogError(f"{field} must be a nonnegative number or null")

    for field in ("totals", "known_nutrition_subtotal"):
        values = record.get(field)
        if not isinstance(values, dict):
            raise FoodLogError(f"{field} must be an object")
        for nutrient in ALL_NUTRIENTS:
            value = values.get(nutrient)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
            ):
                raise FoodLogError(
                    f"{field}.{nutrient} must be a nonnegative number or null"
                )
    return record


def file_date(path: Path) -> str:
    match = FILE_NAME.fullmatch(path.name)
    if not match:
        raise FoodLogError("daily log must be named food-log-YYYY-MM-DD.jsonl")
    return match.group(1)


def read_records(path: Path) -> list[dict[str, Any]]:
    expected_date = file_date(path)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    revisions: dict[str, int] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            raise FoodLogError(f"blank line at {path.name}:{line_number}")
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FoodLogError(f"invalid JSON at {path.name}:{line_number}: {exc}") from exc
        validate_record(record, expected_date)
        entry_id = record["entry_id"]
        expected_revision = revisions.get(entry_id, 0) + 1
        if record["revision"] != expected_revision:
            raise FoodLogError(
                f"{entry_id!r} revision must be {expected_revision}, "
                f"got {record['revision']}"
            )
        revisions[entry_id] = expected_revision
        records.append(record)
    return records


def current_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    current: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in records:
        entry_id = record["entry_id"]
        if entry_id not in current:
            order.append(entry_id)
        current[entry_id] = record
    return [current[entry_id] for entry_id in order if current[entry_id]["status"] == "Active"]


def _comparable(record: dict[str, Any]) -> dict[str, Any]:
    result = dict(record)
    result.pop("revision", None)
    result.pop("last_updated", None)
    return result


def append_record(
    path: Path, record: dict[str, Any], *, correction: bool = False
) -> dict[str, Any]:
    expected_date = file_date(path)
    records = read_records(path)
    prior = [row for row in records if row["entry_id"] == record.get("entry_id")]
    candidate = dict(record)
    candidate["revision"] = len(prior) + 1
    validate_record(candidate, expected_date)

    if prior and _comparable(prior[-1]) == _comparable(candidate):
        return {"result": "duplicate", "record": prior[-1]}
    if prior and not correction:
        raise FoodLogError(
            "entry_id already exists with different content; use --correction to append a revision"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(candidate, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        written = os.write(descriptor, encoded)
        if written != len(encoded):
            raise OSError("short JSONL append")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return {"result": "corrected" if prior else "appended", "record": candidate}


def delete_entry(path: Path, entry_id: str, updated_at: str) -> dict[str, Any]:
    records = read_records(path)
    prior = [row for row in records if row["entry_id"] == entry_id]
    if not prior:
        raise FoodLogError(f"entry_id not found: {entry_id}")
    if prior[-1]["status"] == "Deleted":
        return {"result": "duplicate", "record": prior[-1]}
    tombstone = dict(prior[-1])
    tombstone["status"] = "Deleted"
    tombstone["last_updated"] = _iso_timestamp(updated_at, "updated_at")
    return append_record(path, tombstone, correction=True)


def summarize(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    active = current_records(records)
    totals: dict[str, float] = {name: 0.0 for name in ALL_NUTRIENTS}
    unknown: set[str] = set()
    for record in active:
        for nutrient in ALL_NUTRIENTS:
            value = record["totals"].get(nutrient)
            if value is None:
                unknown.add(nutrient)
            else:
                totals[nutrient] += float(value)
    return {
        "meal_count": len(active),
        "totals": {
            nutrient: None if nutrient in unknown else round(value, 2)
            for nutrient, value in totals.items()
        },
        "known_nutrition_subtotal": {
            nutrient: round(
                sum(
                    float(record["known_nutrition_subtotal"].get(nutrient) or 0)
                    for record in active
                ),
                2,
            )
            for nutrient in ALL_NUTRIENTS
        },
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    append = commands.add_parser("append")
    append.add_argument("daily_log", type=Path)
    append.add_argument("meal_json", type=Path)
    append.add_argument("--correction", action="store_true")

    read = commands.add_parser("read")
    read.add_argument("daily_log", type=Path)
    read.add_argument("--all-history", action="store_true")

    validate = commands.add_parser("validate")
    validate.add_argument("daily_log", type=Path)

    delete = commands.add_parser("delete")
    delete.add_argument("daily_log", type=Path)
    delete.add_argument("entry_id")
    delete.add_argument("--updated-at", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "append":
            payload = json.loads(args.meal_json.read_text(encoding="utf-8"))
            result = append_record(args.daily_log, payload, correction=args.correction)
        elif args.command == "delete":
            result = delete_entry(args.daily_log, args.entry_id, args.updated_at)
        else:
            records = read_records(args.daily_log)
            if args.command == "validate":
                result = {
                    "status": "validated",
                    "record_count": len(records),
                    "active_meal_count": len(current_records(records)),
                }
            else:
                selected = records if args.all_history else current_records(records)
                result = {"records": selected, "summary": summarize(records)}
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, FoodLogError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
