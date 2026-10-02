#!/usr/bin/env python3
"""Measure value ambiguity induced by coarser boundary-state projections."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from checker import load_json


def names(instance: dict) -> list[str]:
    return list(instance["inputs"]) + [node["out"] for node in instance["nodes"]]


def decode_mask(mask: int, ordered: list[str]) -> list[str]:
    return [name for bit, name in enumerate(ordered) if mask & (1 << bit)]


def projection(name: str, row: list, ordered: list[str], footprint: dict[str, int]):
    done, mode, resident, dirty, _ = row

    def units(mask):
        return sum(footprint[value] for bit, value in enumerate(ordered) if mask & (1 << bit))
    if name == "full":
        return (done, mode, resident, dirty)
    if name == "without_done":
        return (mode, resident, dirty)
    if name == "completion_count_only":
        return (done.bit_count(), mode, resident, dirty)
    if name == "without_mode":
        return (done, resident, dirty)
    if name == "without_dirty_identity":
        return (done, mode, resident, dirty.bit_count())
    if name == "without_dirty_state":
        return (done, mode, resident)
    if name == "occupancy_only":
        return (done, mode, resident.bit_count(), dirty.bit_count())
    if name == "footprint_totals_only":
        return (done, mode, units(resident), units(dirty))
    raise ValueError(name)


PROJECTIONS = (
    "full",
    "without_done",
    "completion_count_only",
    "without_mode",
    "without_dirty_identity",
    "without_dirty_state",
    "occupancy_only",
    "footprint_totals_only",
)


def label_token(label):
    return "dead" if label is None else label


def analyze(results_dir: Path):
    certificate_dir = results_dir / "certificates"
    certificate_paths = sorted(certificate_dir.glob("*.json"))
    if not certificate_paths:
        raise ValueError(f"no certificates found under {certificate_dir}")

    totals = {
        pname: {
            "projection": pname,
            "certificates": len(certificate_paths),
            "represented_states": 0,
            "abstract_groups": 0,
            "merged_groups": 0,
            "ambiguous_groups": 0,
            "finite_cost_ambiguous_groups": 0,
            "mixed_live_dead_groups": 0,
            "states_in_ambiguous_groups": 0,
            "cases_with_ambiguity": 0,
            "max_finite_spread": 0,
        }
        for pname in PROJECTIONS
    }
    witnesses: dict[str, dict | None] = {pname: None for pname in PROJECTIONS}

    for path in certificate_paths:
        certificate = load_json(path)
        instance = certificate["instance"]
        ordered_names = names(instance)
        footprint = instance["footprint"]
        rows = certificate["states"]
        for pname in PROJECTIONS:
            groups: dict[tuple, list[list]] = defaultdict(list)
            for row in rows:
                groups[projection(pname, row, ordered_names, footprint)].append(row)
            stat = totals[pname]
            stat["represented_states"] += len(rows)
            stat["abstract_groups"] += len(groups)
            case_ambiguous = False
            for key, members in groups.items():
                if len(members) > 1:
                    stat["merged_groups"] += 1
                distinct = {member[4] for member in members}
                if len(distinct) <= 1:
                    continue
                case_ambiguous = True
                stat["ambiguous_groups"] += 1
                stat["states_in_ambiguous_groups"] += len(members)
                finite = sorted({value for value in distinct if value is not None})
                mixed = None in distinct and bool(finite)
                finite_ambiguous = len(finite) > 1
                if mixed:
                    stat["mixed_live_dead_groups"] += 1
                if finite_ambiguous:
                    stat["finite_cost_ambiguous_groups"] += 1
                    spread = finite[-1] - finite[0]
                    stat["max_finite_spread"] = max(stat["max_finite_spread"], spread)
                else:
                    spread = 0

                score = (1 if mixed else 0, spread, len(distinct), len(members))
                prior = witnesses[pname]
                if prior is None or score > tuple(prior["score"]):
                    decoded = []
                    for done, mode, resident, dirty, label in sorted(
                        members,
                        key=lambda row: (
                            row[4] is None,
                            -1 if row[4] is None else row[4],
                            row[0], row[1], row[2], row[3],
                        ),
                    ):
                        decoded.append({
                            "done_mask": done,
                            "done_nodes": [
                                index for index in range(len(instance["nodes"]))
                                if done & (1 << index)
                            ],
                            "mode": mode,
                            "resident_mask": resident,
                            "resident": decode_mask(resident, ordered_names),
                            "dirty_mask": dirty,
                            "dirty": decode_mask(dirty, ordered_names),
                            "resident_units": sum(footprint[value] for value in decode_mask(resident, ordered_names)),
                            "dirty_units": sum(footprint[value] for value in decode_mask(dirty, ordered_names)),
                            "continuation_upper": label_token(label),
                        })
                    witnesses[pname] = {
                        "score": list(score),
                        "case": instance["name"],
                        "projection_key": list(key),
                        "labels": sorted(
                            (label_token(value) for value in distinct),
                            key=lambda value: (
                                isinstance(value, str),
                                value if isinstance(value, int) else str(value),
                            ),
                        ),
                        "members": decoded,
                    }
            if case_ambiguous:
                stat["cases_with_ambiguity"] += 1

    csv_path = results_dir / "abstraction-ablation.csv"
    fields = list(next(iter(totals.values())).keys())
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(totals[pname] for pname in PROJECTIONS)

    payload = {
        "scope": (
            "complete accepted certificate closures for the frozen ready-set batch; "
            "ambiguity means a projection merges represented legal states with "
            "different exact continuation labels"
        ),
        "projections": [totals[pname] for pname in PROJECTIONS],
        "witnesses": witnesses,
    }
    (results_dir / "abstraction-ablation.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", "--results", dest="results", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    print(json.dumps(analyze(args.results.resolve()), indent=2))


if __name__ == "__main__":
    main()
