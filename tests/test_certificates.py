"""Benign self-contained certificate corruptions and metamorphic checks."""
from __future__ import annotations

from copy import deepcopy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cases import boundary_case, make, schedule_cases
from planner import solve
from checker import check, check_trace, load_json, CheckError


def run_tests():
    instance = boundary_case(False)
    certificate = solve(instance)["certificate"]
    tests = []
    all_done = (1 << len(instance["nodes"])) - 1

    def rejected(name, subject, bound_instance, edit):
        damaged = deepcopy(subject)
        edit(damaged)
        try:
            check(bound_instance, damaged)
        except CheckError as exc:
            tests.append({"name": name, "rejected": True, "reason": str(exc)})
        else:
            raise AssertionError(f"mutation survived: {name}")

    def rejected_instance(name, edit):
        damaged_instance = deepcopy(instance)
        damaged_certificate = deepcopy(certificate)
        edit(damaged_instance)
        damaged_certificate["instance"] = deepcopy(damaged_instance)
        try:
            check(damaged_instance, damaged_certificate)
        except CheckError as exc:
            tests.append({"name": name, "rejected": True, "reason": str(exc)})
        else:
            raise AssertionError(f"malformed instance survived: {name}")

    rejected("understated_upper", certificate, instance, lambda c: c.update(upper=c["upper"] - 1))
    rejected("overstated_lower", certificate, instance, lambda c: c.update(lower=c["lower"] + 1))
    rejected("missing_count", certificate, instance, lambda c: c["counts"].pop("sp_read"))
    rejected("forged_count", certificate, instance, lambda c: c["counts"].update(dram_write=0))
    rejected("boolean_count", certificate, instance, lambda c: c["counts"].update(sp_read=True))
    rejected("negative_count", certificate, instance, lambda c: c["counts"].update(sp_read=-1))
    rejected("omitted_successor", certificate, instance, lambda c: c["states"].pop(1))
    rejected("omitted_source", certificate, instance, lambda c: c["states"].pop(0))
    rejected("duplicate_state", certificate, instance, lambda c: c["states"].append(c["states"][0][:]))
    rejected(
        "extraneous_unreachable_goal", certificate, instance,
        lambda c: c["states"].append([all_done, 0, 0, 0, 0]),
    )
    rejected(
        "dependency_open_completed_set", certificate, instance,
        lambda c: c["states"].append([2, 0, 0, 0, None]),
    )
    rejected("future_resident", certificate, instance, lambda c: c["states"][0].__setitem__(2, 4))
    rejected("dirty_not_resident", certificate, instance, lambda c: c["states"][0].__setitem__(3, 1))
    rejected("boolean_mask", certificate, instance, lambda c: c["states"][0].__setitem__(2, False))
    rejected("negative_potential", certificate, instance, lambda c: c["states"][1].__setitem__(4, -1))
    rejected("source_declared_dead", certificate, instance, lambda c: c["states"][0].__setitem__(4, None))
    rejected("inflated_potential", certificate, instance, lambda c: c["states"][1].__setitem__(4, 10**9))
    goal_index = next(i for i, row in enumerate(certificate["states"]) if row[0] == all_done and row[3] == 0)
    rejected("nonzero_goal_potential", certificate, instance, lambda c: c["states"][goal_index].__setitem__(4, 1))
    rejected("missing_terminal_store", certificate, instance, lambda c: c["trace"].pop())
    rejected("unknown_action", certificate, instance, lambda c: c["trace"].__setitem__(0, ["teleport", "x"]))
    switch_index = next(i for i, action in enumerate(certificate["trace"]) if action[0] == "switch")
    rejected("boolean_switch", certificate, instance, lambda c: c["trace"].__setitem__(switch_index, ["switch", True]))
    run_index = next(i for i, action in enumerate(certificate["trace"]) if action[0] == "run")
    rejected("invalid_run_node", certificate, instance, lambda c: c["trace"].__setitem__(run_index, ["run", 99]))
    rejected("changed_model_cost", certificate, instance, lambda c: c["instance"]["bounds"].update(dram_read=[0, 0]))
    rejected("changed_model_footprint", certificate, instance, lambda c: c["instance"]["footprint"].update(x=2))
    rejected("changed_model_retention", certificate, instance, lambda c: c["instance"]["retain"][0].__setitem__(1, True))
    rejected("numeric_boolean_binding", certificate, instance, lambda c: c["instance"]["bounds"].update(sp_read=[True, True]))
    rejected("unknown_certificate_field", certificate, instance, lambda c: c.update(unchecked=True))
    rejected("empty_state_certificate", certificate, instance, lambda c: c.update(states=[]))
    rejected("wrong_trace_type", certificate, instance, lambda c: c.update(trace="not a trace"))
    rejected("wrong_state_type", certificate, instance, lambda c: c.update(states={}))
    rejected("malformed_record", certificate, instance, lambda c: c["states"].__setitem__(0, [0]))
    rejected("noninteger_potential", certificate, instance, lambda c: c["states"][0].__setitem__(4, 52.0))
    rejected("feasible_status_flip", certificate, instance, lambda c: c.update(status="infeasible"))
    rejected("missing_status", certificate, instance, lambda c: c.pop("status"))
    rejected("unknown_status", certificate, instance, lambda c: c.update(status="optimal"))

    rejected_instance("missing_footprint_value", lambda x: x["footprint"].pop("x"))
    rejected_instance("extra_footprint_value", lambda x: x["footprint"].update(ghost=1))
    rejected_instance("boolean_footprint", lambda x: x["footprint"].update(x=True))
    rejected_instance("oversized_footprint", lambda x: x["footprint"].update(x=17))
    rejected_instance("zero_capacity", lambda x: x["capacity"].__setitem__(0, 0))

    # Duplicate keys and non-finite constants must not be accepted by the JSON loader.
    with tempfile.TemporaryDirectory(prefix="contract-json-") as tmp:
        path = Path(tmp) / "bad.json"
        for name, text in (
            ("duplicate_json_key", '{"upper":52,"upper":0}'),
            ("nonfinite_json", '{"upper":NaN}'),
        ):
            path.write_text(text, encoding="utf-8")
            try:
                load_json(path)
            except CheckError as exc:
                tests.append({"name": name, "rejected": True, "reason": str(exc)})
            else:
                raise AssertionError(name)

    # An explicitly illegal destructive switch loses an unbacked intermediate.
    bad_trace = [
        ["load", "x"], ["run", 0], ["switch", 1],
        ["load", "v0"], ["run", 1], ["store", "v1"],
    ]
    try:
        check_trace(instance, bad_trace)
    except CheckError as exc:
        tests.append({"name": "dirty_flush", "rejected": True, "reason": str(exc)})
    else:
        raise AssertionError("dirty flush accepted")

    # A one-node binary operator cannot execute with capacity two because its
    # two distinct operands and fresh result must coexist.
    impossible = make("infeasible-mutation", ["x", "w"], [["x", "w"]], capacity=2)
    impossible_result = solve(impossible)
    assert not impossible_result["feasible"]
    dead = impossible_result["certificate"]
    rejected("infeasible_source_finite", dead, impossible, lambda c: c["states"][0].__setitem__(4, 0))
    rejected("infeasible_omitted_successor", dead, impossible, lambda c: c["states"].pop(1))
    rejected("infeasible_omitted_source", dead, impossible, lambda c: c["states"].pop(0))
    rejected("infeasible_duplicate_state", dead, impossible, lambda c: c["states"].append(c["states"][0][:]))
    rejected("infeasible_unknown_field", dead, impossible, lambda c: c.update(unchecked=True))
    rejected("infeasible_status_flip", dead, impossible, lambda c: c.update(status="feasible"))
    rejected("infeasible_wrong_state_type", dead, impossible, lambda c: c.update(states={}))
    rejected("infeasible_malformed_record", dead, impossible, lambda c: c["states"].__setitem__(0, [0]))
    rejected("infeasible_noninteger_potential", dead, impossible, lambda c: c["states"][0].__setitem__(4, 0.5))
    rejected("infeasible_changed_instance", dead, impossible, lambda c: c["instance"].update(name="other"))
    rejected("infeasible_dead_reaches_finite", dead, impossible, lambda c: c["states"][1].__setitem__(4, 0))
    rejected("infeasible_added_trace", dead, impossible, lambda c: c.update(trace=[]))

    # Renaming SSA values is semantic alpha-conversion.
    renamed = deepcopy(instance)
    mapping = {"x": "input-tile", "v0": "middle-tile", "v1": "output-tile"}
    renamed["name"] = "renamed"
    renamed["inputs"] = [mapping[value] for value in renamed["inputs"]]
    renamed["outputs"] = [mapping[value] for value in renamed["outputs"]]
    renamed["footprint"] = {mapping[value]: size for value, size in renamed["footprint"].items()}
    for node in renamed["nodes"]:
        node["out"] = mapping[node["out"]]
        node["args"] = [mapping[value] for value in node["args"]]
    renamed_certificate = solve(renamed)["certificate"]
    assert check(renamed, renamed_certificate)["upper"] == certificate["upper"]

    # Relisting incomparable nodes changes their numeric run identifiers but not
    # the ready-set optimum.  This distinguishes the new machine from the fixed
    # list-order baseline.
    listed = deepcopy(schedule_cases()[-1])
    relisted = deepcopy(listed)
    relisted["name"] = "schedule-relisted"
    relisted["nodes"] = [
        listed["nodes"][0], listed["nodes"][2], listed["nodes"][1],
        listed["nodes"][3], listed["nodes"][4],
    ]
    listed_value = check(listed, solve(listed)["certificate"])["upper"]
    relisted_value = check(relisted, solve(relisted)["certificate"])["upper"]
    assert listed_value == relisted_value

    return {
        "mutations": tests,
        "mutations_rejected": len(tests),
        "rename_invariant": True,
        "topological_relisting_invariant": True,
    }


class CertificateMutationTests(unittest.TestCase):
    def test_mutations_and_metamorphisms(self):
        report = run_tests()
        self.assertEqual(report["mutations_rejected"], 55)
        self.assertTrue(report["rename_invariant"])
        self.assertTrue(report["topological_relisting_invariant"])


if __name__ == "__main__":
    unittest.main()
