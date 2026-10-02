"""Finite ready-set datapath semantics; no tensor execution.

The producer uses integer bit masks.  The certificate checker deliberately
reimplements the same abstract machine with Python sets and frozensets.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache


class InvalidModel(ValueError):
    pass


def integer(x: object, lo: int, hi: int) -> bool:
    return type(x) is int and lo <= x <= hi


@dataclass(frozen=True)
class State:
    done: int
    mode: int
    resident: int
    dirty: int


class Model:
    """Validated finite DAG, storage, reconfiguration, and event-cost model."""

    def __init__(self, obj: dict):
        expected_fields = {
            "name", "tile_type", "inputs", "nodes", "outputs", "footprint",
            "capacity", "retain", "bounds",
        }
        if type(obj) is not dict or set(obj) != expected_fields:
            raise InvalidModel("model fields")
        if not isinstance(obj["name"], str) or not obj["name"]:
            raise InvalidModel("name")
        if obj["tile_type"] != {"dtype": "int16", "shape": [4, 4]}:
            raise InvalidModel("this fragment has uniform int16[4,4] tiles")

        ins, nodes, outs = obj["inputs"], obj["nodes"], obj["outputs"]
        caps, retain, bounds = obj["capacity"], obj["retain"], obj["bounds"]
        if not isinstance(ins, list) or not isinstance(nodes, list) or not isinstance(outs, list):
            raise InvalidModel("graph lists")
        if not (1 <= len(caps) <= 3 and all(integer(c, 1, 32) for c in caps)):
            raise InvalidModel("capacities")
        self.modes = len(caps)
        if (len(retain) != self.modes or
                any(not isinstance(row, list) or len(row) != self.modes or
                    any(type(v) is not bool for v in row) for row in retain)):
            raise InvalidModel("retention matrix")
        if any(not retain[m][m] for m in range(self.modes)):
            raise InvalidModel("identity must retain")

        names = list(ins)
        if (any(not isinstance(v, str) or not v or len(v) > 64 for v in names) or
                len(set(names)) != len(names)):
            raise InvalidModel("input names")
        # The implementation can parse larger masks, but the explicit reachable
        # closure is intentionally capped.  The supplied campaign uses <=6 nodes.
        if len(nodes) > 20:
            raise InvalidModel("at most 20 nodes in executable fragment")

        producer: dict[str, int] = {}
        dep_masks: list[int] = []
        arg_masks: list[int] = []
        output_bits: list[int] = []
        for j, node in enumerate(nodes):
            if not isinstance(node, dict) or set(node) != {"out", "op", "args", "modes"}:
                raise InvalidModel("node fields")
            out = node["out"]
            if not isinstance(out, str) or not out or out in names or len(out) > 64:
                raise InvalidModel("SSA output")
            args = node["args"]
            if (node["op"] not in ("unary", "binary") or not isinstance(args, list) or
                    len(args) != (1 if node["op"] == "unary" else 2)):
                raise InvalidModel("arity")
            if any(v not in names for v in args):
                raise InvalidModel("topological dependency declaration")
            modes = node["modes"]
            if (not isinstance(modes, list) or not modes or len(set(modes)) != len(modes) or
                    not all(integer(m, 0, self.modes - 1) for m in modes)):
                raise InvalidModel("allowed modes")

            deps = 0
            for v in args:
                if v in producer:
                    deps |= 1 << producer[v]
            dep_masks.append(deps)
            names.append(out)
            producer[out] = j

        if len(names) > 40 or len(set(outs)) != len(outs) or any(v not in names for v in outs):
            raise InvalidModel("output names / model size")
        footprint = obj["footprint"]
        if (type(footprint) is not dict or set(footprint) != set(names) or
                any(not integer(size, 1, 16) for size in footprint.values())):
            raise InvalidModel("value footprint")

        self.obj = obj
        self.names = names
        self.nodes = nodes
        self.bits = {v: 1 << j for j, v in enumerate(names)}
        self.input_mask = self.mask(ins)
        self.output_mask = self.mask(outs)
        self.node_output_masks = [self.bits[node["out"]] for node in nodes]
        self.node_arg_masks = [self.mask(node["args"]) for node in nodes]
        self.dep_masks = dep_masks
        self.all_done = (1 << len(nodes)) - 1

        keys = {"dram_read", "dram_write", "sp_read", "sp_write"}
        keys |= {f"op.{op}.{m}" for op in ("unary", "binary") for m in range(self.modes)}
        keys |= {f"cfg.{m}.{k}" for m in range(self.modes) for k in range(self.modes) if k != m}
        if type(bounds) is not dict or set(bounds) != keys:
            raise InvalidModel("event basis")
        if any(not isinstance(b, list) or len(b) != 2 or
               not all(integer(v, 0, 10**9) for v in b) or b[0] > b[1]
               for b in bounds.values()):
            raise InvalidModel("interval bounds must be ordered nonnegative integers")
        self.capacity, self.retain, self.bounds = caps, retain, bounds
        self.footprint = footprint

    def mask(self, values) -> int:
        result = 0
        for value in values:
            result |= self.bits[value]
        return result

    @lru_cache(maxsize=None)
    def occupied(self, mask: int) -> int:
        return sum(self.footprint[value] for value in self.names if mask & self.bits[value])

    @lru_cache(maxsize=None)
    def available(self, done: int) -> int:
        result = self.input_mask
        for j, bit in enumerate(self.node_output_masks):
            if done & (1 << j):
                result |= bit
        return result

    @lru_cache(maxsize=None)
    def live(self, done: int) -> int:
        """Produced values needed by an output or at least one unfinished node."""
        needed = self.output_mask
        for j, arg_mask in enumerate(self.node_arg_masks):
            if not (done & (1 << j)):
                needed |= arg_mask
        return self.available(done) & needed

    @lru_cache(maxsize=None)
    def ready(self, done: int) -> tuple[int, ...]:
        return tuple(
            j for j, deps in enumerate(self.dep_masks)
            if not (done & (1 << j)) and deps & done == deps
        )

    def initial(self) -> State:
        return State(0, 0, 0, 0)

    def goal(self, state: State) -> bool:
        return state.done == self.all_done and not (state.dirty & self.output_mask)

    def cost(self, events: dict, endpoint: int = 1) -> int:
        return sum(count * self.bounds[event][endpoint] for event, count in events.items())

    def successors(self, state: State):
        if self.goal(state):
            return
        done, mode, resident, dirty = state.done, state.mode, state.resident, state.dirty
        live = self.live(done)
        cap = self.capacity[mode]

        for value in self.names:
            bit = self.bits[value]
            if not (live & bit):
                continue
            units = self.footprint[value]
            if not (resident & bit) and self.occupied(resident) + units <= cap:
                yield ["load", value], State(done, mode, resident | bit, dirty), {
                    "dram_read": units, "sp_write": units,
                }
            if dirty & bit:
                yield ["store", value], State(done, mode, resident, dirty ^ bit), {
                    "sp_read": units, "dram_write": units,
                }
            elif resident & bit:
                yield ["drop", value], State(done, mode, resident ^ bit, dirty), {}

        for target in range(self.modes):
            if target == mode:
                continue
            if self.retain[mode][target]:
                if self.occupied(resident) <= self.capacity[target]:
                    yield ["switch", target], State(done, target, resident, dirty), {
                        f"cfg.{mode}.{target}": 1,
                    }
            elif not dirty:
                yield ["switch", target], State(done, target, 0, 0), {
                    f"cfg.{mode}.{target}": 1,
                }

        for node_index in self.ready(done):
            node = self.nodes[node_index]
            required = self.node_arg_masks[node_index]
            out = self.node_output_masks[node_index]
            if (mode in node["modes"] and required & resident == required and
                    self.occupied(resident) + self.footprint[node["out"]] <= cap):
                done2 = done | (1 << node_index)
                live2 = self.live(done2)
                events = {
                    f"op.{node['op']}.{mode}": 1,
                    "sp_read": sum(self.footprint[value] for value in node["args"]),
                    "sp_write": self.footprint[node["out"]],
                }
                yield ["run", node_index], State(
                    done2,
                    mode,
                    (resident | out) & live2,
                    (dirty | out) & live2,
                ), events
