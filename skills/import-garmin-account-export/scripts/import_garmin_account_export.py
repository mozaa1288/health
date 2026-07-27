#!/usr/bin/env python3
"""Validate and normalize a Garmin account export ZIP."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


MANIFEST_SCHEMA = "garmin-account-export-manifest/v1"
RECORD_SCHEMA = "garmin-account-export-record/v1"
EMAIL_RE = re.compile(r"[^/@\s]+@[^/\s]+")
PROFILE_ID_RE = re.compile(r"(?<!\d)\d{9,}(?!\d)")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DROP_KEYS = {
    "userid",
    "userprofileid",
    "userprofilepk",
    "userprofilePk",
    "deviceid",
    "deviceId",
    "uuid",
    "uuidmsb",
    "uuidlsb",
    "email",
    "emailaddress",
    "startlatitude",
    "startlongitude",
    "endlatitude",
    "endlongitude",
    "latitude",
    "longitude",
    "locationname",
}
DROP_KEYS_NORMALIZED = {re.sub(r"[^a-z0-9]", "", key.lower()) for key in DROP_KEYS}
DROP_KEYS_NORMALIZED.update({"profileid", "profilepk", "accountid", "accountpk"})


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_member(name: str) -> None:
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or "\x00" in name:
        raise ValueError(f"unsafe ZIP member path: {name!r}")


def redacted_path(name: str) -> str:
    return PROFILE_ID_RE.sub("<redacted-id>", EMAIL_RE.sub("<redacted-email>", name))


def scrub(value: Any) -> Any:
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if not isinstance(value, dict):
        return value
    clean = {}
    for key, item in value.items():
        normalized = re.sub(r"[^a-z0-9]", "", key.lower())
        if (
            key in DROP_KEYS
            or normalized in DROP_KEYS_NORMALIZED
            or normalized.endswith("latitude")
            or normalized.endswith("longitude")
        ):
            continue
        clean[key] = scrub(item)
    return clean


def iter_records(obj: Any, dataset: str) -> Iterable[dict[str, Any]]:
    if dataset == "activities":
        roots = obj if isinstance(obj, list) else [obj]
        for root in roots:
            if isinstance(root, dict):
                rows = root.get("summarizedActivitiesExport", [])
                if isinstance(rows, list):
                    yield from (r for r in rows if isinstance(r, dict))
        return
    if dataset == "personal_records":
        roots = obj if isinstance(obj, list) else [obj]
        for root in roots:
            if isinstance(root, dict):
                rows = root.get("personalRecords", [])
                if isinstance(rows, list):
                    yield from (r for r in rows if isinstance(r, dict))
        return
    if dataset == "gear":
        roots = obj if isinstance(obj, list) else [obj]
        for root in roots:
            if isinstance(root, dict):
                rows = root.get("gearDTOS", [])
                if isinstance(rows, list):
                    yield from (r for r in rows if isinstance(r, dict))
        return
    if isinstance(obj, list):
        yield from (r for r in obj if isinstance(r, dict))
    elif isinstance(obj, dict):
        yield obj


def classify(name: str) -> str | None:
    low = name.lower()
    if "udsfile_" in low:
        return "daily"
    if "summarizedactivities" in low:
        return "activities"
    if low.endswith("_sleepdata.json"):
        return "sleep"
    if low.endswith("_healthstatusdata.json"):
        return "health_status"
    if "hydrationlogfile_" in low:
        return "hydration"
    if "traininghistory_" in low:
        return "training_status"
    if "metricsmaxmetdata_" in low:
        return "vo2max"
    if "metricsheataltitudeacclimation_" in low:
        return "acclimation"
    if low.endswith("_userbiometrics.json") or low.endswith("_userbiometricprofiledata.json") or low.endswith("_biometrics_latest.json"):
        return "biometrics"
    if low.endswith("_fitnessagedata.json"):
        return "fitness_age"
    if low.endswith("_heartratezones.json"):
        return "heart_rate_zones"
    if low.endswith("_personalrecord.json"):
        return "personal_records"
    if low.endswith("_gear.json"):
        return "gear"
    return None


def parse_date_value(value: Any) -> str | None:
    if isinstance(value, str):
        candidate = value[:10]
        if DATE_RE.match(candidate):
            try:
                dt.date.fromisoformat(candidate)
                return candidate
            except ValueError:
                return None
    if isinstance(value, (int, float)) and value > 10_000_000_000:
        try:
            return dt.datetime.fromtimestamp(value / 1000, tz=dt.timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    return None


def event_date(record: dict[str, Any], dataset: str) -> str | None:
    keys = (
        "calendarDate",
        "asOfDateGmt",
        "createdDate",
        "dateBegin",
        "startTimeLocal",
        "startTimeGmt",
        "beginTimestamp",
        "timestampLocal",
        "timestamp",
        "createTimestamp",
        "updateTimestamp",
    )
    for key in keys:
        if key in record:
            parsed = parse_date_value(record[key])
            if parsed:
                return parsed
    metadata = record.get("metaData")
    if isinstance(metadata, dict):
        for key in ("calendarDate", "effectiveDate", "updateTimestamp", "createTimestamp"):
            parsed = parse_date_value(metadata.get(key))
            if parsed:
                return parsed
    return None


def stable_id(dataset: str, record: dict[str, Any], digest: str, date_value: str | None) -> str:
    preferred_keys = {
        "activities": ("activityId",),
        "personal_records": ("personalRecordId",),
        "gear": ("gearPk",),
        "hydration": ("uuid", "activityId"),
    }.get(dataset, ())
    for key in preferred_keys:
        if record.get(key) not in (None, ""):
            if key == "uuid":
                opaque = sha256_bytes(str(record[key]).encode())[:24]
                return f"{dataset}:uuid-sha256:{opaque}"
            return f"{dataset}:{key}:{record[key]}"
    pieces = [date_value or ""]
    for key in ("timestamp", "timestampLocal", "startTimeGmt", "sport", "trainingMethod"):
        if record.get(key) not in (None, ""):
            pieces.append(str(record[key]))
    if any(pieces):
        return f"{dataset}:natural:{sha256_bytes('|'.join(pieces).encode())[:24]}"
    return f"{dataset}:hash:{digest[:24]}"


def is_placeholder(dataset: str, record: dict[str, Any]) -> bool:
    return not record or (dataset == "sleep" and set(record) <= {"retro"})


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            stream.write("\n")


def inspect_nested_zip(container: str, payload: bytes) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows = []
    counts = Counter()
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as nested:
            bad = nested.testzip()
            if bad:
                raise ValueError(f"nested ZIP integrity failure: {redacted_path(container)}")
            for info in nested.infolist():
                safe_member(info.filename)
                if info.is_dir():
                    continue
                suffix = Path(info.filename).suffix.lower().lstrip(".") or "none"
                counts[suffix] += 1
                if suffix == "fit":
                    inventory_record = {
                        "member_name": redacted_path(PurePosixPath(info.filename).name),
                        "compressed_size": info.compress_size,
                        "uncompressed_size": info.file_size,
                        "crc32": f"{info.CRC:08x}",
                        "decoded": False,
                    }
                    inventory_digest = sha256_bytes(
                        json.dumps(inventory_record, sort_keys=True, separators=(",", ":")).encode()
                    )
                    rows.append(
                        {
                            "schema_version": RECORD_SCHEMA,
                            "dataset": "fit_inventory",
                            "stable_id": f"fit_inventory:hash:{inventory_digest[:24]}",
                            "source_record_sha256": inventory_digest,
                            "canonical_record_sha256": inventory_digest,
                            "source_file": redacted_path(container),
                            "source_index": len(rows),
                            "event_date": None,
                            "record": inventory_record,
                        }
                    )
    except zipfile.BadZipFile as exc:
        raise ValueError(f"invalid nested ZIP: {redacted_path(container)}") from exc
    return rows, dict(counts)


def build_import(
    input_path: Path,
    output_dir: Path,
    snapshot_date: dt.date,
    drive_id: str | None,
    snapshot_copy_drive_id: str | None,
) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory already exists and is not empty")
    if not zipfile.is_zipfile(input_path):
        raise ValueError("input is not a ZIP file")

    source_sha = sha256_file(input_path)
    datasets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_pairs: dict[str, set[tuple[str, str]]] = defaultdict(set)
    stable_hashes: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    placeholder_counts = Counter()
    outer_types = Counter()
    nested_types = Counter()
    anomalies: list[dict[str, Any]] = []
    json_errors: list[str] = []
    outer_file_count = 0
    outer_uncompressed = 0

    try:
        with zipfile.ZipFile(input_path) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f"ZIP integrity failure at {redacted_path(bad)}")
            for info in archive.infolist():
                safe_member(info.filename)
                if info.is_dir():
                    continue
                outer_file_count += 1
                outer_uncompressed += info.file_size
                suffix = Path(info.filename).suffix.lower().lstrip(".") or "none"
                outer_types[suffix] += 1
                payload = archive.read(info)
                if suffix == "zip":
                    fit_rows, type_counts = inspect_nested_zip(info.filename, payload)
                    datasets["fit_inventory"].extend(fit_rows)
                    nested_types.update(type_counts)
                    continue
                dataset = classify(info.filename)
                if not dataset:
                    continue
                try:
                    obj = json.loads(payload)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    json_errors.append(f"{redacted_path(info.filename)}: {exc.__class__.__name__}")
                    continue
                for source_index, record in enumerate(iter_records(obj, dataset)):
                    if is_placeholder(dataset, record):
                        placeholder_counts[dataset] += 1
                        continue
                    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
                    digest = sha256_bytes(canonical)
                    clean_record = scrub(record)
                    canonical_digest = sha256_bytes(
                        json.dumps(
                            clean_record,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        ).encode()
                    )
                    date_value = event_date(record, dataset)
                    sid = stable_id(dataset, record, digest, date_value)
                    pair = (sid, canonical_digest)
                    if pair in seen_pairs[dataset]:
                        continue
                    seen_pairs[dataset].add(pair)
                    stable_hashes[dataset][sid].add(canonical_digest)
                    row = {
                        "schema_version": RECORD_SCHEMA,
                        "dataset": dataset,
                        "stable_id": sid,
                        "source_record_sha256": digest,
                        "canonical_record_sha256": canonical_digest,
                        "source_file": redacted_path(info.filename),
                        "source_index": source_index,
                        "event_date": date_value,
                        "record": clean_record,
                    }
                    if date_value:
                        parsed = dt.date.fromisoformat(date_value)
                        if parsed > snapshot_date + dt.timedelta(days=7):
                            anomalies.append(
                                {
                                    "dataset": dataset,
                                    "stable_id": sid,
                                    "event_date": date_value,
                                    "reason": "future_date_more_than_7_days_after_snapshot",
                                    "source_file": redacted_path(info.filename),
                                }
                            )
                    datasets[dataset].append(row)
    except zipfile.BadZipFile as exc:
        raise ValueError("input ZIP is corrupt") from exc

    if json_errors:
        raise ValueError("supported JSON parse failures: " + "; ".join(json_errors))

    for dataset, groups in stable_hashes.items():
        conflicted = {sid for sid, hashes in groups.items() if len(hashes) > 1}
        if not conflicted:
            continue
        for row in datasets[dataset]:
            if row["stable_id"] in conflicted:
                row["conflict_group"] = row["stable_id"]
        for sid in sorted(conflicted):
            anomalies.append(
                {
                    "dataset": dataset,
                    "stable_id": sid,
                    "reason": "same_stable_id_different_payload",
                    "variants": len(groups[sid]),
                }
            )

    temp_parent = output_dir.parent if output_dir.parent.exists() else Path(".")
    with tempfile.TemporaryDirectory(prefix=".garmin-import-", dir=temp_parent) as temp_name:
        staging = Path(temp_name) / "result"
        normalized = staging / "normalized"
        normalized.mkdir(parents=True)
        artifacts = []
        anomaly_keys = {(a.get("dataset"), a.get("stable_id")) for a in anomalies if a.get("event_date")}

        for dataset in sorted(datasets):
            rows = sorted(
                datasets[dataset],
                key=lambda r: (
                    r.get("event_date") or "",
                    r["stable_id"],
                    r.get("canonical_record_sha256") or "",
                ),
            )
            if not rows:
                continue
            path = normalized / f"{dataset}.jsonl"
            write_jsonl(path, rows)
            trustworthy_dates = [
                r["event_date"]
                for r in rows
                if r.get("event_date") and (dataset, r["stable_id"]) not in anomaly_keys
            ]
            artifacts.append(
                {
                    "dataset": dataset,
                    "path": f"normalized/{path.name}",
                    "record_count": len(rows),
                    "byte_size": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "trustworthy_coverage": {
                        "start": min(trustworthy_dates) if trustworthy_dates else None,
                        "end": max(trustworthy_dates) if trustworthy_dates else None,
                    },
                }
            )

        validation = {
            "status": "validated",
            "zip_integrity": True,
            "safe_paths": True,
            "supported_json_parse_errors": 0,
            "artifact_hashes_computed": True,
        }
        manifest = {
            "schema_version": MANIFEST_SCHEMA,
            "snapshot_date": snapshot_date.isoformat(),
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            "source": {
                "original_drive_file_id": drive_id,
                "snapshot_copy_drive_file_id": snapshot_copy_drive_id,
                "original_name": "<redacted-garmin-account-export>.zip",
                "byte_size": input_path.stat().st_size,
                "sha256": source_sha,
            },
            "inventory": {
                "outer_file_count": outer_file_count,
                "outer_uncompressed_bytes": outer_uncompressed,
                "outer_file_types": dict(sorted(outer_types.items())),
                "nested_file_types": dict(sorted(nested_types.items())),
            },
            "artifacts": artifacts,
            "skipped_placeholders": dict(sorted(placeholder_counts.items())),
            "anomalies": sorted(anomalies, key=lambda a: (a.get("dataset", ""), a.get("stable_id", ""), a.get("reason", ""))),
            "privacy": {
                "raw_zip_contains_sensitive_data": True,
                "normalized_direct_identifiers_removed": True,
                "excluded_from_normalized_surface": [
                    "account_and_contact",
                    "consent_and_social",
                    "courses_and_gps",
                    "ecg",
                    "media",
                    "raw_fit_payloads",
                ],
            },
            "fit_handling": "inventory_only_not_decoded",
            "validation": validation,
        }
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        lines = [
            "# Garmin Account Export Catalog",
            "",
            f"- Snapshot date: `{snapshot_date.isoformat()}`",
            f"- Source SHA-256: `{source_sha}`",
            f"- Validation: `{validation['status']}`",
            f"- Normalized datasets: {len(artifacts)}",
            f"- FIT files inventoried: {len(datasets.get('fit_inventory', []))}",
            "- FIT payload decoding: not performed",
            "- Direct account, device, email, UUID, location-name, and GPS fields are removed from normalized records.",
            "",
            "## Dataset coverage",
            "",
            "| Dataset | Records | Trustworthy start | Trustworthy end |",
            "|---|---:|---|---|",
        ]
        for artifact in artifacts:
            coverage = artifact["trustworthy_coverage"]
            lines.append(
                f"| `{artifact['dataset']}` | {artifact['record_count']} | "
                f"{coverage['start'] or 'unknown'} | {coverage['end'] or 'unknown'} |"
            )
        lines.extend(
            [
                "",
                "## Validation notes",
                "",
                f"- Skipped placeholder records: {sum(placeholder_counts.values())}",
                f"- Flagged anomalies or conflicts: {len(anomalies)}",
                "- Missing dates or datasets remain unknown; they are never interpreted as zero.",
                "- The immutable original ZIP remains the audit source and is not unpacked into Drive.",
                "",
            ]
        )
        (staging / "catalog.md").write_text("\n".join(lines), encoding="utf-8")

        if output_dir.exists():
            output_dir.rmdir()
        os.replace(staging, output_dir)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Garmin account export ZIP")
    parser.add_argument("--output-dir", required=True, type=Path, help="new or empty output directory")
    parser.add_argument("--snapshot-date", required=True, type=dt.date.fromisoformat)
    parser.add_argument("--source-drive-id", default=None)
    parser.add_argument("--snapshot-copy-drive-id", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        build_import(
            args.input.resolve(),
            args.output_dir.resolve(),
            args.snapshot_date,
            args.source_drive_id,
            args.snapshot_copy_drive_id,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(str(args.output_dir.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
