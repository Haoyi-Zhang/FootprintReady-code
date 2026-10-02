"""Two explicit comparison policies for the ready-set machine.

``solve_fixed_order`` computes the exact optimum when node execution is restricted
to the supplied topological list.  ``solve_sealed`` permits any ready order but
forces an empty, home-backed scratchpad between node executions.  The latter is an
exact implementation only for instances with at most two modes; larger instances
are rejected because a cheap indirect configuration route can beat the direct edge
used by the macro dynamic program.
"""
from __future__ import annotations

from heapq import heappop, heappush

from model import Model, State


def _shortest_with_filter(model, allow):
    source = model.initial()
    distance = {source: 0}
    predecessor = {}
    queue = [(0, 0, source)]
    serial = 1
    goal = None
    while queue:
        value, _, state = heappop(queue)
        if distance.get(state) != value:
            continue
        if model.goal(state):
            goal = state
            break
        for action, target, events in model.successors(state):
            if not allow(state, action):
                continue
            candidate = value + model.cost(events)
            if candidate < distance.get(target, 10**30):
                distance[target] = candidate
                predecessor[target] = (state, action)
                heappush(queue, (candidate, serial, target))
                serial += 1
    if goal is None:
        return None
    trace = []
    state = goal
    while state != source:
        state, action = predecessor[state]
        trace.append(action)
    trace.reverse()
    return {"upper": distance[goal], "trace": trace}


def solve_fixed_order(obj):
    model = Model(obj)

    def allow(state, action):
        if action[0] != "run":
            return True
        # Reachable restricted states always have a prefix done mask.  Checking
        # the exact next index keeps the restriction explicit.
        next_index = state.done.bit_count()
        return action[1] == next_index

    return _shortest_with_filter(model, allow)


def solve_sealed(obj):
    """Exact dynamic program for the two-mode home-sealed boundary policy."""
    model = Model(obj)
    if model.modes > 2:
        raise ValueError(
            "home-sealed exact baseline is established only for at most two modes"
        )
    source = (0, 0)  # done mask, current mode; storage is empty and backed
    distance = {source: 0}
    predecessor = {}
    queue = [(0, source)]
    goal = None

    while queue:
        value, state = heappop(queue)
        if distance.get(state) != value:
            continue
        done, mode = state
        if done == model.all_done:
            goal = state
            break
        for node_index in model.ready(done):
            node = model.nodes[node_index]
            unique_args = list(dict.fromkeys(node["args"]))
            for target_mode in node["modes"]:
                if (sum(model.footprint[value] for value in unique_args) +
                        model.footprint[node["out"]] > model.capacity[target_mode]):
                    continue
                events = {}
                actions = []
                if target_mode != mode:
                    events[f"cfg.{mode}.{target_mode}"] = 1
                    actions.append(["switch", target_mode])
                for value_name in unique_args:
                    units = model.footprint[value_name]
                    events["dram_read"] = events.get("dram_read", 0) + units
                    events["sp_write"] = events.get("sp_write", 0) + units
                    actions.append(["load", value_name])
                events[f"op.{node['op']}.{target_mode}"] = 1
                events["sp_read"] = events.get("sp_read", 0) + sum(
                    model.footprint[value] for value in node["args"]
                )
                events["sp_write"] = events.get("sp_write", 0) + model.footprint[node["out"]]
                actions.append(["run", node_index])

                done2 = done | (1 << node_index)
                # The fresh result is the only dirty value because the incoming
                # boundary is clean.  Store it exactly when it remains live.
                if model.node_output_masks[node_index] & model.live(done2):
                    units = model.footprint[node["out"]]
                    events["sp_read"] = events.get("sp_read", 0) + units
                    events["dram_write"] = events.get("dram_write", 0) + units
                    actions.append(["store", node["out"]])
                target = (done2, target_mode)
                candidate = value + model.cost(events)
                if candidate < distance.get(target, 10**30):
                    distance[target] = candidate
                    predecessor[target] = (state, actions)
                    heappush(queue, (candidate, target))

    if goal is None:
        return None

    macro_actions = []
    state = goal
    while state != source:
        state, actions = predecessor[state]
        macro_actions.append(actions)
    macro_actions.reverse()

    # Materialize the zero-cost drops needed to restore the promised empty
    # boundary before each nonterminal macro-step.
    trace = []
    concrete = model.initial()
    for macro_index, actions in enumerate(macro_actions):
        for action in actions:
            matches = [step for step in model.successors(concrete) if step[0] == action]
            if len(matches) != 1:
                raise AssertionError(("sealed action became illegal", action, concrete))
            trace.append(action)
            concrete = matches[0][1]
        if not model.goal(concrete) and macro_index + 1 < len(macro_actions):
            for value_name in model.names:
                bit = model.bits[value_name]
                if concrete.resident & bit:
                    action = ["drop", value_name]
                    matches = [step for step in model.successors(concrete) if step[0] == action]
                    if len(matches) != 1:
                        raise AssertionError(("sealed drop became illegal", action, concrete))
                    trace.append(action)
                    concrete = matches[0][1]
    if not model.goal(concrete):
        raise AssertionError("sealed reconstruction did not reach a goal")
    return {"upper": distance[goal], "trace": trace}
