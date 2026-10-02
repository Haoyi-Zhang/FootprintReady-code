#!/usr/bin/env python3
"""Run the bounded one-worker intake and ready-set discrimination pilot."""
from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from baseline import solve_fixed_order, solve_sealed
from cases import boundary_case, footprint_identity_case, pilot_case, schedule_cases
from checker import CheckError, check, check_trace, load_json
from oracle import optimum
from planner import solve


def run(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    wall0, cpu0 = time.monotonic(), time.process_time()
    selected = [
        boundary_case(False),
        boundary_case(True),
        pilot_case(),
        schedule_cases()[-1],
        footprint_identity_case(),
    ]
    for instance in selected:
        frozen = load_json(ROOT / "inputs" / f"{instance['name']}.json")
        if frozen != instance:
            raise AssertionError(f"pilot input differs from frozen input: {instance['name']}")
        wall, cpu = time.monotonic(), time.process_time()
        answer = solve(instance)
        if not answer["feasible"]:
            raise AssertionError(f"pilot instance unexpectedly infeasible: {instance['name']}")
        verdict = check(instance, answer["certificate"])
        exact = optimum(instance)
        fixed = solve_fixed_order(instance)
        sealed = solve_sealed(instance)
        if fixed is None or sealed is None:
            raise AssertionError("pilot comparison policy unexpectedly infeasible")
        if exact["upper"] != verdict["upper"]:
            raise AssertionError("pilot oracle disagreement")
        if check_trace(instance, fixed["trace"])["upper"] != fixed["upper"]:
            raise AssertionError("pilot fixed-order trace disagreement")
        if check_trace(instance, sealed["trace"])["upper"] != sealed["upper"]:
            raise AssertionError("pilot home-sealed trace disagreement")
        (out / f"{instance['name']}-certificate.json").write_text(
            json.dumps(answer["certificate"], separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        rows.append({
            "case": instance["name"],
            **verdict,
            "fixed_order_upper": fixed["upper"],
            "sealed_upper": sealed["upper"],
            **{f"oracle_{key}": value for key, value in exact.items()},
            "wall_seconds": time.monotonic() - wall,
            "cpu_seconds": time.process_time() - cpu,
        })

    invalid = [
        ["load", "x"], ["run", 0], ["switch", 1],
        ["load", "v0"], ["run", 1], ["store", "v1"],
    ]
    try:
        check_trace(boundary_case(False), invalid)
    except CheckError as exc:
        negative = {"rejected": True, "reason": str(exc)}
    else:
        raise AssertionError("dirty flush was accepted")

    report = {
        "workers": 1,
        "cases": rows,
        "dirty_flush_negative_control": negative,
        "wall_seconds": time.monotonic() - wall0,
        "cpu_seconds": time.process_time() - cpu0,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "scope": "abstract finite graph checking only; no tensor execution or physical energy measurement",
    }
    (out / "pilot.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    report = run(args.out.resolve())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
