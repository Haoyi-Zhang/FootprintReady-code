"""Focused regression tests for weighted storage and transfer semantics."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cases import make
from checker import check, check_trace
from model import Model
from planner import solve


class FootprintSemanticsTests(unittest.TestCase):
    def test_transfer_and_operator_events_scale_in_units(self):
        instance = make(
            "weighted-events",
            ["x"],
            [["x"]],
            capacity=5,
            footprints={"x": 2, "v0": 3},
        )
        trace = [["load", "x"], ["run", 0], ["store", "v0"]]
        observed = check_trace(instance, trace)
        expected = {event: 0 for event in instance["bounds"]}
        expected.update({
            "dram_read": 2,
            "dram_write": 3,
            "sp_read": 5,
            "sp_write": 5,
            "op.unary.0": 1,
        })
        self.assertEqual(observed["counts"], expected)
        self.assertEqual(observed["upper"], 49)

    def test_fresh_output_must_fit_with_current_residents(self):
        instance = make(
            "weighted-capacity-failure",
            ["x"],
            [["x"]],
            capacity=4,
            footprints={"x": 2, "v0": 3},
        )
        result = solve(instance)
        self.assertFalse(result["feasible"])
        self.assertEqual(check(instance, result["certificate"])["status"], "infeasible")

    def test_retaining_switch_obeys_target_weighted_capacity(self):
        instance = make(
            "weighted-retaining-target",
            ["x"],
            [["x"]],
            capacity=5,
            retain=True,
            footprints={"x": 4, "v0": 1},
        )
        instance["capacity"] = [5, 3]
        model = Model(instance)
        load = next(step for step in model.successors(model.initial()) if step[0] == ["load", "x"])
        actions = [step[0] for step in model.successors(load[1])]
        self.assertNotIn(["switch", 1], actions)


if __name__ == "__main__":
    unittest.main()
