#!/usr/bin/env python3
"""Normalize one dataset from a Garmin export, daily archive, or live payload."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from import_garmin_account_export import (
    RECORD_SCHEMA,
    event_date,
    is_placeholder,
    iter_records,
    redacted_path,
    scrub,
    stable_id,
)


def digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def valid_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def select_dataset(payload: Any, dataset: str) -> tuple[Any, str | None, str]:
    """Extract a dataset from a cron-generated per-day archive when present."""

    if (
        isinstance(payload, dict)
        and dataset in payload
        and "date" in payload
        and "pulled_at" in payload
    ):
        return payload[dataset], valid_date(payload.get("date")), "daily_archive"
    return payload, None, "direct_payload"


def records(payload: Any, dataset: str) -> Iterable[dict[str, Any]]:
    """Accept both export wrappers and direct daily endpoint responses."""

    if dataset == "activities" and isinstance(payload, list):
        yield from (row for row in payload if isinstance(row, dict))
        return
    yield from iter_records(payload, dataset)


def derived_date(
    record: dict[str, Any], dataset: str, archive_date: str | None
) -> str | None:
    return event_date(record, dataset) or archive_date


def record_stable_id(
    dataset: str,
    record: dict[str, Any],
    source_hash: str,
    date_value: str | None,
) -> str:
    """Give interval records stable IDs without collapsing a day's time series."""

    interval_keys = (
        ("startGMT", "endGMT"),
        ("startTimestampGMT", "endTimestampGMT"),
        ("startTimeGMT", "endTimeGMT"),
        ("startTimeGmt", "endTimeGmt"),
        ("eventStartTimeGmt", "eventUpdateTimeGmt"),
    )
    for start_key, end_key in interval_keys:
        start = record.get(start_key)
        end = record.get(end_key)
        if start not in (None, ""):
            token = "|".join((dataset, str(start), str(end or "")))
            opaque = hashlib.sha256(token.encode()).hexdigest()[:24]
            return f"{dataset}:interval-sha256:{opaque}"
    return stable_id(dataset, record, source_hash, date_value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--input-json", required=True, type=Path)
    parser.add_argument("--output-jsonl", required=True, type=Path)
    parser.add_argument("--source-file", required=True)
    args = parser.parse_args()

    try:
        root = json.loads(args.input_json.read_text(encoding="utf-8"))
        payload, archive_date, source_shape = select_dataset(root, args.dataset)

        if isinstance(payload, dict) and payload.get("error"):
            args.output_jsonl.write_text("", encoding="utf-8")
            print(
                json.dumps(
                    {
                        "status": "source_error",
                        "dataset": args.dataset,
                        "record_count": 0,
                        "error": str(payload.get("error")),
                        "source_shape": source_shape,
                    }
                )
            )
            return 0

        rows = []
        seen = set()
        for index, record in enumerate(records(payload, args.dataset)):
            if is_placeholder(args.dataset, record):
                continue
            source_hash = digest(record)
            clean = scrub(record)
            canonical_hash = digest(clean)
            date_value = derived_date(record, args.dataset, archive_date)
            sid = record_stable_id(
                args.dataset, record, source_hash, date_value
            )
            pair = (sid, canonical_hash)
            if pair in seen:
                continue
            seen.add(pair)
            rows.append(
                {
                    "schema_version": RECORD_SCHEMA,
                    "dataset": args.dataset,
                    "stable_id": sid,
                    "source_record_sha256": source_hash,
                    "canonical_record_sha256": canonical_hash,
                    "source_file": redacted_path(args.source_file),
                    "source_index": index,
                    "event_date": date_value,
                    "record": clean,
                }
            )
        rows.sort(
            key=lambda row: (
                row.get("event_date") or "",
                row["stable_id"],
                row["canonical_record_sha256"],
            )
        )
        with args.output_jsonl.open("w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(
                    json.dumps(
                        row,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "status": "validated",
                "dataset": args.dataset,
                "record_count": len(rows),
                "source_shape": source_shape,
                "archive_date": archive_date,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
