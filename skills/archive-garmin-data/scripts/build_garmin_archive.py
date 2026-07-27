#!/usr/bin/env python3
"""Build a Garmin archive directly from serialized MCP call results."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "garmin-daily-archive-envelope/v2"
CAPTURE_STRING_FIELDS = ("captured_at_local", "captured_at_utc", "timezone")
CAPTURE_OBJECT_FIELDS = (
    "requested_date_range",
    "returned_date_range",
    "date_completeness",
)
ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
LOCAL_TIMEZONE = ZoneInfo("America/Los_Angeles")


def require_nonempty_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def parse_aware_timestamp(value: Any, *, field: str) -> datetime:
    text = require_nonempty_string(value, field=field)
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a UTC offset")
    return parsed


def parse_iso_date(value: Any, *, field: str) -> date:
    text = require_nonempty_string(value, field=field)
    if not ISO_DATE_RE.fullmatch(text):
        raise ValueError(f"{field} must use YYYY-MM-DD")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid calendar date") from exc


def validate_date_range(value: Any, *, field: str) -> tuple[date, date]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    if set(value) != {"from", "to"}:
        raise ValueError(f"{field} must contain exactly 'from' and 'to'")
    start = parse_iso_date(value["from"], field=f"{field}.from")
    end = parse_iso_date(value["to"], field=f"{field}.to")
    if start > end:
        raise ValueError(f"{field}.from must not be after {field}.to")
    return start, end


def validate_capture(capture: Any) -> dict[str, Any]:
    if not isinstance(capture, dict):
        raise ValueError("input must contain a capture object")
    for field in CAPTURE_STRING_FIELDS:
        if field not in capture:
            raise ValueError(f"capture is missing required field {field!r}")
    for field in CAPTURE_OBJECT_FIELDS:
        if field not in capture:
            raise ValueError(f"capture is missing required field {field!r}")

    captured_local = parse_aware_timestamp(
        capture["captured_at_local"], field="capture.captured_at_local"
    )
    captured_utc = parse_aware_timestamp(
        capture["captured_at_utc"], field="capture.captured_at_utc"
    )
    if capture["timezone"] != "America/Los_Angeles":
        raise ValueError("capture.timezone must be 'America/Los_Angeles'")
    if captured_utc.utcoffset() != timedelta(0):
        raise ValueError("capture.captured_at_utc must use UTC")
    if captured_local.astimezone(timezone.utc) != captured_utc.astimezone(timezone.utc):
        raise ValueError("capture timestamps must identify the same instant")
    expected_local = captured_utc.astimezone(LOCAL_TIMEZONE)
    if (
        captured_local.replace(tzinfo=None) != expected_local.replace(tzinfo=None)
        or captured_local.utcoffset() != expected_local.utcoffset()
    ):
        raise ValueError(
            "capture.captured_at_local must be represented in America/Los_Angeles"
        )

    requested_start, requested_end = validate_date_range(
        capture["requested_date_range"], field="capture.requested_date_range"
    )
    returned_start, returned_end = validate_date_range(
        capture["returned_date_range"], field="capture.returned_date_range"
    )
    if returned_start < requested_start or returned_end > requested_end:
        raise ValueError("capture.returned_date_range must be within requested_date_range")

    date_completeness = capture["date_completeness"]
    if not isinstance(date_completeness, dict):
        raise ValueError("capture.date_completeness must be an object")
    expected_dates = {
        (returned_start + timedelta(days=offset)).isoformat()
        for offset in range((returned_end - returned_start).days + 1)
    }
    if set(date_completeness) != expected_dates:
        raise ValueError(
            "capture.date_completeness must contain exactly one entry per returned date"
        )
    for raw_date, completeness in date_completeness.items():
        completeness_date = parse_iso_date(
            raw_date, field="capture.date_completeness key"
        )
        if completeness_date < returned_start or completeness_date > returned_end:
            raise ValueError(
                "capture.date_completeness dates must be within returned_date_range"
            )
        if not isinstance(completeness, str) or completeness.strip().lower() not in {
            "complete",
            "partial",
        }:
            raise ValueError(
                "capture.date_completeness values must be 'complete' or 'partial'"
            )
    return capture


def validate_calls(calls: Any) -> list[dict[str, Any]]:
    if not isinstance(calls, list) or not calls:
        raise ValueError("input must contain a non-empty calls array")
    validated: list[dict[str, Any]] = []
    for index, call in enumerate(calls):
        if not isinstance(call, dict):
            raise ValueError(f"calls[{index}] must be an object")
        endpoint = require_nonempty_string(
            call.get("endpoint"), field=f"calls[{index}].endpoint"
        )
        if endpoint != endpoint.strip():
            raise ValueError(f"calls[{index}].endpoint must not have surrounding whitespace")
        if "request" not in call or not isinstance(call["request"], dict):
            raise ValueError(f"calls[{index}].request must be an object")
        if "result" not in call or not isinstance(call["result"], dict):
            raise ValueError(f"calls[{index}].result must be an MCP result object")
        if "isError" in call["result"] and not isinstance(call["result"]["isError"], bool):
            raise ValueError(f"calls[{index}].result.isError must be a boolean")
        validated.append(call)
    return validated


def response_payload(result: dict[str, Any]) -> Any:
    """Return native structured JSON, falling back to verbatim content blocks."""
    if "structuredContent" in result and result["structuredContent"] is not None:
        return result["structuredContent"]
    return result.get("content")


def build_archive(source: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise ValueError("input must be a JSON object")
    capture = validate_capture(source.get("capture"))
    calls = validate_calls(source.get("calls"))

    records: list[dict[str, Any]] = []
    for index, call in enumerate(calls):
        result = call["result"]
        records.append(
            {
                "endpoint": call["endpoint"],
                "request": call["request"],
                "response": response_payload(result),
                "is_error": bool(result.get("isError", False)),
            }
        )

    return {
        "archive_schema": SCHEMA_VERSION,
        "capture": capture,
        "endpoint_inventory": [
            {
                "endpoint": record["endpoint"],
                "request": record["request"],
                "is_error": record["is_error"],
            }
            for record in records
        ],
        "endpoint_records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8") as handle:
        source = json.load(handle)

    archive = build_archive(source)
    encoded = json.dumps(archive, indent=2, ensure_ascii=False) + "\n"

    # Validate the exact serialized bytes before writing them.
    json.loads(encoded)
    args.output.write_text(encoded, encoding="utf-8")

    # Validate the written artifact as a second check.
    with args.output.open("r", encoding="utf-8") as handle:
        written = json.load(handle)
    if written.get("archive_schema") != SCHEMA_VERSION:
        raise RuntimeError("written archive failed schema verification")

    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(args.output),
                "endpoint_count": len(archive["endpoint_records"]),
                "schema": SCHEMA_VERSION,
            }
        )
    )


if __name__ == "__main__":
    main()
