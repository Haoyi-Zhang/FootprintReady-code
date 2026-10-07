"""Owned bounded event replay and edge-retention regressions; no timings."""
from copy import deepcopy
from itertools import product
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import weakref

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import planner
from cases import make
from checker import check
from model import Model
from oracle import optimum


def definition_counts(instance, trace):
    """Separate event definition, not Model.cost/successors or checker transitions."""
    counts = {event: 0 for event in instance['bounds']}
    mode = 0
    def add(event, count):
        counts[event] += count
    for kind, item in trace:
        if kind == 'load':
            units = instance['footprint'][item]
            add('dram_read', units); add('sp_write', units)
        elif kind == 'store':
            units = instance['footprint'][item]
            add('sp_read', units); add('dram_write', units)
        elif kind == 'switch':
            add(f'cfg.{mode}.{item}', 1); mode = item
        elif kind == 'run':
            node = instance['nodes'][item]
            add(f"op.{node['op']}.{mode}", 1)
            add('sp_read', sum(instance['footprint'][v] for v in node['args']))
            add('sp_write', instance['footprint'][node['out']])
        elif kind != 'drop':
            raise AssertionError('unknown owned trace action')
    return counts


def owned_cases():
    for repeated, keep, cfg, size in product((False, True), (False, True), (0, 9), (1, 2)):
        args = ['x', 'x'] if repeated else ['x']
        yield make('owned-events', ['x'], [args, ['v0']], capacity=2 + size,
                   retain=keep, cfg=cfg, width=1, forced=True,
                   footprints={'x': size, 'v0': 1, 'v1': 2})


class TraceEventTests(unittest.TestCase):
    def test_selected_events_without_a_second_successor_pass(self):
        calls = []
        class ObservedModel(Model):
            def successors(self, state):
                calls.append(state)
                yield from super().successors(state)
        for instance in owned_cases():
            calls.clear()
            with patch.object(planner, 'Model', ObservedModel):
                result = planner.solve(instance)
            self.assertEqual(len(calls), result['states'])
            self.assertEqual(len(set(calls)), result['states'])
            self.assertTrue(check(instance, result['certificate'])['accepted'])
            if result['feasible']:
                self.assertEqual(result['certificate']['counts'],
                                 definition_counts(instance, result['certificate']['trace']))

    def test_definition_and_independent_bounded_optimum(self):
        for instance in owned_cases():
            before = deepcopy(instance)
            result = planner.solve(instance)
            certificate = result['certificate']
            self.assertTrue(check(instance, certificate)['accepted'])
            wanted = optimum(instance)['upper']
            self.assertEqual(certificate.get('upper'), wanted)
            if result['feasible']:
                counts = definition_counts(instance, certificate['trace'])
                self.assertEqual(certificate['counts'], counts)
                for endpoint, name in ((0, 'lower'), (1, 'upper')):
                    self.assertEqual(certificate[name], sum(n * instance['bounds'][e][endpoint]
                                                          for e, n in counts.items()))
            self.assertEqual(instance, before)

    def test_zero_cost_hop_tie_and_explicit_ceiling_errors(self):
        instance = make('owned-zero-cycle', ['x'], [['x']], capacity=2, retain=True)
        instance['bounds'] = {e: [0, 0] for e in instance['bounds']}
        result = planner.solve(instance)
        self.assertEqual(result['certificate']['trace'], [['load', 'x'], ['run', 0], ['store', 'v0']])
        self.assertEqual(result['certificate']['upper'], 0)
        self.assertTrue(check(instance, result['certificate'])['accepted'])
        for limits, message in ((dict(state_limit=1), 'state ceiling 1'),
                                (dict(edge_limit=0), 'edge ceiling 0')):
            with self.assertRaisesRegex(planner.SearchLimit, message):
                planner.solve(instance, **limits)

    def test_event_maps_are_not_retained_for_the_whole_closure(self):
        class EventMap(dict):
            __slots__ = ('__weakref__',)
        references = []
        alive = []
        class ObservedModel(Model):
            def successors(self, state):
                for action, target, events in super().successors(state):
                    mapped = EventMap(events)
                    references.append(weakref.ref(mapped))
                    alive.append(sum(r() is not None for r in references))
                    yield action, target, mapped
        instance = make('owned-retention', ['x'], [['x'], ['v0']], capacity=3, retain=True)
        with patch.object(planner, 'Model', ObservedModel):
            result = planner.solve(instance)
        self.assertGreater(result['edges'], 4)
        self.assertLessEqual(max(alive), 4)
        self.assertTrue(all(r() is None for r in references))
        self.assertTrue(check(instance, result['certificate'])['accepted'])


if __name__ == '__main__':
    unittest.main()
