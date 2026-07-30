#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from food_log_compiler import compile_entry, load_database
from food_log_jsonl import (
    append_record,
    current_records,
    delete_entry,
    read_records,
    summarize,
)
from migrate_food_log_csv import LEGACY_HEADERS, migrate
from unit_conversions import ConversionError, base_quantity, edible_grams


class FoodLogJsonlTests(unittest.TestCase):
    def raw_record(self) -> dict:
        return {
            "schema_version": "food_log.meal.v1",
            "record_type": "meal",
            "entry_id": "meal-test",
            "revision": 1,
            "status": "Active",
            "logged_at": "2026-07-29T08:00:00-07:00",
            "local_date": "2026-07-29",
            "meal": "Breakfast",
            "description": "Test breakfast",
            "original_text": "I ate a test breakfast",
            "planned_meal_id": None,
            "last_updated": "2026-07-29T09:00:00-07:00",
            "items": [
                {
                    "item_id": "item-test",
                    "item": "Test food",
                    "quantity": 1,
                    "unit": "count",
                    "base_quantity": {"amount": 1, "unit": "count"},
                    "edible_grams": 50,
                    "nutrition": {
                        "calories": 100,
                        "protein_g": 10,
                        "carbs_g": 5,
                        "fat_g": 4,
                        "fiber_g": 1,
                        "sodium_mg": 20,
                    },
                    "nutrition_row_id": "1",
                    "nutrition_match": "Exact",
                    "source": "Canonical CSV",
                    "confidence": "High",
                    "note": None,
                    "source_url": None,
                    "source_accessed": None,
                }
            ],
            "totals": {
                "calories": 100,
                "protein_g": 10,
                "carbs_g": 5,
                "fat_g": 4,
                "fiber_g": 1,
                "sodium_mg": 20,
            },
            "known_nutrition_subtotal": {
                "calories": 100,
                "protein_g": 10,
                "carbs_g": 5,
                "fat_g": 4,
                "fiber_g": 1,
                "sodium_mg": 20,
            },
        }

    def test_append_dedupe_correction_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "food-log-2026-07-29.jsonl"
            record = self.raw_record()
            self.assertEqual(append_record(path, record)["result"], "appended")
            self.assertEqual(append_record(path, record)["result"], "duplicate")

            corrected = json.loads(json.dumps(record))
            corrected["description"] = "Corrected breakfast"
            corrected["last_updated"] = "2026-07-29T09:05:00-07:00"
            result = append_record(path, corrected, correction=True)
            self.assertEqual(result["record"]["revision"], 2)

            deleted = delete_entry(
                path, "meal-test", "2026-07-29T09:10:00-07:00"
            )
            self.assertEqual(deleted["record"]["revision"], 3)
            records = read_records(path)
            self.assertEqual(len(records), 3)
            self.assertEqual(current_records(records), [])
            self.assertEqual(summarize(records)["meal_count"], 0)

    def test_unit_conversion(self) -> None:
        self.assertEqual(base_quantity(2, "tablespoons"), (30, "ml"))
        self.assertEqual(edible_grams(2, "tbsp", grams_per_unit=10), 20)
        self.assertEqual(edible_grams(0.25, "cup", grams_per_unit=120), 30)
        with self.assertRaises(ConversionError):
            edible_grams(2, "tbsp", grams_per_unit=10, explicit_grams=25)

    def test_compiler_emits_jsonl_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            csv_path = Path(temporary) / "nutrition.csv"
            csv_path.write_text(
                "Unnamed: 0,name,serving_size [g],calories,protein [g],"
                "carbohydrate [g],fat [g],fiber [g],sodium [mg]\n"
                "1,Chia seeds,100,486,16.5,42.1,30.7,34.4,16\n",
                encoding="utf-8",
            )
            database = load_database(csv_path, {})
            raw = {
                "logged_at": "2026-07-29T08:00:00-07:00",
                "local_date": "2026-07-29",
                "meal": "Breakfast",
                "description": "Chia",
                "original_text": "2 tbsp chia",
                "last_updated": "2026-07-29T09:00:00-07:00",
                "items": [
                    {
                        "item": "Chia seeds",
                        "quantity": 2,
                        "unit": "tbsp",
                        "grams_per_unit": 10,
                        "nutrition_row_id": 1,
                        "nutrition_match_type": "exact",
                        "source": "Canonical CSV",
                        "confidence": "High",
                    }
                ],
            }
            result = compile_entry(raw, database)
            self.assertEqual(result["schema_version"], "food_log.meal.v1")
            self.assertNotIn("sheet" + "_rows", result)
            self.assertEqual(result["items"][0]["base_quantity"], {"amount": 30, "unit": "ml"})
            self.assertEqual(result["items"][0]["edible_grams"], 20)
            self.assertEqual(result["totals"]["calories"], 97.2)

    def test_legacy_csv_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "legacy.csv"
            row = {header: "" for header in LEGACY_HEADERS}
            row.update(
                {
                    "Entry ID": "legacy-meal",
                    "Item ID": "legacy-item",
                    "Logged At": "2026-07-28T12:00:00-07:00",
                    "Local Date": "2026-07-28",
                    "Meal": "Lunch",
                    "Description": "Legacy lunch",
                    "Item": "Beans",
                    "Quantity": "100",
                    "Unit": "g",
                    "Edible Grams": "100",
                    "Calories": "120",
                    "Protein g": "8",
                    "Carbs g": "20",
                    "Fat g": "1",
                    "Fiber g": "7",
                    "Sodium mg": "10",
                    "Nutrition Row ID": "2",
                    "Nutrition Match": "Exact",
                    "Source": "Canonical CSV",
                    "Confidence": "High",
                    "Original Text": "I had beans",
                    "Last Updated": "2026-07-28T12:10:00-07:00",
                    "Status": "Active",
                }
            )
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=LEGACY_HEADERS)
                writer.writeheader()
                writer.writerow(row)
            result = migrate(source, root / "out")
            self.assertEqual(result, {"files_written": 1, "records_written": 1})
            migrated = read_records(root / "out" / "food-log-2026-07-28.jsonl")
            self.assertEqual(migrated[0]["entry_id"], "legacy-meal")


if __name__ == "__main__":
    unittest.main()
