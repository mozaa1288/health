#!/usr/bin/env python3
"""Pull Garmin daily data into one raw JSON archive per local date."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from garminconnect import Garmin

LOCAL_ZONE = ZoneInfo("America/Los_Angeles")
DEFAULT_TOKEN_DIR = Path.home() / ".garminconnect"
DEFAULT_OUTPUT_DIR = Path(
    os.environ.get(
        "GARMIN_ARCHIVE_DIR",
        str(Path.home() / "Documents" / "Health" / "Daily_Archives"),
    )
)

ENDPOINT_NAMES = (
    "stats",
    "user_summary",
    "sleep",
    "heart_rate",
    "stress",
    "body_battery",
    "steps",
    "hrv",
    "respiration",
    "spo2",
    "max_metrics",
    "training_status",
    "training_readiness",
    "body_composition",
    "weigh_ins",
    "daily_weigh_ins",
    "activities",
)


def safe_fetch_method(
    garmin: Garmin, method_name: str, *args: Any, **kwargs: Any
) -> Any:
    try:
        func = getattr(garmin, method_name)
        return func(*args, **kwargs)
    except Exception as exc:  # Garmin endpoint failures must remain in the archive.
        return {"error": f"{type(exc).__name__}: {exc}"}


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO date: {value}") from exc


def date_range(start: dt.date, end: dt.date):
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def build_payload(garmin: Garmin, date_value: dt.date) -> dict[str, Any]:
    date_str = date_value.isoformat()
    return {
        "date": date_str,
        "pulled_at": dt.datetime.now(LOCAL_ZONE).isoformat(),
        "stats": safe_fetch_method(garmin, "get_stats", date_str),
        "user_summary": safe_fetch_method(garmin, "get_user_summary", date_str),
        "sleep": safe_fetch_method(garmin, "get_sleep_data", date_str),
        "heart_rate": safe_fetch_method(garmin, "get_heart_rates", date_str),
        "stress": safe_fetch_method(garmin, "get_stress_data", date_str),
        "body_battery": safe_fetch_method(garmin, "get_body_battery", date_str),
        "steps": safe_fetch_method(garmin, "get_steps_data", date_str),
        "hrv": safe_fetch_method(garmin, "get_hrv_data", date_str),
        "respiration": safe_fetch_method(garmin, "get_respiration_data", date_str),
        "spo2": safe_fetch_method(garmin, "get_spo2_data", date_str),
        "max_metrics": safe_fetch_method(garmin, "get_max_metrics", date_str),
        "training_status": safe_fetch_method(
            garmin, "get_training_status", date_str
        ),
        "training_readiness": safe_fetch_method(
            garmin, "get_training_readiness", date_str
        ),
        "body_composition": safe_fetch_method(
            garmin, "get_body_composition", date_str
        ),
        "weigh_ins": safe_fetch_method(
            garmin, "get_weigh_ins", date_str, date_str
        ),
        "daily_weigh_ins": safe_fetch_method(
            garmin, "get_daily_weigh_ins", date_str
        ),
        "activities": safe_fetch_method(
            garmin, "get_activities_by_date", date_str, date_str
        ),
    }


def validate_payload(payload: dict[str, Any], expected_date: dt.date) -> list[str]:
    errors: list[str] = []
    if payload.get("date") != expected_date.isoformat():
        errors.append("top-level date does not match filename date")

    pulled_at = payload.get("pulled_at")
    try:
        parsed = dt.datetime.fromisoformat(str(pulled_at))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            errors.append("pulled_at is not timezone-aware")
    except ValueError:
        errors.append("pulled_at is not valid ISO datetime")

    for key in ENDPOINT_NAMES:
        if key not in payload:
            errors.append(f"missing endpoint section: {key}")
    return errors


def write_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def existing_archive_is_valid(path: Path, expected_date: dt.date) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and not validate_payload(payload, expected_date)


def endpoint_failures(payload: dict[str, Any]) -> list[str]:
    failures = []
    for key in ENDPOINT_NAMES:
        value = payload.get(key)
        if isinstance(value, dict) and "error" in value:
            failures.append(f"{key}: {value['error']}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-dir", type=Path, default=DEFAULT_TOKEN_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--start-date", type=parse_date)
    parser.add_argument("--end-date", type=parse_date)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=1.5)
    args = parser.parse_args()

    today = dt.datetime.now(LOCAL_ZONE).date()
    if args.start_date or args.end_date:
        if not (args.start_date and args.end_date):
            parser.error("--start-date and --end-date must be supplied together")
        start_date = args.start_date
        end_date = args.end_date
    else:
        if args.days < 1:
            parser.error("--days must be at least 1")
        end_date = today
        start_date = today - dt.timedelta(days=args.days - 1)

    if start_date > end_date:
        parser.error("start date must not be after end date")
    if end_date > today:
        parser.error("end date must not be in the future")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{dt.datetime.now(LOCAL_ZONE).isoformat()}] Authenticating with Garmin...")
    try:
        garmin = Garmin()
        garmin.login(tokenstore=str(args.token_dir))
    except Exception as exc:
        print(f"ERROR: Garmin authentication failed: {exc}", file=sys.stderr)
        return 2

    written = 0
    skipped = 0
    failed = 0
    endpoint_error_count = 0

    dates = list(date_range(start_date, end_date))
    for index, date_value in enumerate(dates, start=1):
        output_path = args.output_dir / f"garmin_{date_value.isoformat()}.json"

        # Today and yesterday are refreshed because same-day archives may be partial.
        refresh_recent = date_value >= today - dt.timedelta(days=1)
        if output_path.exists():
            existing_valid = existing_archive_is_valid(output_path, date_value)
            if not args.force and not refresh_recent and existing_valid:
                print(f"[{index}/{len(dates)}] {date_value}: existing stable file; skipped")
                skipped += 1
                continue
            if not existing_valid:
                print(
                    f"[{index}/{len(dates)}] {date_value}: existing file is invalid; "
                    "re-pulling"
                )

        print(f"[{index}/{len(dates)}] {date_value}: pulling")
        payload = build_payload(garmin, date_value)
        validation_errors = validate_payload(payload, date_value)
        if validation_errors:
            print(
                f"ERROR: {date_value}: " + "; ".join(validation_errors),
                file=sys.stderr,
            )
            failed += 1
            continue

        try:
            write_atomic(output_path, payload)
        except OSError as exc:
            print(f"ERROR: {date_value}: write failed: {exc}", file=sys.stderr)
            failed += 1
            continue

        failures = endpoint_failures(payload)
        endpoint_error_count += len(failures)
        written += 1
        print(
            f"[{index}/{len(dates)}] {date_value}: wrote {output_path.name}"
            + (f" with {len(failures)} endpoint error(s)" if failures else "")
        )

        if index < len(dates) and args.delay_seconds > 0:
            time.sleep(args.delay_seconds)

    summary = {
        "status": (
            "complete"
            if failed == 0 and endpoint_error_count == 0
            else "partial"
        ),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "output_dir": str(args.output_dir),
        "written": written,
        "skipped": skipped,
        "failed": failed,
        "endpoint_errors": endpoint_error_count,
    }
    print(json.dumps(summary, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
