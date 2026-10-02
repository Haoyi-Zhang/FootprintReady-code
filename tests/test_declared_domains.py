"""Regression tests for declared numeric and restricted-policy domains."""
from __future__ import annotations

import copy
import unittest

from baseline import solve_sealed
from checker import CheckError, Semantics, check, check_trace
from model import InvalidModel, Model
from planner import solve


def unary_instance(*, modes: int = 1) -> dict:
    bounds = {
        "dram_read": [0, 0],
        "dram_write": [0, 0],
        "sp_read": [0, 0],
        "sp_write": [0, 0],
    }
    for mode in range(modes):
        bounds[f"op.unary.{mode}"] = [0, 0]
        bounds[f"op.binary.{mode}"] = [0, 0]
        for target in range(modes):
            if target != mode:
                bounds[f"cfg.{mode}.{target}"] = [10, 10]
    return {
        "name": f"declared-domain-{modes}-mode",
        "tile_type": {"dtype": "int16", "shape": [4, 4]},
        "inputs": ["x"],
        "outputs": ["v0"],
        "nodes": [{"op": "unary", "args": ["x"], "out": "v0", "modes": [0]}],
        "capacity": [2] * modes,
        "retain": [[True for _ in range(modes)] for _ in range(modes)],
        "footprint": {"x": 1, "v0": 1},
        "bounds": bounds,
    }


class DeclaredDomainTests(unittest.TestCase):
    def test_half_unit_operator_interval_is_outside_executable_domain(self):
        instance = unary_instance()
        instance["bounds"]["op.unary.0"] = [0.5, 0.5]
        with self.assertRaisesRegex(InvalidModel, "nonnegative integers"):
            Model(copy.deepcopy(instance))
        with self.assertRaisesRegex(CheckError, "nonnegative integers"):
            Semantics(copy.deepcopy(instance))

    def test_three_mode_home_sealed_guard_preserves_indirect_switch_risk(self):
        instance = unary_instance(modes=3)
        instance["nodes"][0]["modes"] = [2]
        instance["bounds"]["cfg.0.1"] = [1, 1]
        instance["bounds"]["cfg.1.2"] = [1, 1]
        # cfg.0.2 remains 10, so 0 -> 1 -> 2 is the legal cheaper route.
        solved = solve(copy.deepcopy(instance))
        self.assertTrue(solved["feasible"])
        result = solved["certificate"]
        self.assertEqual(result["upper"], 2)
        self.assertEqual(
            [action for action in result["trace"] if action[0] == "switch"],
            [["switch", 1], ["switch", 2]],
        )
        accepted = check(copy.deepcopy(instance), result)
        self.assertTrue(accepted["accepted"])
        self.assertEqual(accepted["upper"], 2)

        indirect = [
            ["switch", 1], ["switch", 2], ["load", "x"],
            ["run", 0], ["store", "v0"],
        ]
        direct = [
            ["switch", 2], ["load", "x"], ["run", 0], ["store", "v0"],
        ]
        self.assertEqual(check_trace(copy.deepcopy(instance), indirect)["upper"], 2)
        self.assertEqual(check_trace(copy.deepcopy(instance), direct)["upper"], 10)
        with self.assertRaisesRegex(ValueError, "at most two modes"):
            solve_sealed(copy.deepcopy(instance))


if __name__ == "__main__":
    unittest.main()
