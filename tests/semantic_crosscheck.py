"""Differential check between producer and checker transition reconstructions."""
from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from model import Model
from checker import Semantics


def _set_state(model, state):
    resident = frozenset(
        value for value in model.names if state.resident & model.bits[value]
    )
    dirty = frozenset(
        value for value in model.names if state.dirty & model.bits[value]
    )
    return (state.done, state.mode, resident, dirty)


def _normalize_producer(model, steps):
    return sorted(
        (
            json.dumps(action, separators=(",", ":")),
            _set_state(model, target),
            tuple(sorted(events.items())),
        )
        for action, target, events in steps
    )


def _normalize_checker(steps):
    return sorted(
        (
            json.dumps(action, separators=(",", ":")),
            target,
            tuple(sorted(events.items())),
        )
        for action, target, events in steps
    )


def crosscheck(instances):
    cases = states = edges = 0
    max_states = 0
    for instance in instances:
        model = Model(instance)
        semantics = Semantics(instance)
        source = model.initial()
        queue = deque([source])
        seen = {source}
        case_edges = 0
        while queue:
            state = queue.popleft()
            checker_state = _set_state(model, state)
            assert model.goal(state) == semantics.goal(checker_state), (
                instance["name"], state, "goal mismatch"
            )
            producer_steps = list(model.successors(state))
            checker_steps = semantics.transitions(checker_state)
            assert _normalize_producer(model, producer_steps) == _normalize_checker(checker_steps), (
                instance["name"], state, producer_steps, checker_steps
            )
            case_edges += len(producer_steps)
            for _, target, _ in producer_steps:
                if target not in seen:
                    seen.add(target)
                    queue.append(target)
        cases += 1
        states += len(seen)
        edges += case_edges
        max_states = max(max_states, len(seen))
    return {
        "cases": cases,
        "states": states,
        "edges": edges,
        "max_states_per_case": max_states,
        "transition_sets_equal": True,
    }
