"""Bounded closure enumeration and certificate production.

The producer is intentionally outside the checker trust path.  It emits a full
reachable-state closure labeled by exact upper-endpoint distance to a goal (or
``null`` when no goal is reachable), plus one acyclic optimum trace when feasible.
"""
from __future__ import annotations

from collections import deque
from heapq import heappop, heappush

from model import Model


class SearchLimit(RuntimeError):
    pass


def _trace_events(model: Model, state, action: list) -> dict:
    """Recount an already selected legal edge without enumerating alternatives."""
    kind, item = action
    if kind == 'load':
        units = model.footprint[item]
        return {'dram_read': units, 'sp_write': units}
    if kind == 'store':
        units = model.footprint[item]
        return {'sp_read': units, 'dram_write': units}
    if kind == 'drop':
        return {}
    if kind == 'switch':
        return {f'cfg.{state.mode}.{item}': 1}
    if kind == 'run':
        node = model.nodes[item]
        return {f"op.{node['op']}.{state.mode}": 1,
                'sp_read': sum(model.footprint[v] for v in node['args']),
                'sp_write': model.footprint[node['out']]}
    raise AssertionError('unknown selected trace action')


def solve(obj: dict, state_limit: int = 120000, edge_limit: int = 1_200_000) -> dict:
    model = Model(obj)
    states = [model.initial()]
    ids = {states[0]: 0}
    edges: list[list[tuple[int, list, int]]] = [[]]
    reverse: list[list[tuple[int, int]]] = [[]]
    edge_count = 0

    cursor = 0
    while cursor < len(states):
        for action, destination, events in model.successors(states[cursor]):
            if destination not in ids:
                if len(states) >= state_limit:
                    raise SearchLimit(f"state ceiling {state_limit}")
                ids[destination] = len(states)
                states.append(destination)
                edges.append([])
                reverse.append([])
            target = ids[destination]
            weight = model.cost(events, 1)
            edges[cursor].append((target, action, weight))
            reverse[target].append((cursor, weight))
            edge_count += 1
            if edge_count > edge_limit:
                raise SearchLimit(f"edge ceiling {edge_limit}")
        cursor += 1

    distance: list[int | None] = [None] * len(states)
    queue: list[tuple[int, int]] = []
    for index, state in enumerate(states):
        if model.goal(state):
            distance[index] = 0
            heappush(queue, (0, index))
    while queue:
        value, index = heappop(queue)
        if distance[index] != value:
            continue
        for predecessor, weight in reverse[index]:
            candidate = value + weight
            if distance[predecessor] is None or candidate < distance[predecessor]:
                distance[predecessor] = candidate
                heappush(queue, (candidate, predecessor))

    records = [
        [state.done, state.mode, state.resident, state.dirty, distance[index]]
        for index, state in enumerate(states)
    ]
    if distance[0] is None:
        certificate = {
            "status": "infeasible",
            "instance": obj,
            "states": records,
        }
        return {
            "feasible": False,
            "states": len(states),
            "edges": edge_count,
            "certificate": certificate,
        }

    # A separate unweighted reverse pass supplies an acyclic optimum witness even
    # when zero-cost transitions form cycles among equal-distance states.
    hops: list[int | None] = [None] * len(states)
    work = deque()
    for index, state in enumerate(states):
        if model.goal(state):
            hops[index] = 0
            work.append(index)
    while work:
        index = work.popleft()
        for predecessor, weight in reverse[index]:
            if (distance[predecessor] is not None and
                    distance[predecessor] == weight + distance[index] and
                    hops[predecessor] is None):
                hops[predecessor] = hops[index] + 1
                work.append(predecessor)

    trace: list[list] = []
    counts = {event: 0 for event in sorted(model.bounds)}
    index = 0
    while not model.goal(states[index]):
        step = next(
            (
                edge for edge in edges[index]
                if distance[edge[0]] is not None and
                distance[index] == edge[2] + distance[edge[0]] and
                hops[index] == hops[edge[0]] + 1
            ),
            None,
        )
        if step is None:
            raise AssertionError("missing decreasing optimum witness")
        target, action, weight = step
        # Legality and destination come from the stored closure edge. Its event
        # vector depends only on action, source mode and the fixed instance.
        events = _trace_events(model, states[index], action)
        if model.cost(events, 1) != weight:
            raise AssertionError("selected edge event replay disagrees with closure")
        trace.append(action)
        for event, count in events.items():
            counts[event] += count
        index = target

    certificate = {
        "status": "feasible",
        "instance": obj,
        "upper": distance[0],
        "lower": model.cost(counts, 0),
        "trace": trace,
        "counts": counts,
        "states": records,
    }
    return {
        "feasible": True,
        "states": len(states),
        "edges": edge_count,
        "certificate": certificate,
    }
