"""Bound finite campaigns to live instances, not all past instances."""
import gc
import sys
import unittest
import weakref
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cases import boundary_case
from model import Model
from checker import Semantics


class InstanceCacheTests(unittest.TestCase):
    def test_completed_instances_are_collectible(self):
        for cls in (Model, Semantics):
            with self.subTest(implementation=cls.__name__):
                refs = []
                for _ in range(32):
                    instance = cls(boundary_case())
                    instance.available(0)
                    instance.live(0)
                    instance.ready(0)
                    if cls is Model:
                        instance.occupied(0)
                        list(instance.successors(instance.initial()))
                    else:
                        instance.done_nodes(0)
                        instance.transitions(instance.initial())
                    refs.append(weakref.ref(instance))
                    del instance
                gc.collect()
                self.assertTrue(all(ref() is None for ref in refs))

    def test_cache_values_do_not_cross_instance_boundaries(self):
        for cls in (Model, Semantics):
            with self.subTest(implementation=cls.__name__):
                left = cls(boundary_case())
                other = boundary_case()
                other["nodes"][1]["args"] = ["x"]
                right = cls(other)
                self.assertEqual(left.ready(0), (0,))
                self.assertEqual(right.ready(0), (0, 1))
                self.assertEqual(left.ready(0), (0,))


if __name__ == "__main__":
    unittest.main()
