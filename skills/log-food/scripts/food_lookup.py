#!/usr/bin/env python3
"""Rank food candidates from confirmed history and registered nutrition sources."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
import sqlite3
import tempfile
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "food_lookup_candidates.v1"
SOURCE_BONUS = {
    "Previous Food Log": 320.0,
    "Preferred Food Map": 220.0,
    "Open Food Facts": 120.0,
    "Canonical CSV": 30.0,
}
NUTRIENT_FIELDS = {
    "calories": ("Calories", "calories", "energy-kcal_100g", "energy_kcal_100g"),
    "protein_g": ("Protein g", "protein_g", "proteins_100g"),
    "carbs_g": ("Carbs g", "carbs_g", "carbohydrate [g]", "carbohydrates_100g"),
    "fat_g": ("Fat g", "fat_g", "fat [g]", "total_fat [g]", "fat_100g"),
    "fiber_g": ("Fiber g", "fiber_g", "fiber [g]", "fiber_100g"),
    "sodium_mg": ("Sodium mg", "sodium_mg", "sodium [mg]", "sodium_100g"),
}


class LookupError(ValueError):
    pass


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def tokens(value: Any) -> list[str]:
    return normalize(value).split()


def number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text or text.casefold() in {"none", "null", "nan"}:
        return None
    match = re.match(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", text.replace(",", ""))
    if not match:
        return None
    try:
        result = float(match.group())
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def first(record: dict[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        if name in record and record[name] not in (None, ""):
            return record[name]
    return None


def clean_number(value: float | None) -> int | float | None:
    if value is None:
        return None
    rounded = round(value, 2)
    return int(rounded) if rounded.is_integer() else rounded


def nutrition_from(record: dict[str, Any], per_100g: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, names in NUTRIENT_FIELDS.items():
        value = number(first(record, names))
        if key == "sodium_mg" and per_100g and value is not None:
            # Open Food Facts sodium_100g is grams; a canonical "sodium [mg]" field is already mg.
            source_name = next((name for name in names if record.get(name) not in (None, "")), "")
            if source_name == "sodium_100g":
                value *= 1000
        result[key] = clean_number(value)
    return result


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "\x1f".join(str(part or "") for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


@dataclass
class Candidate:
    candidate_id: str
    source: str
    name: str
    brand: str | None
    flavor: str | None
    barcode: str | None
    serving: dict[str, Any]
    nutrition: dict[str, Any]
    confidence: str | None
    source_identity: dict[str, Any]
    aliases: list[str]
    note: str | None
    search_text: str
    score: float = 0.0
    coverage: float = 0.0
    matched_terms: list[str] | None = None

    def public(self, choice: int) -> dict[str, Any]:
        return {
            "choice": choice,
            "candidate_id": self.candidate_id,
            "source": self.source,
            "name": self.name,
            "brand": self.brand,
            "flavor": self.flavor,
            "barcode": self.barcode,
            "serving": self.serving,
            "nutrition": self.nutrition,
            "confidence": self.confidence,
            "source_identity": self.source_identity,
            "aliases": self.aliases,
            "match": {
                "score": round(self.score, 2),
                "term_coverage": round(self.coverage, 3),
                "matched_terms": self.matched_terms or [],
                "note": self.note,
            },
        }


def read_json(path: Path) -> Any:
    try:
        if path.suffix == ".jsonl":
            records = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            current: dict[str, dict[str, Any]] = {}
            for record in records:
                if isinstance(record, dict) and record.get("entry_id"):
                    current[str(record["entry_id"])] = record
            return list(current.values())
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LookupError(f"cannot read JSON {path}: {exc}") from exc


def object_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "items", "values", "data", "mappings", "foods"):
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, dict)]
    return []


def history_candidates(path: Path) -> list[Candidate]:
    raw_rows = object_rows(read_json(path))
    rows: list[dict[str, Any]] = []
    for record in raw_rows:
        if isinstance(record.get("items"), list):
            if normalize(record.get("status", "Active")) != "active":
                continue
            for item in record["items"]:
                if not isinstance(item, dict):
                    continue
                nutrition = item.get("nutrition") if isinstance(item.get("nutrition"), dict) else {}
                rows.append({
                    "Status": record.get("status"),
                    "Confidence": item.get("confidence"),
                    "Item": item.get("item"),
                    "Description": record.get("description"),
                    "Original Text": record.get("original_text"),
                    "Quantity": item.get("quantity"),
                    "Unit": item.get("unit"),
                    "Edible Grams": item.get("edible_grams"),
                    "Item ID": item.get("item_id"),
                    "Entry ID": record.get("entry_id"),
                    "Nutrition Row ID": item.get("nutrition_row_id"),
                    "Source": item.get("source"),
                    "Notes": item.get("note"),
                    **nutrition,
                })
        else:
            rows.append(record)
    best: dict[str, Candidate] = {}
    for row in rows:
        if normalize(row.get("Status", "Active")) not in {"", "active"}:
            continue
        confidence = str(row.get("Confidence") or "").title()
        if confidence not in {"High", "Medium"}:
            continue
        name = str(row.get("Item") or row.get("Description") or "").strip()
        if not name:
            continue
        quantity = number(row.get("Quantity"))
        unit = str(row.get("Unit") or "").strip()
        grams = number(row.get("Edible Grams"))
        aliases = [
            text for text in (
                str(row.get("Description") or "").strip(),
                str(row.get("Original Text") or "").strip(),
            ) if text
        ]
        item_id = str(row.get("Item ID") or "").strip()
        entry_id = str(row.get("Entry ID") or "").strip()
        candidate = Candidate(
            candidate_id=stable_id("history", entry_id, item_id),
            source="Previous Food Log",
            name=name,
            brand=None,
            flavor=None,
            barcode=str(row.get("Nutrition Row ID") or "").strip() or None,
            serving={"quantity": clean_number(quantity), "unit": unit or None, "grams": clean_number(grams)},
            nutrition=nutrition_from(row),
            confidence=confidence,
            source_identity={"entry_id": entry_id, "item_id": item_id},
            aliases=aliases,
            note="Previously logged active component with confirmed nutrition.",
            search_text=" ".join([name, *aliases, str(row.get("Notes") or "")]),
        )
        key = normalize(f"{name} {quantity} {unit} {row.get('Source')}")
        previous = best.get(key)
        if previous is None or confidence == "High" and previous.confidence != "High":
            best[key] = candidate
    return list(best.values())


def walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def preferred_candidates(path: Path) -> list[Candidate]:
    payload = read_json(path)
    result: list[Candidate] = []
    seen: set[str] = set()
    for row in walk_dicts(payload):
        name = first(row, ("name", "food", "preferred_name", "canonical_name", "nutrition_name"))
        row_id = first(row, ("nutrition_row_id", "row_id", "canonical_row_id"))
        raw_aliases = first(row, ("aliases", "terms", "user_phrases"))
        aliases = [str(value) for value in raw_aliases] if isinstance(raw_aliases, list) else []
        if not name or not (row_id or aliases):
            continue
        candidate_id = stable_id("preferred", row_id, name, *aliases)
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        nutrition = row.get("nutrition") if isinstance(row.get("nutrition"), dict) else {}
        result.append(Candidate(
            candidate_id=candidate_id,
            source="Preferred Food Map",
            name=str(name),
            brand=str(row.get("brand") or "").strip() or None,
            flavor=str(row.get("flavor") or "").strip() or None,
            barcode=str(row.get("barcode") or "").strip() or None,
            serving={
                "quantity": clean_number(number(row.get("quantity"))),
                "unit": row.get("unit"),
                "grams": clean_number(number(first(row, ("grams", "edible_grams", "nutrition_grams_total")))),
            },
            nutrition=nutrition_from(nutrition),
            confidence=str(row.get("confidence") or "High").title(),
            source_identity={"nutrition_row_id": str(row_id) if row_id is not None else None},
            aliases=aliases,
            note=str(row.get("note") or row.get("match_note") or "").strip() or None,
            search_text=" ".join([str(name), *aliases, str(row.get("brand") or ""), str(row.get("flavor") or "")]),
        ))
    return result


def canonical_candidates(path: Path) -> list[Candidate]:
    result: list[Candidate] = []
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise LookupError(f"cannot read canonical CSV {path}: {exc}") from exc
    with handle:
        for row in csv.DictReader(handle):
            name = str(row.get("name") or "").strip()
            row_id = str(row.get("Unnamed: 0") or "").strip()
            if not name or not row_id:
                continue
            grams = number(row.get("serving_size [g]"))
            result.append(Candidate(
                candidate_id=f"canonical:{row_id}",
                source="Canonical CSV",
                name=name,
                brand=None,
                flavor=None,
                barcode=None,
                serving={"quantity": 1, "unit": "canonical serving", "grams": clean_number(grams)},
                nutrition=nutrition_from(row),
                confidence="High",
                source_identity={"nutrition_row_id": row_id},
                aliases=[],
                note="Generic canonical nutrition row.",
                search_text=name,
            ))
    return result


def sqlite_rows(index: Path, query_tokens: list[str], barcode: str | None, limit: int) -> list[dict[str, Any]]:
    temporary: tempfile.TemporaryDirectory[str] | None = None
    db_path = index
    try:
        if index.suffix == ".gz":
            temporary = tempfile.TemporaryDirectory(prefix="food-lookup-")
            db_path = Path(temporary.name) / "openfoodfacts_search.sqlite"
            with gzip.open(index, "rb") as source, db_path.open("wb") as destination:
                while chunk := source.read(1024 * 1024):
                    destination.write(chunk)
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        if barcode:
            digits = "".join(char for char in barcode if char.isdigit())
            rows = db.execute(
                "SELECT * FROM products WHERE code = ? OR code_nozero = ? LIMIT ?",
                (digits, digits.lstrip("0") or "0", limit),
            ).fetchall()
        else:
            safe = [token for token in query_tokens if token]
            if not safe:
                return []
            expression = " OR ".join(f'"{token}"*' for token in safe)
            rows = db.execute(
                """
                SELECT p.*
                FROM products_fts f
                JOIN products p ON p.rowid = f.rowid
                WHERE products_fts MATCH ?
                ORDER BY bm25(products_fts)
                LIMIT ?
                """,
                (expression, max(limit * 12, 50)),
            ).fetchall()
        db.close()
        return [dict(row) for row in rows]
    except (OSError, sqlite3.Error) as exc:
        raise LookupError(f"cannot query Open Food Facts index {index}: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.cleanup()


def openfoodfacts_candidates(index: Path, query_tokens: list[str], barcode: str | None, limit: int) -> list[Candidate]:
    result: list[Candidate] = []
    for row in sqlite_rows(index, query_tokens, barcode, limit):
        code = str(first(row, ("code", "code_nozero")) or "").strip()
        name = str(first(row, ("product_name", "generic_name", "name")) or "").strip()
        if not code or not name:
            continue
        brand = str(first(row, ("brands", "brand")) or "").strip() or None
        serving_text = str(first(row, ("serving_size", "serving")) or "").strip() or None
        serving_grams = number(first(row, ("serving_quantity", "serving_size_g")))
        result.append(Candidate(
            candidate_id=f"openfoodfacts:{code}",
            source="Open Food Facts",
            name=name,
            brand=brand,
            flavor=str(row.get("flavor") or "").strip() or None,
            barcode=code,
            serving={"quantity": 100, "unit": "g", "grams": 100, "label": serving_text},
            nutrition=nutrition_from(row, per_100g=True),
            confidence="Medium",
            source_identity={"barcode": code, "shard": row.get("shard")},
            aliases=[],
            note="Indexed snapshot candidate; verify against a current package label when available.",
            search_text=" ".join([
                name,
                brand or "",
                str(row.get("generic_name") or ""),
                str(row.get("categories") or ""),
            ]),
        ))
    return result


def term_similarity(term: str, haystack: str, hay_tokens: list[str]) -> float:
    if term in haystack:
        return 1.0
    wanted = tokens(term)
    if not wanted or not hay_tokens:
        return 0.0
    token_scores = []
    for query_token in wanted:
        token_scores.append(max(SequenceMatcher(None, query_token, candidate).ratio() for candidate in hay_tokens))
    return sum(token_scores) / len(token_scores)


def rank(candidate: Candidate, query_terms: list[str], barcode: str | None) -> Candidate:
    haystack = normalize(candidate.search_text)
    hay_tokens = haystack.split()
    matched: list[str] = []
    similarities: list[float] = []
    for term in query_terms:
        similarity = term_similarity(normalize(term), haystack, hay_tokens)
        similarities.append(similarity)
        if similarity >= 0.78:
            matched.append(term)
    coverage = len(matched) / len(query_terms) if query_terms else 0.0
    score = SOURCE_BONUS.get(candidate.source, 0.0)
    score += sum(value * 105.0 for value in similarities)
    score += coverage * 180.0
    whole_query = normalize(" ".join(query_terms))
    if whole_query and whole_query in haystack:
        score += 60.0
    if candidate.source == "Previous Food Log":
        score += 60.0 if candidate.confidence == "High" else 20.0
    if barcode and candidate.barcode:
        digits = "".join(char for char in barcode if char.isdigit())
        candidate_digits = "".join(char for char in candidate.barcode if char.isdigit())
        if digits == candidate_digits or digits.lstrip("0") == candidate_digits.lstrip("0"):
            score += 2000.0
            coverage = 1.0
    candidate.score = score
    candidate.coverage = coverage
    candidate.matched_terms = matched
    return candidate


def deduplicate(candidates: list[Candidate]) -> list[Candidate]:
    best: dict[str, Candidate] = {}
    for candidate in candidates:
        key = normalize(f"{candidate.name} {candidate.brand or ''} {candidate.barcode or ''} "
                        f"{candidate.serving.get('grams') or ''}")
        previous = best.get(key)
        if previous is None or candidate.score > previous.score:
            best[key] = candidate
    return list(best.values())


def decision(ranked: list[Candidate], barcode: str | None) -> dict[str, Any]:
    if not ranked:
        return {"mode": "no_match", "reason": "No candidate met the minimum match threshold."}
    top = ranked[0]
    margin = top.score - ranked[1].score if len(ranked) > 1 else top.score
    if barcode and top.barcode and top.coverage == 1.0:
        return {"mode": "auto", "candidate_id": top.candidate_id, "reason": "Exact barcode match."}
    if (
        top.source == "Previous Food Log"
        and top.confidence == "High"
        and top.coverage == 1.0
        and margin >= 80.0
    ):
        return {
            "mode": "auto",
            "candidate_id": top.candidate_id,
            "reason": "Unambiguous high-confidence prior Food Log match.",
        }
    return {
        "mode": "choose",
        "reason": "User selection is required for fuzzy or materially ambiguous matches.",
    }


def search(args: argparse.Namespace) -> dict[str, Any]:
    query_terms = [term.strip() for term in args.term if term.strip()]
    if not query_terms and not args.barcode:
        raise LookupError("search requires at least one --term or --barcode")
    candidates: list[Candidate] = []
    if args.history:
        candidates.extend(history_candidates(args.history))
    if args.preferred:
        candidates.extend(preferred_candidates(args.preferred))
    if args.openfoodfacts_index:
        candidates.extend(openfoodfacts_candidates(
            args.openfoodfacts_index,
            tokens(" ".join(query_terms)),
            args.barcode,
            args.limit,
        ))
    if args.canonical_csv:
        candidates.extend(canonical_candidates(args.canonical_csv))
    ranked = [rank(candidate, query_terms, args.barcode) for candidate in candidates]
    minimum = 1.0 if args.barcode else SOURCE_BONUS["Canonical CSV"] + 45.0
    minimum_coverage = 1.0 if len(query_terms) == 1 else 0.5
    ranked = [
        candidate for candidate in ranked
        if candidate.score >= minimum
        and (
            args.barcode
            or candidate.coverage >= minimum_coverage
            or candidate.source in {"Previous Food Log", "Preferred Food Map"} and candidate.coverage > 0
        )
    ]
    ranked = sorted(deduplicate(ranked), key=lambda item: (-item.score, item.name.casefold()))
    ranked = ranked[: args.limit]
    return {
        "schema_version": SCHEMA_VERSION,
        "query": {"terms": query_terms, "barcode": args.barcode},
        "decision": decision(ranked, args.barcode),
        "candidates": [candidate.public(index) for index, candidate in enumerate(ranked, start=1)],
    }


def select(args: argparse.Namespace) -> dict[str, Any]:
    payload = read_json(args.candidates)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise LookupError("candidate file has an unsupported schema version")
    choices = payload.get("candidates")
    if not isinstance(choices, list) or not choices:
        raise LookupError("candidate file contains no choices")
    selected = next((candidate for candidate in choices if candidate.get("choice") == args.choice), None)
    if selected is None:
        raise LookupError(f"choice must be one of 1..{len(choices)}")
    return {
        "status": "selected",
        "schema_version": "selected_food.v1",
        "query": payload.get("query"),
        "selected": selected,
    }


def write_result(payload: dict[str, Any], output: Path) -> None:
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    subparsers = root.add_subparsers(dest="command", required=True)

    find = subparsers.add_parser("search")
    find.add_argument("--term", action="append", default=[])
    find.add_argument("--barcode")
    find.add_argument("--history", type=Path)
    find.add_argument("--preferred", type=Path)
    find.add_argument("--canonical-csv", type=Path)
    find.add_argument("--openfoodfacts-index", type=Path)
    find.add_argument("--limit", type=int, default=8)
    find.add_argument("--output", type=Path, required=True)

    choose = subparsers.add_parser("select")
    choose.add_argument("--candidates", type=Path, required=True)
    choose.add_argument("--choice", type=int, required=True)
    choose.add_argument("--output", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "search":
            if args.limit < 1 or args.limit > 20:
                raise LookupError("--limit must be between 1 and 20")
            payload = search(args)
        else:
            payload = select(args)
        write_result(payload, args.output)
    except (LookupError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
