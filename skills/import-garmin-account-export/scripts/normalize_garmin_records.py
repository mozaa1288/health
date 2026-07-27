#!/usr/bin/env python3
"""Normalize one Garmin export, daily-archive, or live-response JSON payload."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--input-json", required=True, type=Path)
    parser.add_argument("--output-jsonl", required=True, type=Path)
    parser.add_argument("--source-file", required=True)
    args = parser.parse_args()

    try:
        payload = json.loads(args.input_json.read_text(encoding="utf-8"))
        rows = []
        seen = set()
        for index, record in enumerate(iter_records(payload, args.dataset)):
            if is_placeholder(args.dataset, record):
                continue
            source_hash = digest(record)
            clean = scrub(record)
            canonical_hash = digest(clean)
            date_value = event_date(record, args.dataset)
            sid = stable_id(args.dataset, record, source_hash, date_value)
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
    print(json.dumps({"status": "validated", "record_count": len(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
