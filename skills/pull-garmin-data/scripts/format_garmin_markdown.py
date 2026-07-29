#!/usr/bin/env python3
"""Format Garmin daily archives as portable Markdown.

Output is plain Markdown — tables and text only — so it pastes natively into
ChatGPT, Gemini, Slack, Notion, or a plain file with no rendering layer. No
HTML, no images, no code fences around the report body.

Reads the same inputs as read_garmin_archive.py (raw archive, Drive tool-result
envelope, or inner base64 object).

Usage:
    python format_garmin_markdown.py FILE [FILE ...]
    python format_garmin_markdown.py FILE -o report.md
    python format_garmin_markdown.py FILE --no-traces      # tables only

Contract: unavailable data renders as an explicit gap character, never as zero.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from read_garmin_archive import (  # noqa: E402
    dig,
    load_archive,
    summarize,
    validate,
)

MS_MIN = 60_000
MS_HOUR = 3_600_000
MS_DAY = 86_400_000

BLOCKS = "▁▂▃▄▅▆▇█"
GAP = "·"          # sampled window with no data — never a zero-height block
BUCKET_MIN = 30    # one character per half hour
QUARTERS = [
    ("12–6 AM", 0, 6),
    ("6 AM–12 PM", 6, 12),
    ("12–6 PM", 12, 18),
    ("6 PM–12 AM", 18, 24),
]


# --------------------------------------------------------------------------- #
# Time
# --------------------------------------------------------------------------- #

def parse_ts(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(dt.datetime.fromisoformat(str(value).rstrip("Z")).timestamp() * 1000)
    except ValueError:
        return None


def local_offset_ms(archive: dict[str, Any]) -> int:
    gmt = dig(archive, "sleep", "dailySleepDTO", "sleepStartTimestampGMT")
    loc = dig(archive, "sleep", "dailySleepDTO", "sleepStartTimestampLocal")
    if isinstance(gmt, (int, float)) and isinstance(loc, (int, float)):
        return int(loc - gmt)
    g = parse_ts(dig(archive, "stats", "wellnessStartTimeGmt"))
    l = parse_ts(dig(archive, "stats", "wellnessStartTimeLocal"))
    return (l - g) if (g is not None and l is not None) else 0


def day_start(archive: dict[str, Any]) -> int:
    start = parse_ts(dig(archive, "stats", "wellnessStartTimeLocal"))
    if start is not None:
        return start
    date = dt.date.fromisoformat(archive["date"])
    return int(dt.datetime.combine(date, dt.time.min).timestamp() * 1000)


def clock(local_ms: Any) -> str:
    if not isinstance(local_ms, (int, float)):
        return "—"
    stamp = dt.datetime.fromtimestamp(local_ms / 1000)
    hour = stamp.hour % 12 or 12
    return f"{hour}:{stamp.minute:02d} {'AM' if stamp.hour < 12 else 'PM'}"


def hhmm(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return "—"
    return f"{int(seconds) // 3600}h{(int(seconds) % 3600) // 60:02d}m"


# --------------------------------------------------------------------------- #
# Series
# --------------------------------------------------------------------------- #

def series_body_battery(archive, off) -> list[tuple[int, float]]:
    rows = dig(archive, "stress", "bodyBatteryValuesArray", default=[]) or []
    return [
        (int(r[0]) + off, float(r[2]))
        for r in rows
        if isinstance(r, (list, tuple)) and len(r) >= 3
        and r[1] not in (None, "OFF_WRIST") and isinstance(r[2], (int, float))
    ]


def series_stress(archive, off) -> list[tuple[int, float]]:
    rows = dig(archive, "stress", "stressValuesArray", default=[]) or []
    # Negative levels are sentinels (unmeasured / off-wrist), not zero stress.
    return [
        (int(r[0]) + off, float(r[1]))
        for r in rows
        if isinstance(r, (list, tuple)) and len(r) >= 2
        and isinstance(r[1], (int, float)) and r[1] >= 0
    ]


def series_heart_rate(archive, off) -> list[tuple[int, float]]:
    rows = dig(archive, "heart_rate", "heartRateValues", default=[]) or []
    return [
        (int(r[0]) + off, float(r[1]))
        for r in rows
        if isinstance(r, (list, tuple)) and len(r) >= 2 and isinstance(r[1], (int, float))
    ]


def series_steps(archive, off) -> list[tuple[int, float]]:
    rows = archive.get("steps")
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        start = parse_ts(row.get("startGMT")) if isinstance(row, dict) else None
        steps = row.get("steps") if isinstance(row, dict) else None
        if start is not None and isinstance(steps, (int, float)):
            out.append((start + off, float(steps)))
    return out


def bucketize(
    points: Sequence[tuple[int, float]], t0: int, mode: str = "mean"
) -> list[float | None]:
    """Collapse a series into 48 half-hour buckets; None where nothing was sampled."""
    count = MS_DAY // (BUCKET_MIN * MS_MIN)
    sums: list[float] = [0.0] * count
    hits: list[int] = [0] * count
    for ts, value in points:
        idx = (ts - t0) // (BUCKET_MIN * MS_MIN)
        if 0 <= idx < count:
            sums[idx] += value
            hits[idx] += 1
    out: list[float | None] = []
    for total, n in zip(sums, hits):
        if n == 0:
            out.append(None)
        else:
            out.append(total if mode == "sum" else total / n)
    return out


def spark(buckets: Sequence[float | None], lo: float | None = None,
          hi: float | None = None) -> list[str]:
    real = [b for b in buckets if b is not None]
    if not real:
        return [GAP] * len(buckets)
    low = lo if lo is not None else min(real)
    high = hi if hi is not None else max(real)
    span = high - low
    chars = []
    for value in buckets:
        if value is None:
            chars.append(GAP)
        elif span <= 0:
            chars.append(BLOCKS[3])
        else:
            step = int((value - low) / span * (len(BLOCKS) - 1) + 0.5)
            chars.append(BLOCKS[max(0, min(len(BLOCKS) - 1, step))])
    return chars


def trace_row(label: str, buckets: Sequence[float | None], unit: str,
              fmt: str = "{:.0f}", lo=None, hi=None,
              raw: Sequence[tuple[int, float]] | None = None) -> str:
    """Render one channel row.

    The sparkline shows half-hour buckets; the Range column reports true sample
    extremes (from `raw` when given), so a smoothed bucket never understates the
    real peak.
    """
    chars = spark(buckets, lo, hi)
    per = len(chars) // 4
    cells = ["".join(chars[i * per:(i + 1) * per]) for i in range(4)]
    if raw is not None:
        values = [v for _, v in raw]
    else:
        values = [b for b in buckets if b is not None]
    rng = f"{fmt.format(min(values))}–{fmt.format(max(values))}{unit}" if values else "no data"
    return f"| {label} | {' | '.join(cells)} | {rng} |"


# --------------------------------------------------------------------------- #
# Report sections
# --------------------------------------------------------------------------- #

def fmt_value(value: Any, fmt: str | None) -> str:
    if value in (None, ""):
        return "—"
    return fmt.format(value) if fmt else str(value)


def summary_table(summaries: list[dict[str, Any]]) -> list[str]:
    fields = [
        ("Steps", "steps", "{:,.0f}"),
        ("Resting HR", "resting_hr", "{:.0f} bpm"),
        ("Sleep", "sleep", None),
        ("Sleep score", "sleep_score", "{:.0f}"),
        ("Avg stress", "avg_stress", "{:.0f}"),
        ("Body battery (wake → low)", None, None),
        ("Intensity minutes", "intensity_minutes", "{:.0f}"),
        ("Active calories", "active_kcal", "{:,.0f} kcal"),
        ("Avg SpO2", "avg_spo2", "{:.0f}%"),
        ("VO2 max", "vo2max", "{:.1f}"),
        ("Weight", "weight_lb", "{:.1f} lb"),
    ]
    header = "| Metric | " + " | ".join(s["date"] for s in summaries) + " |"
    divider = "|---|" + "---|" * len(summaries)
    lines = [header, divider]
    for label, key, fmt in fields:
        if key is None:
            cells = [
                f"{fmt_value(s.get('body_battery_wake'), '{:.0f}')} → "
                f"{fmt_value(s.get('body_battery_low'), '{:.0f}')}"
                for s in summaries
            ]
        else:
            cells = [fmt_value(s.get(key), fmt) for s in summaries]
        if all(c == "—" for c in cells):
            continue
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return lines


def day_section(archive: dict[str, Any], validation: dict[str, Any],
                summary: dict[str, Any], source: str, traces: bool) -> list[str]:
    off = local_offset_ms(archive)
    t0 = day_start(archive)
    date = dt.date.fromisoformat(archive["date"])
    dto = dig(archive, "sleep", "dailySleepDTO", default={}) or {}

    lines: list[str] = [f"### {date.strftime('%A, %B %-d, %Y')}", ""]

    through = parse_ts(summary.get("data_through_local"))
    if through is not None and through < t0 + MS_DAY - MS_MIN:
        lines += [f"**Partial day** — watch synced through {clock(through)} local.", ""]

    if traces:
        bb = series_body_battery(archive, off)
        hr = series_heart_rate(archive, off)
        st = series_stress(archive, off)
        sp = series_steps(archive, off)
        lines += [
            "**Through the day** (half-hour resolution, `" + GAP + "` = not sampled)",
            "",
            "| Channel | " + " | ".join(q[0] for q in QUARTERS) + " | Range |",
            "|---|---|---|---|---|---|",
            trace_row("Body battery", bucketize(bb, t0), "", "{:.0f}",
                      lo=0, hi=100, raw=bb),
            trace_row("Heart rate", bucketize(hr, t0), " bpm", raw=hr),
            trace_row("Stress", bucketize(st, t0), "", "{:.0f}", lo=0, hi=100, raw=st),
            # Steps are summed per bucket, so the range is per-half-hour totals.
            trace_row("Steps", bucketize(sp, t0, mode="sum"), " / 30 min"),
            "",
        ]

    stages = [
        ("Deep", dto.get("deepSleepSeconds")),
        ("Light", dto.get("lightSleepSeconds")),
        ("REM", dto.get("remSleepSeconds")),
        ("Awake", dto.get("awakeSleepSeconds")),
    ]
    total = sum(v for _, v in stages if isinstance(v, (int, float)))
    if total:
        parts = " · ".join(
            f"{name} {hhmm(sec)} ({sec / total * 100:.0f}%)"
            for name, sec in stages
            if isinstance(sec, (int, float)) and sec > 0
        )
        window = (
            f"{clock(dto.get('sleepStartTimestampLocal'))} → "
            f"{clock(dto.get('sleepEndTimestampLocal'))}"
        )
        lines += [f"**Sleep** {window} — {parts}", ""]

    activities = summary.get("activities") or []
    if activities:
        lines += ["| Activity | Type | Duration | Distance |", "|---|---|---|---|"]
        for act in activities:
            lines.append(
                f"| {act.get('name') or 'Activity'} | {act.get('type') or '—'} | "
                f"{fmt_value(act.get('minutes'), '{:.0f} min')} | "
                f"{fmt_value(act.get('miles'), '{:.2f} mi')} |"
            )
        lines.append("")
    else:
        lines += ["No recorded activities.", ""]

    unavailable = [n for n, s in validation["section_status"].items() if s != "present"]
    unavail = ", ".join(
        f"`{n}` ({validation['section_status'][n]})" for n in unavailable
    ) or "none — all 17 sections present"
    lines += [
        f"*Source `{source}` · pulled {validation['pulled_at']} · "
        f"unavailable: {unavail}*",
    ]

    failures = [p for p in validation["problems"] if p.startswith("endpoint failure")]
    if failures:
        lines += [""] + [f"> **Endpoint failure** — {f.split(': ', 1)[-1]}" for f in failures]
    lines.append("")
    return lines


def build_markdown(results: list[tuple[Path, dict, dict, dict]], traces: bool) -> str:
    summaries = [r[3] for r in results]
    dates = [s["date"] for s in summaries]
    span = dates[0] if len(dates) == 1 else f"{dates[0]} → {dates[-1]}"

    lines = [f"## Garmin daily archive — {span}", ""]
    if len(results) > 1:
        lines += summary_table(summaries) + [""]
    for path, archive, validation, summary in results:
        lines += day_section(archive, validation, summary, path.name, traces)
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("-o", "--out", type=Path, help="write to a file instead of stdout")
    parser.add_argument("--no-traces", action="store_true", help="omit sparkline rows")
    args = parser.parse_args()

    results = []
    for path in args.files:
        archive = load_archive(path)
        results.append((path, archive, validate(archive, path), summarize(archive)))
    results.sort(key=lambda r: r[3]["date"] or "")

    text = build_markdown(results, traces=not args.no_traces)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        sys.stderr.close()
        raise SystemExit(0)
