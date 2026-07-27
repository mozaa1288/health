#!/usr/bin/env python3
"""Search the user's compact Open Food Facts index and emit log-food JSON."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import re
import shutil
import sqlite3
import sys
import unicodedata
from pathlib import Path
from typing import Any

SNAPSHOT_DATE = "2019-09-19"
DRIVE_FOLDER_URL = (
    "https://drive.google.com/drive/folders/1gSiZ1TQVBKFkfXVqsiG5TIVpio6OfST7"
)
SEARCH_COLUMNS = ("product_name", "generic_name", "brands", "categories_en")
NUTRIENT_COLUMNS = (
    "energy_100g",
    "fat_100g",
    "carbohydrates_100g",
    "fiber_100g",
    "proteins_100g",
    "sodium_100g",
)


class LookupError(ValueError):
    pass


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    return " ".join(re.findall(r"[a-z0-9]+", folded))


def tokens(text: str) -> list[str]:
    return [token for token in normalize(text).split() if len(token) > 1]


def ensure_sqlite(path: Path, cache_dir: Path | None) -> Path:
    if path.suffix != ".gz":
        return path
    output = (cache_dir or path.parent) / path.with_suffix("").name
    if not output.exists() or output.stat().st_mtime < path.stat().st_mtime:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        with gzip.open(path, "rb") as source, temporary.open("wb") as destination:
            shutil.copyfileobj(source, destination)
        temporary.replace(output)
    return output


def safe_fts(words: list[str]) -> str:
    return " AND ".join(f'"{word.replace(chr(34), "")}"' for word in words)


def search_rows(db: sqlite3.Connection, query: str, limit: int) -> list[sqlite3.Row]:
    query_tokens = tokens(query)
    if not query_tokens:
        raise LookupError("search query has no searchable letters or digits")
    attempts: list[list[str]] = [query_tokens]
    if len(query_tokens) > 1:
        attempts.extend(
            query_tokens[:index] + query_tokens[index + 1 :]
            for index in range(len(query_tokens) - 1, -1, -1)
        )
    seen: set[str] = set()
    rows: list[sqlite3.Row] = []
    for attempt in attempts:
        if not attempt:
            continue
        found = db.execute(
            """
            SELECT p.*, bm25(products_fts) AS fts_rank
            FROM products_fts f
            JOIN products p ON p.rowid = f.rowid
            WHERE products_fts MATCH ?
            ORDER BY fts_rank
            LIMIT ?
            """,
            (safe_fts(attempt), max(limit * 5, 25)),
        ).fetchall()
        for row in found:
            code = str(row["code"])
            if code not in seen:
                seen.add(code)
                rows.append(row)
        if len(rows) >= limit * 2:
            break
    return rows


def parse_serving_grams(value: Any) -> float | None:
    match = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)\s*g\b", str(value or ""), re.I)
    if not match:
        return None
    grams = float(match.group(1))
    return grams if grams > 0 else None


def complete_nutrition(row: sqlite3.Row) -> bool:
    return all(row[column] is not None for column in NUTRIENT_COLUMNS)


def score_row(row: sqlite3.Row, query: str) -> tuple[float, float, list[str]]:
    query_tokens = tokens(query)
    name = normalize(str(row["product_name"] or ""))
    brand = normalize(str(row["brands"] or ""))
    generic = normalize(str(row["generic_name"] or ""))
    categories = normalize(str(row["categories_en"] or ""))
    haystack = f"{name} {brand} {generic} {categories}"
    matched = [token for token in query_tokens if token in haystack.split()]
    coverage = len(matched) / len(query_tokens)
    score = coverage * 100
    normalized_query = normalize(query)
    if normalized_query == name:
        score += 45
    if normalized_query == f"{brand} {name}" or normalized_query == f"{name} {brand}":
        score += 55
    if all(token in brand.split() for token in query_tokens):
        score += 15
    if complete_nutrition(row):
        score += 8
    if parse_serving_grams(row["serving_size"]):
        score += 4
    return score, coverage, matched


def finite(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def scaled_nutrition(row: sqlite3.Row, grams: float) -> dict[str, float | None]:
    factor = grams / 100
    energy_kj = finite(row["energy_100g"])
    sodium_g = finite(row["sodium_100g"])

    def scale(column: str) -> float | None:
        value = finite(row[column])
        return None if value is None else round(value * factor, 2)

    return {
        "calories": None if energy_kj is None else round(energy_kj / 4.184 * factor, 2),
        "protein_g": scale("proteins_100g"),
        "carbs_g": scale("carbohydrates_100g"),
        "fat_g": scale("fat_100g"),
        "fiber_g": scale("fiber_100g"),
        "sodium_mg": None if sodium_g is None else round(sodium_g * factor * 1000, 2),
    }


def serialize(row: sqlite3.Row, score: float, coverage: float) -> dict[str, Any]:
    serving_g = parse_serving_grams(row["serving_size"])
    return {
        "barcode": row["code"],
        "barcode_no_leading_zero": row["code_nozero"],
        "product_name": row["product_name"],
        "brand": row["brands"],
        "quantity": row["quantity"],
        "serving_size": row["serving_size"],
        "serving_grams": serving_g,
        "ingredients": row["ingredients_text"],
        "allergens": row["allergens_en"],
        "categories": row["categories_en"],
        "nutrition_per_100g": {
            "energy_kj": finite(row["energy_100g"]),
            "fat_g": finite(row["fat_100g"]),
            "saturated_fat_g": finite(row["saturated_fat_100g"]),
            "carbs_g": finite(row["carbohydrates_100g"]),
            "sugars_g": finite(row["sugars_100g"]),
            "fiber_g": finite(row["fiber_100g"]),
            "protein_g": finite(row["proteins_100g"]),
            "salt_g": finite(row["salt_100g"]),
            "sodium_g": finite(row["sodium_100g"]),
        },
        "nutrition_complete_for_log": complete_nutrition(row),
        "shard_suffix": row["shard"],
        "search_score": round(score, 2),
        "query_token_coverage": round(coverage, 3),
    }


def build_result(
    rows: list[sqlite3.Row],
    query: str,
    lookup_type: str,
    grams: float | None,
    limit: int,
    source_url: str,
    snapshot_date: str,
) -> dict[str, Any]:
    ranked: list[tuple[float, float, sqlite3.Row]] = []
    for row in rows:
        if lookup_type == "barcode":
            score, coverage = 200.0, 1.0
        else:
            score, coverage, _ = score_row(row, query)
        ranked.append((score, coverage, row))
    ranked.sort(key=lambda item: (-item[0], float(item[2]["fts_rank"] or 0)))
    candidates = [serialize(row, score, coverage) for score, coverage, row in ranked[:limit]]

    status = "not_found"
    reason = "No matching product was found."
    selected: dict[str, Any] | None = None
    if candidates:
        if lookup_type == "barcode":
            status, reason, selected = (
                "resolved",
                "Exact barcode match; nutrition is from the dated snapshot.",
                candidates[0],
            )
        else:
            top = candidates[0]
            runner_score = candidates[1]["search_score"] if len(candidates) > 1 else -100
            margin = top["search_score"] - runner_score
            if (
                top["query_token_coverage"] == 1
                and top["nutrition_complete_for_log"]
                and margin >= 20
            ):
                status, reason, selected = (
                    "resolved",
                    "Unique full-token text match with complete core nutrition.",
                    top,
                )
            else:
                status = "ambiguous"
                if top["query_token_coverage"] < 1:
                    reason = "The snapshot lacks one or more query terms; verify a barcode or current label."
                elif margin < 20:
                    reason = "Multiple similarly strong products matched; verify a barcode or package."
                else:
                    reason = "The best match lacks complete core nutrition."

    consumed_grams = grams
    if selected and consumed_grams is None:
        consumed_grams = selected["serving_grams"]
    compiler_item = None
    if selected and consumed_grams is not None:
        row = ranked[0][2]
        nutrition = scaled_nutrition(row, consumed_grams)
        if all(nutrition[key] is not None for key in ("calories", "protein_g", "carbs_g", "fat_g")):
            compiler_item = {
                "nutrition_match_type": "open_food_facts",
                "open_food_facts_nutrition": nutrition,
                "nutrition_row_id": selected["barcode"],
                "nutrition_grams_total": round(consumed_grams, 3),
                "source": "Open Food Facts",
                "source_url": source_url,
                "source_accessed": snapshot_date,
                "confidence": "Medium",
                "nutrition_match_note": (
                    f"Open Food Facts snapshot {snapshot_date}; exact barcode/product "
                    "identity should be checked against the current package when formulations may differ."
                ),
            }

    return {
        "status": status,
        "reason": reason,
        "lookup_type": lookup_type,
        "query": query,
        "snapshot_date": snapshot_date,
        "source_url": source_url,
        "selected": selected,
        "consumed_grams": consumed_grams,
        "compiler_item": compiler_item,
        "candidates": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=Path, help="SQLite index or .sqlite.gz download")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--barcode")
    group.add_argument("--search")
    parser.add_argument("--grams", type=float)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--source-url", default=DRIVE_FOLDER_URL)
    parser.add_argument("--snapshot-date", default=SNAPSHOT_DATE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.grams is not None and args.grams <= 0:
            raise LookupError("--grams must be positive")
        if not 1 <= args.limit <= 50:
            raise LookupError("--limit must be between 1 and 50")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.snapshot_date):
            raise LookupError("--snapshot-date must be YYYY-MM-DD")
        if not re.match(r"^https://", args.source_url):
            raise LookupError("--source-url must be HTTPS")
        db_path = ensure_sqlite(args.index, args.cache_dir)
        if not db_path.exists():
            raise LookupError(f"index does not exist: {db_path}")
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        if args.barcode:
            digits = "".join(character for character in args.barcode if character.isdigit())
            if not digits:
                raise LookupError("barcode has no digits")
            rows = db.execute(
                """
                SELECT p.*, 0.0 AS fts_rank FROM products p
                WHERE code = ? OR code_nozero = ?
                LIMIT ?
                """,
                (digits, digits.lstrip("0") or "0", args.limit),
            ).fetchall()
            result = build_result(
                rows,
                digits,
                "barcode",
                args.grams,
                args.limit,
                args.source_url,
                args.snapshot_date,
            )
        else:
            query = str(args.search).strip()
            rows = search_rows(db, query, args.limit)
            result = build_result(
                rows,
                query,
                "text",
                args.grams,
                args.limit,
                args.source_url,
                args.snapshot_date,
            )
        db.close()
        rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except (OSError, sqlite3.Error, LookupError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
