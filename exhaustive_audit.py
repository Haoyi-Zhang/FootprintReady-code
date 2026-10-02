#!/usr/bin/env python3
"""Exhaustive two-node audit of the declared finite fragment.

The universe is deliberately explicit and small enough to enumerate completely:
* inputs ``x`` and ``w``;
* exactly two topologically declared nodes;
* unary or commutative-shape binary argument multisets over available values;
* each node allowed in mode 0, mode 1, or either mode;
* uniform capacity 2, 3, or 4 abstract storage units;
* destructive or retaining cross-mode switches;
* three fixed footprint assignments.

For every member, the bit-mask producer, set-based checker, and non-memoized
normal-form oracle must agree on feasibility and, when feasible, exact upper cost.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from itertools import combinations_with_replacement
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from cases import make
from checker import check
from oracle import optimum
from planner import solve


def argument_shapes(values: list[str]) -> list[list[str]]:
    return [[value] for value in values] + [list(pair) for pair in combinations_with_replacement(values, 2)]


def instances():
    permissions = ([0], [1], [0, 1])
    footprint_patterns = (
        (1, 1, 1, 1),
        (1, 2, 2, 1),
        (2, 1, 1, 3),
    )
    serial = 0
    for args0 in argument_shapes(["x", "w"]):
        for args1 in argument_shapes(["x", "w", "v0"]):
            for modes0 in permissions:
                for modes1 in permissions:
                    for capacity in (2, 3, 4):
                        for retain in (False, True):
                            for pattern_index, units in enumerate(footprint_patterns):
                                case = make(
                                    f"audit-{serial:05d}",
                                    ["x", "w"],
                                    [args0, args1],
                                    capacity=capacity,
                                    retain=retain,
                                    cfg=9,
                                    footprints=dict(zip(("x", "w", "v0", "v1"), units)),
                                )
                                case["nodes"][0]["modes"] = list(modes0)
                                case["nodes"][1]["modes"] = list(modes1)
                                serial += 1
                                yield pattern_index, case


def audit():
    started = time.monotonic()
    cases = feasible = infeasible = 0
    states = edges = 0
    max_states = max_edges = 0
    oracle_visits = oracle_plans = 0
    by_footprint = {str(index): {"cases": 0, "feasible": 0, "infeasible": 0} for index in range(3)}

    for pattern_index, instance in instances():
        result = solve(instance)
        verdict = check(instance, result["certificate"])
        independent = optimum(instance)
        expected = verdict.get("upper") if result["feasible"] else None
        if independent["upper"] != expected:
            raise AssertionError((instance, verdict, independent))

        cases += 1
        states += result["states"]
        edges += result["edges"]
        max_states = max(max_states, result["states"])
        max_edges = max(max_edges, result["edges"])
        oracle_visits += independent["branch_visits"]
        oracle_plans += independent["complete_plans"]
        bucket = by_footprint[str(pattern_index)]
        bucket["cases"] += 1
        if result["feasible"]:
            feasible += 1
            bucket["feasible"] += 1
        else:
            infeasible += 1
            bucket["infeasible"] += 1

    return {
        "universe": {
            "inputs": ["x", "w"],
            "nodes": 2,
            "node_argument_rule": "all unary choices and binary multisets over values available at declaration",
            "mode_permissions_per_node": [[0], [1], [0, 1]],
            "uniform_capacities": [2, 3, 4],
            "cross_mode_retention": [False, True],
            "configuration_upper": 9,
            "footprint_assignments_x_w_v0_v1": [[1, 1, 1, 1], [1, 2, 2, 1], [2, 1, 1, 3]],
        },
        "cases": cases,
        "feasible": feasible,
        "infeasible": infeasible,
        "states": states,
        "edges": edges,
        "max_states_per_case": max_states,
        "max_edges_per_case": max_edges,
        "oracle_branch_visits": oracle_visits,
        "oracle_complete_plans": oracle_plans,
        "producer_checker_oracle_agree": True,
        "by_footprint_assignment": by_footprint,
        "wall_seconds": time.monotonic() - started,
        "timing_policy": "observational only; excluded from deterministic reproduction equality",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = audit()
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
