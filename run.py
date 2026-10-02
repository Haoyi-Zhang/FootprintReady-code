#!/usr/bin/env python3
"""One-worker resumable validation over the frozen exact JSON inputs."""
from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from planner import solve, SearchLimit
from checker import check, check_trace, load_json
from oracle import optimum
from baseline import solve_sealed, solve_fixed_order


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int)
    args = parser.parse_args()

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "certificates").mkdir(exist_ok=True)
    fixtures = load_json(ROOT / "inputs" / "validation-cases.json")
    stop = len(fixtures) if args.stop is None else args.stop
    if not 0 <= args.start <= stop <= len(fixtures):
        parser.error("invalid slice")

    wall0, cpu0 = time.monotonic(), time.process_time()
    rows = []
    for index in range(args.start, stop):
        item = fixtures[index]
        instance, group = item["instance"], item["group"]
        wall, cpu = time.monotonic(), time.process_time()
        try:
            result = solve(instance)
        except SearchLimit as exc:
            rows.append({
                "index": index,
                "case": instance["name"],
                "group": group,
                "status": "limit",
                "reason": str(exc),
            })
            continue

        certificate = result["certificate"]
        checked = check(instance, certificate)
        expected_status = "feasible" if result["feasible"] else "infeasible"
        if checked["status"] != expected_status:
            raise AssertionError(f"checker status mismatch for {instance['name']}")
        if checked["states"] != result["states"]:
            raise AssertionError(f"checker state-count mismatch for {instance['name']}")
        if checked["edges"] != result["edges"]:
            raise AssertionError(f"checker edge-count mismatch for {instance['name']}")
        (out / "certificates" / f"{instance['name']}.json").write_text(
            json.dumps(certificate, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

        row = {
            "index": index,
            "case": instance["name"],
            "group": group,
            "nodes": len(instance["nodes"]),
            "capacity": instance["capacity"],
            "retain": instance["retain"][0][1],
            "cfg": instance["bounds"]["cfg.0.1"][1],
            "nonuniform_footprint": len(set(instance["footprint"].values())) > 1,
            "max_footprint": max(instance["footprint"].values()),
            "status": expected_status,
            "states": result["states"],
            "edges": result["edges"],
            "certificate_accepted": True,
        }
        if result["feasible"]:
            row.update(
                upper=checked["upper"],
                lower=checked["lower"],
                trace_actions=len(certificate["trace"]),
                run_order=[action[1] for action in certificate["trace"] if action[0] == "run"],
            )
            fixed = solve_fixed_order(instance)
            sealed = solve_sealed(instance)
            if fixed is None or sealed is None:
                raise AssertionError("comparison policy unexpectedly infeasible")
            if check_trace(instance, fixed["trace"])["upper"] != fixed["upper"]:
                raise AssertionError(f"fixed-order trace mismatch for {instance['name']}")
            if check_trace(instance, sealed["trace"])["upper"] != sealed["upper"]:
                raise AssertionError(f"home-sealed trace mismatch for {instance['name']}")
            if fixed["upper"] < certificate["upper"]:
                raise AssertionError(f"fixed-order policy beat unrestricted optimum for {instance['name']}")
            if sealed["upper"] < certificate["upper"]:
                raise AssertionError(f"home-sealed policy beat unrestricted optimum for {instance['name']}")
            row.update(
                fixed_order_upper=fixed["upper"],
                schedule_saved=fixed["upper"] - certificate["upper"],
                sealed_upper=sealed["upper"],
                sealed_saved=sealed["upper"] - certificate["upper"],
            )

        if len(instance["nodes"]) <= 5:
            exact = optimum(instance)
            expected = row.get("upper")
            if exact["upper"] != expected:
                raise AssertionError((instance["name"], exact, row))
            row.update(
                oracle_agrees=True,
                oracle_plans=exact["complete_plans"],
                oracle_visits=exact["branch_visits"],
            )

        row.update(
            wall_seconds=time.monotonic() - wall,
            cpu_seconds=time.process_time() - cpu,
        )
        rows.append(row)
        print(
            f"{index:03d} {instance['name']}: {row['status']} "
            f"states={row['states']} upper={row.get('upper')}",
            flush=True,
        )

    report = {
        "slice": [args.start, stop],
        "workers": 1,
        "cases": rows,
        "wall_seconds": time.monotonic() - wall0,
        "cpu_seconds": time.process_time() - cpu0,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    (out / f"chunk-{args.start}-{stop}.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    if any(row["status"] == "limit" for row in rows):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
