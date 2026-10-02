"""Deterministic synthetic abstract graphs; these are not neural workloads."""
from copy import deepcopy
from random import Random


def make(name, inputs, node_args, *, capacity=3, retain=False, cfg=9, width=0, forced=False, footprints=None):
    nodes = []
    for i, args in enumerate(node_args):
        nodes.append({"out": f"v{i}", "op": "unary" if len(args) == 1 else "binary", "args": list(args), "modes": [i % 2] if forced else [0, 1]})
    center = {"dram_read": 5, "dram_write": 7, "sp_read": 1, "sp_write": 1,
              "op.unary.0": 8, "op.unary.1": 3, "op.binary.0": 4, "op.binary.1": 9,
              "cfg.0.1": cfg, "cfg.1.0": cfg}
    value_names = list(inputs) + [node["out"] for node in nodes]
    footprint = {value: 1 for value in value_names}
    if footprints is not None:
        unknown = set(footprints) - set(value_names)
        if unknown:
            raise ValueError(f"unknown footprint names: {sorted(unknown)}")
        footprint.update(footprints)
    return {"name": name, "tile_type": {"dtype": "int16", "shape": [4, 4]}, "inputs": inputs,
            "nodes": nodes, "outputs": [f"v{len(nodes)-1}"] if nodes else inputs[:1],
            "footprint": footprint, "capacity": [capacity, capacity],
            "retain": [[True, retain], [retain, True]],
            "bounds": {key: [max(0, val - width), val + width] for key, val in center.items()}}


def boundary_case(retain=False):
    return make("boundary-retain" if retain else "boundary-flush", ["x"], [["x"], ["v0"]], capacity=2, retain=retain, forced=True)


def pilot_case():
    return make("pilot-fork-join", ["x", "w"], [["x"], ["x", "w"], ["v0", "v1"], ["v2"]], capacity=3, forced=True)


def small_cases():
    # Frozen enumeration, not selected by outcomes. 2 modes x 3 capacities x
    # 2 retention choices x 8 ordered DAG shapes = 48 instances.
    patterns = [(["x"], []), (["x"], [["x"]]),
                (["x"], [["x"], ["v0"]]), (["x"], [["x"], ["x"], ["v0", "v1"]]),
                (["x", "w"], [["x", "w"], ["v0", "w"]]),
                (["x"], [["x", "x"], ["v0"]]),
                (["x", "w"], [["x"], ["x", "w"], ["v0", "v1"], ["v2"]]),
                (["x"], [["x"], ["v0"], ["v1", "x"], ["v2"]])]
    cases = []
    for p, (inputs, args) in enumerate(patterns):
        for cap in (2, 3, 4):
            for keep in (False, True):
                cases.append(make(f"small-{p:02d}-{cap}-{int(keep)}", inputs, args, capacity=cap, retain=keep))
    return cases


def campaign_cases():
    families = {
        "chain": (["x"], [["x"], ["v0"], ["v1"], ["v2"], ["v3"], ["v4"]]),
        "diamond": (["x"], [["x"], ["x"], ["v0", "v1"], ["v2"], ["v2"], ["v3", "v4"]]),
        "residual": (["x"], [["x"], ["v0"], ["v1", "x"], ["v2"], ["v3", "v2"], ["v4"]]),
        "shared": (["x", "w"], [["x", "w"], ["v0", "w"], ["v1"], ["v2", "w"], ["v3"], ["v4", "w"]]),
        "wide": (["x"], [["x"], ["x"], ["x"], ["v0", "v1"], ["v2", "v3"], ["v4"]]),
        "fanin": (["a", "b", "c", "d"], [["a", "b"], ["c", "d"], ["v0", "v1"], ["v2"], ["v3"], ["v4"]])}
    cases = []
    for family, (inputs, args) in families.items():
        for cap in (3, 4):
            for keep in (False, True):
                for config in (0, 9, 40):
                    cases.append(make(f"{family}-{cap}-{int(keep)}-{config}", inputs, args, capacity=cap, retain=keep, cfg=config))
    # Interval sensitivity is a separate prespecified slice, not inferred energy.
    for width in (0, 1, 3, 7):
        cases.append(make(f"interval-{width}", *families["diamond"], capacity=3, retain=False, width=width))
    # Reproducible random DAGs with exact small-oracle comparisons; no model data.
    rng = Random(730241)
    for j in range(16):
        available = ["x", "w"]
        args = []
        for i in range(4):
            k = 1 if rng.randrange(2) == 0 else 2
            args.append([rng.choice(available) for _ in range(k)])
            available.append(f"v{i}")
        cases.append(make(f"random-{j:02d}", ["x", "w"], args, capacity=3 + j % 2, retain=bool(j % 2), cfg=(0, 9, 40)[j % 3]))
    return cases


def identity_case():
    x = make("dirty-identity", ["x", "w"], [["x"], ["w"], ["v0"], ["v1"]], capacity=3, retain=True)
    x["capacity"] = [3, 2]
    x["outputs"] = ["v2", "v3"]
    for i, node in enumerate(x["nodes"]):
        node["modes"] = [0 if i < 2 else 1]
    return x


def schedule_cases():
    """Forked chains whose supplied list interleaves mode-specialized branches.

    The list order 0,1,2,3,4 is topological, but the ready-set order 0,2,1,3,4
    can cluster the forced modes.  Parameters are frozen before evaluation.
    """
    cases = []
    for capacity in (3, 4):
        for keep in (False, True):
            for cfg in (0, 9, 40):
                x = make(
                    f"schedule-{capacity}-{int(keep)}-{cfg}",
                    ["x", "w"],
                    [["x"], ["w"], ["v0"], ["v1"], ["v2", "v3"]],
                    capacity=capacity,
                    retain=keep,
                    cfg=cfg,
                )
                for index, mode in enumerate((0, 1, 0, 1)):
                    x["nodes"][index]["modes"] = [mode]
                x["nodes"][4]["modes"] = [0, 1]
                cases.append(x)
    return cases


def footprint_cases():
    """Prespecified nonuniform storage-footprint cases.

    All values retain the same logical tile type, while ``footprint`` records
    abstract storage/transfer quanta (for example, padding or compression).
    Cases are fixed independently of outcomes.
    """
    specs = [
        (
            "chain", ["x"], [["x"], ["v0"], ["v1"], ["v2"]],
            {"x": 2, "v0": 1, "v1": 3, "v2": 2, "v3": 1}, 6,
        ),
        (
            "diamond", ["x", "w"], [["x"], ["w"], ["v0", "v1"], ["v2"]],
            {"x": 2, "w": 1, "v0": 2, "v1": 3, "v2": 1, "v3": 2}, 7,
        ),
        (
            "shared", ["x", "w"], [["x", "w"], ["v0", "w"], ["v1"], ["v2", "w"]],
            {"x": 1, "w": 3, "v0": 2, "v1": 1, "v2": 3, "v3": 2}, 8,
        ),
    ]
    cases = []
    for family, inputs, args, footprint, capacity in specs:
        for keep in (False, True):
            for cfg in (9, 40):
                case = make(
                    f"footprint-{family}-{int(keep)}-{cfg}",
                    inputs, args, capacity=capacity, retain=keep, cfg=cfg,
                    footprints=footprint,
                )
                # Alternate forced modes to make storage and reconfiguration
                # interact rather than testing transfer scaling in isolation.
                for index, node in enumerate(case["nodes"]):
                    node["modes"] = [index % 2]
                cases.append(case)
    return cases


def footprint_identity_case():
    """A fixed case for count-only versus unit-weighted storage summaries."""
    case = make(
        "footprint-identity",
        ["x", "w"],
        [["x"], ["w"], ["v0"], ["v1"], ["v2", "v3"]],
        capacity=7, retain=True, cfg=9,
        footprints={"x": 1, "w": 3, "v0": 3, "v1": 1, "v2": 2, "v3": 4, "v4": 1},
    )
    for index, mode in enumerate((0, 0, 1, 1)):
        case["nodes"][index]["modes"] = [mode]
    case["nodes"][4]["modes"] = [0, 1]
    return case
