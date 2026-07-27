#!/usr/bin/env python3
"""Deterministic standard-library tests for plan_updates."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_updates import PlanError, build_plan


AS_OF = "2026-07-26"


def row(**overrides):
    value = {
        "row_number": 10,
        "item": "Rice",
        "nutrition_map_key": "white rice",
        "canonical_unit": "g",
        "confirmed_on_hand": 100,
        "status": "Confirmed",
        "last_confirmed": "2026-07-25",
        "notes": "existing note",
        "package_notes": "",
        "formula_g": '=IF(I10="Confirmed",E10-F10,0)',
    }
    value.update(overrides)
    return value


def observation(observation_id="observation-001", **overrides):
    value = {
        "observation_id": observation_id,
        "observed_name": "Rice",
        "quantity_state": "exact",
        "quantity": 50,
        "unit": "g",
        "confidence": 0.95,
        "match_reason": "label read",
    }
    value.update(overrides)
    return value


def document(*, observations, rows=None, capture_id="capture-0001", source_type="list", mode="additive"):
    return {
        "capture": {
            "capture_id": capture_id,
            "source_type": source_type,
            "mode": mode,
            "captured_at": "2026-07-26T10:00:00-07:00",
            "observations": observations,
        },
        "inventory": {"as_of": AS_OF, "rows": [row()] if rows is None else rows},
    }


class PlanUpdatesTests(unittest.TestCase):
    def test_exact_existing_item_addition(self):
        plan = build_plan(document(observations=[observation()]))
        operation = plan["operations"][0]
        self.assertEqual(operation["action"], "update")
        self.assertEqual(operation["row_number"], 10)
        self.assertEqual(operation["write_cells"]["E"], 150.0)
        self.assertEqual(operation["write_cells"]["I"], "Confirmed")

    def test_new_exact_item_creation(self):
        plan = build_plan(document(observations=[observation(
            observed_name="Black beans", allow_new=True, category="Legumes",
            storage="Pantry", canonical_unit="g", quantity=425,
        )]))
        operation = plan["operations"][0]
        self.assertEqual(operation["action"], "add")
        self.assertEqual(operation["row_number"], 11)
        self.assertEqual(operation["write_cells"]["A"], "Black beans")
        self.assertEqual(operation["write_cells"]["E"], 425.0)

    def test_receipt_duplicate_rejected(self):
        prior = row(notes="[capture:receipt-2026-001] previous receipt")
        with self.assertRaisesRegex(PlanError, "Duplicate capture_id"):
            build_plan(document(
                observations=[observation()], rows=[prior], capture_id="receipt-2026-001",
                source_type="receipt",
            ))

    def test_ambiguous_match_rejected(self):
        with self.assertRaisesRegex(PlanError, "ambiguous match candidates"):
            build_plan(document(observations=[observation(match_candidates=[10, 11])]))

    def test_incompatible_unit_rejected(self):
        with self.assertRaisesRegex(PlanError, "Incompatible unit dimensions"):
            build_plan(document(observations=[observation(quantity=1, unit="cup")]))

    def test_partial_photo_quantity_unknown(self):
        plan = build_plan(document(
            observations=[observation(quantity_state="unknown", quantity=None, unit=None)],
            source_type="photo", mode="snapshot",
        ))
        write = plan["operations"][0]["write_cells"]
        self.assertEqual(write["E"], 0)
        self.assertEqual(write["I"], "Quantity unknown")
        self.assertIsNone(write["J"])

    def test_overlapping_photo_deduplicates(self):
        first = observation(observation_id="photo-a", dedupe_key="shelf-rice")
        second = observation(
            observation_id="photo-b", dedupe_key="shelf-rice", evidence_refs=["photo-b.jpg"],
        )
        plan = build_plan(document(
            observations=[first, second], source_type="photo", mode="snapshot",
        ))
        self.assertEqual(len(plan["operations"]), 1)
        self.assertEqual(plan["summary"], {"updated": 1, "added": 0, "quantity_unknown": 0})

    def test_formula_column_g_is_preserved(self):
        existing = build_plan(document(observations=[observation()]))["operations"][0]
        self.assertNotIn("G", existing["write_cells"])

        added = build_plan(document(observations=[observation(
            observed_name="Lentils", allow_new=True, category="Legumes", storage="Pantry",
            canonical_unit="g", quantity=500,
        )]))["operations"][0]
        self.assertNotIn("G", added["write_cells"])
        self.assertIn("E11-F11", added["formula_g"])


if __name__ == "__main__":
    unittest.main()
