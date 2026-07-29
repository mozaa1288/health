#!/usr/bin/env python3
"""Decode, validate, and summarize Garmin daily archives pulled from Google Drive.

This is the *retrieval-side* helper. It handles the shapes a Drive download
actually arrives in, so the retrieval path is one command instead of ad hoc
JSON unwrapping.

Accepted inputs (auto-detected per file):
  1. A raw archive:            {"date": ..., "pulled_at": ..., "stats": {...}, ...}
  2. A Drive tool-result file: [{"type": "text", "text": "{\"content\": \"<base64>\"}"}]
  3. The inner Drive object:   {"id": ..., "title": ..., "content": "<base64>"}

Usage:
    python read_garmin_archive.py FILE [FILE ...]
    python read_garmin_archive.py FILE --json          # machine-readable summary
    python read_garmin_archive.py FILE --section sleep # dump one raw section
    python read_garmin_archive.py FILE --decode-to DIR # write decoded raw JSON

Exit codes: 0 = all files valid, 1 = one or more validation problems.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any

SECTIONS = (
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

KG_PER_GRAM = 0.001
LB_PER_KG = 2.2046226218
MI_PER_M = 0.000621371


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def load_archive(path: Path) -> dict[str, Any]:
    """Return the raw Garmin archive dict, unwrapping Drive envelopes as needed."""
    text = path.read_text(encoding="utf-8", errors="replace")
    obj = json.loads(text)

    # Shape 2: Drive tool-result list of content blocks.
    if isinstance(obj, list):
        blocks = [b for b in obj if isinstance(b, dict) and b.get("type") == "text"]
        if not blocks:
            raise ValueError(f"{path.name}: list payload has no text block")
        obj = json.loads(blocks[0]["text"])

    if not isinstance(obj, dict):
        raise ValueError(f"{path.name}: unrecognized payload type {type(obj).__name__}")

    # Shape 3: Drive file object carrying base64 content.
    if "content" in obj and "date" not in obj:
        obj = json.loads(base64.b64decode(obj["content"]))

    if not isinstance(obj, dict) or "date" not in obj:
        raise ValueError(f"{path.name}: decoded payload is not a Garmin archive")

    return obj


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def classify_section(value: Any) -> str:
    """One of: error, missing, empty, present."""
    if value is None:
        return "missing"
    if isinstance(value, dict) and "error" in value:
        return "error"
    if isinstance(value, (list, dict)) and len(value) == 0:
        return "empty"
    return "present"


def validate(archive: dict[str, Any], path: Path) -> dict[str, Any]:
    problems: list[str] = []

    stem_date = path.stem.replace("garmin_", "")
    file_date = archive.get("date")
    if stem_date and stem_date != file_date and not path.stem.startswith("Google_"):
        problems.append(f"filename date {stem_date!r} != top-level date {file_date!r}")

    pulled_at = archive.get("pulled_at")
    tz_aware = False
    try:
        import datetime as dt

        parsed = dt.datetime.fromisoformat(str(pulled_at))
        tz_aware = parsed.utcoffset() is not None
    except (TypeError, ValueError):
        problems.append(f"pulled_at is not ISO datetime: {pulled_at!r}")
    if pulled_at and not tz_aware:
        # Warn, do not fail: archives in Drive are currently naive local time.
        problems.append(f"WARN pulled_at is not timezone-aware: {pulled_at!r}")

    status = {name: classify_section(archive.get(name)) for name in SECTIONS}
    for name, state in status.items():
        if state == "error":
            problems.append(f"endpoint failure in {name}: {archive[name]['error']}")
        elif state == "missing":
            problems.append(f"missing section: {name}")

    return {
        "date": file_date,
        "pulled_at": pulled_at,
        "section_status": status,
        "problems": problems,
        "fatal": [p for p in problems if not p.startswith("WARN")],
    }


# --------------------------------------------------------------------------- #
# Summarizing
# --------------------------------------------------------------------------- #

def dig(obj: Any, *keys: Any, default: Any = None) -> Any:
    """Nested get that survives missing keys, nulls, and short lists."""
    cur = obj
    for key in keys:
        if cur is None:
            return default
        try:
            cur = cur[key]
        except (KeyError, IndexError, TypeError):
            return default
    return cur if cur is not None else default


def summarize(archive: dict[str, Any]) -> dict[str, Any]:
    stats = archive.get("stats") or {}
    if isinstance(stats, dict) and "error" in stats:
        stats = {}
    sleep_dto = dig(archive, "sleep", "dailySleepDTO", default={}) or {}

    sleep_seconds = sleep_dto.get("sleepTimeSeconds")
    sleep_text = None
    if isinstance(sleep_seconds, (int, float)):
        sleep_text = f"{int(sleep_seconds) // 3600}h{(int(sleep_seconds) % 3600) // 60:02d}m"

    weight_g = dig(archive, "body_composition", "dateWeightList", 0, "weight")
    weight_lb = round(weight_g * KG_PER_GRAM * LB_PER_KG, 1) if weight_g else None

    activities = archive.get("activities")
    activity_rows = []
    if isinstance(activities, list):
        for act in activities:
            if not isinstance(act, dict):
                continue
            dur = act.get("duration")
            dist = act.get("distance")
            activity_rows.append(
                {
                    "name": act.get("activityName"),
                    "type": dig(act, "activityType", "typeKey"),
                    "minutes": round(dur / 60, 0) if isinstance(dur, (int, float)) else None,
                    "miles": round(dist * MI_PER_M, 2) if isinstance(dist, (int, float)) else None,
                }
            )

    return {
        "date": archive.get("date"),
        "steps": stats.get("totalSteps"),
        "step_goal": stats.get("dailyStepGoal"),
        "resting_hr": stats.get("restingHeartRate"),
        "max_hr": stats.get("maxHeartRate"),
        "total_kcal": stats.get("totalKilocalories"),
        "active_kcal": stats.get("activeKilocalories"),
        "sleep": sleep_text,
        "sleep_score": dig(sleep_dto, "sleepScores", "overall", "value"),
        "sleep_qualifier": dig(sleep_dto, "sleepScores", "overall", "qualifierKey"),
        "avg_stress": stats.get("averageStressLevel"),
        "body_battery_wake": stats.get("bodyBatteryAtWakeTime"),
        "body_battery_low": stats.get("bodyBatteryLowestValue"),
        "avg_spo2": stats.get("averageSpo2"),
        "vo2max": dig(archive, "max_metrics", 0, "generic", "vo2MaxValue"),
        "weight_lb": weight_lb,
        "intensity_minutes": (
            (stats.get("moderateIntensityMinutes") or 0)
            + 2 * (stats.get("vigorousIntensityMinutes") or 0)
        ),
        "activities": activity_rows,
        # Same-day pulls are partial; this shows how far the watch had synced.
        "data_through_local": stats.get("wellnessEndTimeLocal"),
    }


def fmt(value: Any) -> str:
    return "—" if value in (None, "") else str(value)


def print_report(results: list[tuple[Path, dict[str, Any], dict[str, Any]]]) -> None:
    rows = [
        ("Steps", "steps"),
        ("Resting HR", "resting_hr"),
        ("Sleep", "sleep"),
        ("Sleep score", "sleep_score"),
        ("Avg stress", "avg_stress"),
        ("Body batt wake", "body_battery_wake"),
        ("Body batt low", "body_battery_low"),
        ("Avg SpO2", "avg_spo2"),
        ("Intensity min", "intensity_minutes"),
        ("VO2max", "vo2max"),
        ("Weight (lb)", "weight_lb"),
        ("Active kcal", "active_kcal"),
    ]
    dates = [s["date"] for _, _, s in results]
    width = max(14, *(len(d or "") for d in dates)) + 2

    print("| Metric".ljust(18) + "".join(f"| {d:<{width - 2}}" for d in dates) + "|")
    print("|" + "-" * 17 + ("|" + "-" * width) * len(dates) + "|")
    for label, key in rows:
        line = f"| {label:<16}"
        for _, _, summary in results:
            line += f"| {fmt(summary.get(key)):<{width - 2}} "
        print(line + "|")

    for path, validation, summary in results:
        print(f"\n{summary['date']}  ({path.name})")
        print(f"  pulled_at: {fmt(validation['pulled_at'])}")
        print(f"  data through (local): {fmt(summary['data_through_local'])}")
        for act in summary["activities"]:
            print(
                f"  activity: {fmt(act['name'])} [{fmt(act['type'])}] "
                f"{fmt(act['minutes'])} min, {fmt(act['miles'])} mi"
            )
        unavailable = [
            f"{n} ({s})"
            for n, s in validation["section_status"].items()
            if s != "present"
        ]
        print(f"  unavailable sections: {', '.join(unavailable) if unavailable else 'none'}")
        for problem in validation["problems"]:
            print(f"  ! {problem}")


# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument("--section", help="dump one raw section and exit")
    parser.add_argument("--decode-to", type=Path, help="write decoded raw archives to DIR")
    args = parser.parse_args()

    results: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
    for path in args.files:
        archive = load_archive(path)

        if args.decode_to:
            args.decode_to.mkdir(parents=True, exist_ok=True)
            out = args.decode_to / f"garmin_{archive['date']}.json"
            out.write_text(json.dumps(archive, indent=2), encoding="utf-8")
            print(f"wrote {out}", file=sys.stderr)

        if args.section:
            print(json.dumps(archive.get(args.section), indent=2)[:20000])
            continue

        results.append((path, validate(archive, path), summarize(archive)))

    if args.section:
        return 0

    results.sort(key=lambda r: r[2]["date"] or "")

    if args.json:
        print(
            json.dumps(
                [
                    {"file": str(p), "validation": v, "summary": s}
                    for p, v, s in results
                ],
                indent=2,
            )
        )
    else:
        print_report(results)

    return 1 if any(v["fatal"] for _, v, _ in results) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:  # e.g. piped into `head`
        sys.stderr.close()
        raise SystemExit(0)
