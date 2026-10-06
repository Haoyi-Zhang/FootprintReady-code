"""Certificate checking with a representation-distinct set semantics.

The checker imports neither the planner nor the bit-mask model.  It validates the
supplied abstract instance, reconstructs its complete represented transition
closure, and accepts either (i) a feasible trace paired with exactness lower
labels or (ii) an inductive no-goal labeling for an infeasible instance.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


class CheckError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise CheckError(reason)


def is_int(value, minimum=0, maximum=10**30):
    return type(value) is int and minimum <= value <= maximum


def load_json(path):
    path = Path(path)
    require(path.stat().st_size <= 32 * 1024 * 1024, "input byte ceiling")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(_):
        raise CheckError("non-finite JSON constant")

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=pairs,
        parse_constant=invalid_constant,
    )


class Semantics:
    """Set-based reconstruction of the ready-set machine."""

    def __init__(self, instance):
        expected = {
            "name", "tile_type", "inputs", "nodes", "outputs", "footprint",
            "capacity", "retain", "bounds",
        }
        require(type(instance) is dict and set(instance) == expected, "instance schema")
        require(type(instance["name"]) is str and bool(instance["name"]), "instance name")
        require(
            json.dumps(instance["tile_type"], sort_keys=True) ==
            json.dumps({"dtype": "int16", "shape": [4, 4]}, sort_keys=True),
            "tile type",
        )

        self.nodes = instance["nodes"]
        self.inputs = instance["inputs"]
        self.outputs = instance["outputs"]
        self.caps = instance["capacity"]
        self.keep = instance["retain"]
        self.bounds = instance["bounds"]
        require(
            all(type(value) is list for value in
                (self.nodes, self.inputs, self.outputs, self.caps, self.keep)),
            "instance list types",
        )
        require(1 <= len(self.caps) <= 3 and all(is_int(c, 1, 32) for c in self.caps), "capacity")
        self.M, self.N = len(self.caps), len(self.nodes)
        require(self.N <= 20, "node ceiling")
        self.all_done = (1 << self.N) - 1
        require(
            len(self.keep) == self.M and
            all(type(row) is list and len(row) == self.M and
                all(type(flag) is bool for flag in row) for row in self.keep),
            "retention matrix",
        )
        require(all(self.keep[m][m] for m in range(self.M)), "identity retention")

        def valid_name(value):
            return type(value) is str and 1 <= len(value) <= 64

        require(
            all(valid_name(value) for value in self.inputs) and
            len(set(self.inputs)) == len(self.inputs),
            "input names",
        )
        self.names = list(self.inputs)
        made = set(self.inputs)
        producer: dict[str, int] = {}
        self.dependencies: list[frozenset[int]] = []
        for j, node in enumerate(self.nodes):
            require(
                type(node) is dict and set(node) == {"out", "op", "args", "modes"},
                "node schema",
            )
            require(valid_name(node["out"]) and node["out"] not in made, "SSA names")
            require(
                node["op"] in ("unary", "binary") and type(node["args"]) is list and
                len(node["args"]) == (1 if node["op"] == "unary" else 2),
                "operator arity",
            )
            require(
                all(type(value) is str and value in made for value in node["args"]),
                "topological dependency declaration",
            )
            require(
                type(node["modes"]) is list and bool(node["modes"]) and
                all(is_int(mode, 0, self.M - 1) for mode in node["modes"]) and
                len(set(node["modes"])) == len(node["modes"]),
                "mode permissions",
            )
            deps = frozenset(producer[value] for value in node["args"] if value in producer)
            self.dependencies.append(deps)
            self.names.append(node["out"])
            made.add(node["out"])
            producer[node["out"]] = j

        require(
            len(self.names) <= 40 and
            all(type(value) is str and value in made for value in self.outputs) and
            len(set(self.outputs)) == len(self.outputs),
            "graph outputs",
        )
        self.footprint = instance["footprint"]
        require(
            type(self.footprint) is dict and set(self.footprint) == set(self.names) and
            all(is_int(size, 1, 16) for size in self.footprint.values()),
            "value footprint",
        )

        event_names = {"dram_read", "dram_write", "sp_read", "sp_write"}
        for mode in range(self.M):
            event_names.update(f"op.{op}.{mode}" for op in ("unary", "binary"))
            event_names.update(f"cfg.{mode}.{target}" for target in range(self.M) if target != mode)
        require(type(self.bounds) is dict and set(self.bounds) == event_names, "event names")
        require(
            all(type(value) is list and len(value) == 2 and
                all(is_int(endpoint, 0, 10**9) for endpoint in value) and
                value[0] <= value[1] for value in self.bounds.values()),
            "interval endpoints must be ordered nonnegative integers",
        )
        # Each parsed instance owns its memoized sets; completed checks must not
        # remain reachable through a process-global method cache.
        for method in ("done_nodes", "available", "live", "ready"):
            setattr(self, method, lru_cache(maxsize=None)(getattr(self, method)))

    def done_nodes(self, done):
        return frozenset(j for j in range(self.N) if done & (1 << j))

    def available(self, done):
        values = set(self.inputs)
        for j in self.done_nodes(done):
            values.add(self.nodes[j]["out"])
        return frozenset(values)

    def live(self, done):
        needed = set(self.outputs)
        for j, node in enumerate(self.nodes):
            if not (done & (1 << j)):
                needed.update(node["args"])
        return frozenset(set(self.available(done)) & needed)

    def ready(self, done):
        finished = self.done_nodes(done)
        return tuple(
            j for j in range(self.N)
            if not (done & (1 << j)) and self.dependencies[j] <= finished
        )

    def occupied(self, values):
        return sum(self.footprint[value] for value in values)

    def initial(self):
        return (0, 0, frozenset(), frozenset())

    def goal(self, state):
        return state[0] == self.all_done and not (state[3] & set(self.outputs))

    def decode(self, row):
        require(type(row) is list and len(row) == 5, "state record")
        done, mode, resident_mask, dirty_mask, potential = row
        require(is_int(done, 0, self.all_done) and is_int(mode, 0, self.M - 1), "state coordinates")
        max_mask = (1 << len(self.names)) - 1
        require(
            is_int(resident_mask, 0, max_mask) and is_int(dirty_mask, 0, max_mask),
            "state mask",
        )
        resident = frozenset(
            value for j, value in enumerate(self.names)
            if resident_mask & (1 << j)
        )
        dirty = frozenset(
            value for j, value in enumerate(self.names)
            if dirty_mask & (1 << j)
        )
        finished = self.done_nodes(done)
        require(
            all(self.dependencies[node] <= finished for node in finished),
            "dependency-closed completed set",
        )
        require(
            dirty <= resident and resident <= self.live(done) and
            self.occupied(resident) <= self.caps[mode],
            "state invariant",
        )
        require(potential is None or is_int(potential), "potential domain")
        return (done, mode, resident, dirty), potential

    def transitions(self, state):
        if self.goal(state):
            return []
        done, mode, resident, dirty = state
        steps = []
        live = self.live(done)

        for value in sorted(live - resident):
            units = self.footprint[value]
            if self.occupied(resident) + units <= self.caps[mode]:
                steps.append((
                    ["load", value],
                    (done, mode, resident | {value}, dirty),
                    {"dram_read": units, "sp_write": units},
                ))
        for value in sorted(dirty):
            units = self.footprint[value]
            steps.append((
                ["store", value],
                (done, mode, resident, dirty - {value}),
                {"sp_read": units, "dram_write": units},
            ))
        for value in sorted(resident - dirty):
            steps.append((["drop", value], (done, mode, resident - {value}, dirty), {}))

        for target in range(self.M):
            if target == mode:
                continue
            if self.keep[mode][target]:
                if self.occupied(resident) <= self.caps[target]:
                    steps.append((
                        ["switch", target],
                        (done, target, resident, dirty),
                        {f"cfg.{mode}.{target}": 1},
                    ))
            elif not dirty:
                steps.append((
                    ["switch", target],
                    (done, target, frozenset(), frozenset()),
                    {f"cfg.{mode}.{target}": 1},
                ))

        for node_index in self.ready(done):
            node = self.nodes[node_index]
            required = set(node["args"])
            if (mode in node["modes"] and required <= resident and
                    self.occupied(resident) + self.footprint[node["out"]] <= self.caps[mode]):
                done2 = done | (1 << node_index)
                live2 = self.live(done2)
                output = {node["out"]}
                steps.append((
                    ["run", node_index],
                    (
                        done2,
                        mode,
                        frozenset((set(resident) | output) & set(live2)),
                        frozenset((set(dirty) | output) & set(live2)),
                    ),
                    {
                        f"op.{node['op']}.{mode}": 1,
                        "sp_read": sum(self.footprint[value] for value in node["args"]),
                        "sp_write": self.footprint[node["out"]],
                    },
                ))
        return steps

    def weight(self, events, endpoint=1):
        return sum(amount * self.bounds[event][endpoint] for event, amount in events.items())


def check_trace(instance, trace):
    sem = Semantics(instance)
    require(type(trace) is list and len(trace) <= 600000, "trace ceiling")
    state = sem.initial()
    counts = {event: 0 for event in sem.bounds}
    for action in trace:
        require(type(action) is list and action and type(action[0]) is str, "action schema")
        if action[0] == "switch":
            require(len(action) == 2 and is_int(action[1], 0, sem.M - 1), "switch target")
        elif action[0] == "run":
            require(len(action) == 2 and is_int(action[1], 0, sem.N - 1), "run action")
        else:
            require(
                len(action) == 2 and action[0] in ("load", "store", "drop") and
                type(action[1]) is str,
                "memory action",
            )
        matches = [step for step in sem.transitions(state) if step[0] == action]
        require(len(matches) == 1, f"illegal action {action} at done mask {state[0]}")
        _, state, events = matches[0]
        for event, amount in events.items():
            counts[event] += amount
    require(sem.goal(state), "trace does not finish with backed outputs")
    return {
        "counts": counts,
        "lower": sem.weight(counts, 0),
        "upper": sem.weight(counts, 1),
    }


def _check_labels(sem, records):
    require(type(records) is list and 1 <= len(records) <= 120000, "certificate state ceiling")
    labels = {}
    for row in records:
        state, label = sem.decode(row)
        require(state not in labels, "duplicate state")
        labels[state] = label
    require(sem.initial() in labels, "missing source")

    edge_count = 0
    adjacency = {}
    for state, label in labels.items():
        if sem.goal(state):
            require(label == 0, "goal potential")
        targets = []
        for _, target, events in sem.transitions(state):
            edge_count += 1
            require(edge_count <= 1_200_000, "checker edge ceiling")
            require(target in labels, "successor closure")
            targets.append(target)
            target_label = labels[target]
            if label is None:
                require(target_label is None, "dead state reaches finite state")
            elif target_label is not None:
                require(
                    label <= sem.weight(events, 1) + target_label,
                    "Bellman lower-bound inequality",
                )
        adjacency[state] = targets

    # Successor closure alone permits an attacker to append a disconnected,
    # locally valid closed component.  Certificates claim the exact closure
    # reachable from the source, so reconstruct that reachability explicitly.
    reached = {sem.initial()}
    work = [sem.initial()]
    while work:
        state = work.pop()
        for target in adjacency[state]:
            if target not in reached:
                reached.add(target)
                work.append(target)
    require(reached == set(labels), "extraneous source-unreachable state")
    return labels, edge_count


def _check(instance, certificate):
    sem = Semantics(instance)
    require(type(certificate) is dict and certificate.get("status") in ("feasible", "infeasible"), "certificate status")
    status = certificate["status"]
    if status == "feasible":
        expected = {"status", "instance", "upper", "lower", "trace", "counts", "states"}
    else:
        expected = {"status", "instance", "states"}
    require(set(certificate) == expected, "certificate schema")
    require(
        json.dumps(certificate["instance"], sort_keys=True, allow_nan=False) ==
        json.dumps(instance, sort_keys=True, allow_nan=False),
        "instance binding",
    )

    labels, edge_count = _check_labels(sem, certificate["states"])
    source_label = labels[sem.initial()]
    if status == "infeasible":
        require(source_label is None, "infeasible source must be dead")
        return {
            "accepted": True,
            "status": "infeasible",
            "states": len(labels),
            "edges": edge_count,
        }

    require(is_int(certificate["upper"]) and is_int(certificate["lower"]), "claimed cost domain")
    observed = check_trace(instance, certificate["trace"])
    require(
        certificate["upper"] == observed["upper"] and
        certificate["lower"] == observed["lower"],
        "trace cost",
    )
    require(
        type(certificate["counts"]) is dict and
        set(certificate["counts"]) == set(sem.bounds) and
        all(is_int(value) for value in certificate["counts"].values()),
        "count schema",
    )
    require(certificate["counts"] == observed["counts"], "event counts")
    require(source_label == observed["upper"], "source lower bound")
    return {
        "accepted": True,
        "status": "feasible",
        "upper": observed["upper"],
        "lower": observed["lower"],
        "states": len(labels),
        "edges": edge_count,
    }


def check(instance, certificate):
    try:
        return _check(instance, certificate)
    except CheckError:
        raise
    except (TypeError, ValueError, KeyError, IndexError, OverflowError) as exc:
        raise CheckError(f"malformed input: {type(exc).__name__}") from exc
