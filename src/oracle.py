"""Independent non-memoized ready-set normal-form oracle.

The oracle imports neither the planner, the bit-mask model, nor the checker.  For
small instances it enumerates every ready-node choice, allowed execution mode,
and retained-resident subset in the stage normal form proved in
``proofs/semantics.md``.  It is deliberately exponential and bounded.
"""
from __future__ import annotations

from itertools import combinations


def optimum(instance):
    if len(instance["capacity"]) > 2:
        raise ValueError("oracle normal form established only for at most two modes")
    nodes = instance["nodes"]
    if len(nodes) > 5:
        raise ValueError("oracle is intentionally limited to at most five nodes")

    costs = {event: interval[1] for event, interval in instance["bounds"].items()}
    load_cost = costs["dram_read"] + costs["sp_write"]
    store_cost = costs["dram_write"] + costs["sp_read"]
    all_done = (1 << len(nodes)) - 1
    outputs = set(instance["outputs"])
    footprint = instance["footprint"]

    def units(values):
        return sum(footprint[value] for value in values)

    producer = {}
    dependencies = []
    for index, node in enumerate(nodes):
        dependencies.append(frozenset(producer[value] for value in node["args"] if value in producer))
        producer[node["out"]] = index

    def finished(done):
        return {index for index in range(len(nodes)) if done & (1 << index)}

    def live(done):
        available = set(instance["inputs"])
        for index in finished(done):
            available.add(nodes[index]["out"])
        needed = set(outputs)
        for index, node in enumerate(nodes):
            if not (done & (1 << index)):
                needed.update(node["args"])
        return available & needed

    def ready(done):
        complete = finished(done)
        return [
            index for index in range(len(nodes))
            if not (done & (1 << index)) and dependencies[index] <= complete
        ]

    visits = 0
    leaves = 0

    def walk(done, mode, resident, dirty):
        nonlocal visits, leaves
        visits += 1
        if visits > 5_000_000:
            raise RuntimeError("oracle branch ceiling")
        if done == all_done:
            leaves += 1
            return units(set(dirty) & outputs) * store_cost

        best = None
        for node_index in ready(done):
            node = nodes[node_index]
            required = set(node["args"])
            done2 = done | (1 << node_index)
            live2 = live(done2)
            for target in node["modes"]:
                capacity = instance["capacity"][target]
                if units(required) + footprint[node["out"]] > capacity:
                    continue
                same_mode = target == mode
                retains = same_mode or instance["retain"][mode][target]
                cfg_cost = 0 if same_mode else costs[f"cfg.{mode}.{target}"]

                if retains:
                    essential = set(resident) & required
                    optional = sorted(set(resident) - required)
                    survivor_sets = (
                        essential | set(choice)
                        for size in range(len(optional) + 1)
                        for choice in combinations(optional, size)
                    )
                else:
                    survivor_sets = (set(),)

                for saved in survivor_sets:
                    if units(saved | required) + footprint[node["out"]] > capacity:
                        continue
                    if retains:
                        discarded = set(resident) - saved
                        expense = cfg_cost + units(set(dirty) & discarded) * store_cost
                        expense += units(required - saved) * load_cost
                        dirty_kept = set(dirty) & saved
                    else:
                        # A destructive switch is legal only after every dirty
                        # resident value has been backed.  All operands are then
                        # loaded into the target mode.
                        expense = cfg_cost + units(dirty) * store_cost
                        expense += units(required) * load_cost
                        dirty_kept = set()

                    expense += costs[f"op.{node['op']}.{target}"]
                    expense += sum(footprint[value] for value in node["args"]) * costs["sp_read"]
                    expense += footprint[node["out"]] * costs["sp_write"]
                    next_resident = (saved | required | {node["out"]}) & live2
                    next_dirty = (dirty_kept | {node["out"]}) & live2
                    tail = walk(
                        done2,
                        target,
                        frozenset(next_resident),
                        frozenset(next_dirty),
                    )
                    if tail is not None:
                        candidate = expense + tail
                        best = candidate if best is None else min(best, candidate)
        return best

    value = walk(0, 0, frozenset(), frozenset())
    return {
        "upper": value,
        "branch_visits": visits,
        "complete_plans": leaves,
    }
