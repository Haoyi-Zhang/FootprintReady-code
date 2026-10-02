#!/usr/bin/env python3
"""Reconcile finite observations, certificates, differential checks, and tables."""
from __future__ import annotations

import argparse
import csv
import json
import resource
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from checker import check, load_json
from test_certificates import run_tests
from semantic_crosscheck import crosscheck
from analyze_abstractions import analyze as analyze_abstractions


def _value_names(instance):
    return list(instance["inputs"]) + [node["out"] for node in instance["nodes"]]


def _decode(mask, ordered):
    return [name for index, name in enumerate(ordered) if mask & (1 << index)]


def _identity_witness(certificate, *, weighted=False):
    instance = certificate["instance"]
    ordered = _value_names(instance)
    groups = defaultdict(list)
    for record in certificate["states"]:
        done, mode, resident, dirty, _ = record
        key = (done, mode, resident.bit_count(), dirty.bit_count()) if weighted else (
            done, mode, resident, dirty.bit_count()
        )
        groups[key].append(record)
    candidates = []
    for key, members in groups.items():
        finite = [record for record in members if record[4] is not None]
        values = {record[4] for record in finite}
        if len(values) > 1:
            candidates.append((max(values) - min(values), key, finite))
    if not candidates:
        raise AssertionError("identity witness disappeared")
    spread, key, members = max(candidates, key=lambda item: item[0])
    members = sorted(members, key=lambda record: record[4])
    return {
        "done_mask": key[0],
        "done_nodes": [
            index for index in range(len(instance["nodes"]))
            if key[0] & (1 << index)
        ],
        "mode": key[1],
        "resident_count": key[2] if weighted else len(_decode(key[2], ordered)),
        "dirty_count": key[3],
        "alternatives": [
            {
                "resident": _decode(record[2], ordered),
                "dirty": _decode(record[3], ordered),
                "resident_units": sum(instance["footprint"][name] for name in _decode(record[2], ordered)),
                "dirty_units": sum(instance["footprint"][name] for name in _decode(record[3], ordered)),
                "continuation_upper": record[4],
            }
            for record in members
        ],
        "spread": spread,
    }


def summarize(out):
    start = time.process_time()
    inputs = load_json(ROOT / "inputs" / "validation-cases.json")
    chunks = [load_json(path) for path in sorted(out.glob("chunk-*.json"))]
    rows = sorted((row for chunk in chunks for row in chunk["cases"]), key=lambda row: row["index"])
    if [row["index"] for row in rows] != list(range(len(inputs))):
        raise ValueError("missing, overlapping, or out-of-range validation chunks")

    accepted_status = defaultdict(int)
    for row, item in zip(rows, inputs):
        instance = item["instance"]
        if row["case"] != instance["name"]:
            raise AssertionError("case order/name mismatch")
        if row["status"] not in ("feasible", "infeasible"):
            raise AssertionError(f"invalid case status: {row['case']}")
        certificate = load_json(out / "certificates" / f"{row['case']}.json")
        verdict = check(instance, certificate)
        if verdict["status"] != row["status"]:
            raise AssertionError(f"certificate status mismatch: {row['case']}")
        if verdict["states"] != row["states"] or verdict["edges"] != row["edges"]:
            raise AssertionError(f"certificate graph-size mismatch: {row['case']}")
        if row["status"] == "feasible":
            if verdict["upper"] != row["upper"]:
                raise AssertionError(f"certificate cost mismatch: {row['case']}")
        accepted_status[row["status"]] += 1

    lookup = {row["case"]: row for row in rows}
    capacity_pairs = retention_pairs = 0
    families = ("chain", "diamond", "residual", "shared", "wide", "fanin")
    for family in families:
        for cfg in (0, 9, 40):
            for keep in (0, 1):
                if lookup[f"{family}-4-{keep}-{cfg}"]["upper"] > lookup[f"{family}-3-{keep}-{cfg}"]["upper"]:
                    raise AssertionError("capacity monotonicity check failed")
                capacity_pairs += 1
            for capacity in (3, 4):
                if lookup[f"{family}-{capacity}-1-{cfg}"]["upper"] > lookup[f"{family}-{capacity}-0-{cfg}"]["upper"]:
                    raise AssertionError("retention monotonicity check failed")
                retention_pairs += 1

    widths = (0, 1, 3, 7)
    for lower_width, upper_width in zip(widths, widths[1:]):
        if lookup[f"interval-{lower_width}"]["upper"] > lookup[f"interval-{upper_width}"]["upper"]:
            raise AssertionError("interval sensitivity check failed")

    identity_certificate = load_json(out / "certificates" / "dirty-identity.json")
    identity_witness = _identity_witness(identity_certificate, weighted=False)
    footprint_certificate = load_json(out / "certificates" / "footprint-identity.json")
    footprint_witness = _identity_witness(footprint_certificate, weighted=True)

    mutations = run_tests()
    (out / "mutations.json").write_text(json.dumps(mutations, indent=2) + "\n", encoding="utf-8")

    differential = crosscheck([item["instance"] for item in inputs])
    (out / "semantic-differential.json").write_text(
        json.dumps(differential, indent=2) + "\n",
        encoding="utf-8",
    )

    feasible = [row for row in rows if row["status"] == "feasible"]
    infeasible = [row for row in rows if row["status"] == "infeasible"]
    schedule_rows = [row for row in rows if row["group"] == "schedule"]
    schedule_improved = [row for row in schedule_rows if row["schedule_saved"] > 0]
    schedule_reference = lookup["schedule-4-1-40"]

    family_table = []
    for family in families:
        destructive = lookup[f"{family}-3-0-9"]
        retaining = lookup[f"{family}-3-1-9"]
        family_table.append({
            "family": family,
            "sealed": destructive["sealed_upper"],
            "fixed": destructive["fixed_order_upper"],
            "flush": destructive["upper"],
            "retain": retaining["upper"],
            "flush_states": destructive["states"],
        })
    with (out / "family-costs.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(family_table[0]))
        writer.writeheader()
        writer.writerows(family_table)

    intervals = [
        {
            "radius": width,
            "lower": lookup[f"interval-{width}"]["lower"],
            "upper": lookup[f"interval-{width}"]["upper"],
        }
        for width in widths
    ]
    with (out / "interval-costs.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["radius", "lower", "upper"])
        writer.writeheader()
        writer.writerows(intervals)

    schedule_table = [
        {
            "case": row["case"],
            "capacity": row["capacity"][0],
            "retain": int(row["retain"]),
            "cfg": row["cfg"],
            "ready": row["upper"],
            "fixed": row["fixed_order_upper"],
            "sealed": row["sealed_upper"],
            "saved_vs_fixed": row["schedule_saved"],
            "run_order": "-".join(str(value) for value in row["run_order"]),
        }
        for row in schedule_rows
    ]
    with (out / "schedule-costs.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(schedule_table[0]))
        writer.writeheader()
        writer.writerows(schedule_table)

    footprint_rows = [
        {
            "case": row["case"],
            "retain": int(row["retain"]),
            "cfg": row["cfg"],
            "capacity": row["capacity"][0],
            "upper": row.get("upper", ""),
            "status": row["status"],
            "states": row["states"],
            "edges": row["edges"],
        }
        for row in rows if row["group"] in ("footprint", "footprint-identity")
    ]
    with (out / "footprint-costs.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(footprint_rows[0]))
        writer.writeheader()
        writer.writerows(footprint_rows)

    ablation = analyze_abstractions(out)
    report = {
        "case_count": len(rows),
        "feasible": len(feasible),
        "infeasible": len(infeasible),
        "certificate_count": len(rows),
        "feasible_certificates": accepted_status["feasible"],
        "infeasible_certificates": accepted_status["infeasible"],
        "oracle_comparisons": sum(row.get("oracle_agrees", False) for row in rows),
        "oracle_plans_total": sum(row.get("oracle_plans", 0) for row in rows),
        "oracle_visits_total": sum(row.get("oracle_visits", 0) for row in rows),
        "max_states": max(row["states"] for row in rows),
        "max_edges": max(row["edges"] for row in rows),
        "total_states_across_cases": sum(row["states"] for row in rows),
        "total_edges_across_cases": sum(row["edges"] for row in rows),
        "capacity_pairs": capacity_pairs,
        "retention_pairs": retention_pairs,
        "interval_pairs": len(widths) - 1,
        "mutations_rejected": mutations["mutations_rejected"],
        "semantic_differential": differential,
        "identity_example": identity_witness,
        "footprint_identity_example": footprint_witness,
        "nonuniform_footprint_cases": sum(row["nonuniform_footprint"] for row in rows),
        "schedule_cases": len(schedule_rows),
        "schedule_improved_cases": len(schedule_improved),
        "schedule_max_saved": max(row["schedule_saved"] for row in schedule_rows),
        "schedule_reference": {
            "case": schedule_reference["case"],
            "ready": schedule_reference["upper"],
            "fixed": schedule_reference["fixed_order_upper"],
            "sealed": schedule_reference["sealed_upper"],
            "run_order": schedule_reference["run_order"],
        },
        "batch_cpu_seconds": sum(chunk["cpu_seconds"] for chunk in chunks),
        "batch_wall_seconds_sum": sum(chunk["wall_seconds"] for chunk in chunks),
        "batch_peak_rss_kib": max(chunk["peak_rss_kib"] for chunk in chunks),
        "scope": (
            "synthetic finite ready-set action-cost models; not tensor execution, "
            "hardware energy, calibrated workload evidence, or scalability evidence"
        ),
        "abstraction_ablation": {
            row["projection"]: {
                "ambiguous_groups": row["ambiguous_groups"],
                "cases_with_ambiguity": row["cases_with_ambiguity"],
                "max_finite_spread": row["max_finite_spread"],
            }
            for row in ablation["projections"]
        },
        "summary_cpu_seconds": time.process_time() - start,
        "summary_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    summarize(parser.parse_args().out.resolve())
