"""Standard-runner exposure of the representation-differential check."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from checker import load_json
from semantic_crosscheck import crosscheck


class SemanticDifferentialTests(unittest.TestCase):
    def test_all_frozen_reachable_states_and_edges(self):
        fixtures = load_json(ROOT / "inputs" / "validation-cases.json")
        report = crosscheck([item["instance"] for item in fixtures])
        self.assertEqual(report["cases"], len(fixtures))
        self.assertTrue(report["transition_sets_equal"])
        self.assertGreater(report["states"], 0)
        self.assertGreater(report["edges"], 0)


if __name__ == "__main__":
    unittest.main()
