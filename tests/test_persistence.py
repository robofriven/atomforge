"""Persistence safety: failed saves never touch the existing file,
and save/load round trips preserve the graph.
"""

import os
import tempfile
import unittest

from atomforge import AtomSpaceAPI
from atomforge.core import AtomSpace


class FailedSaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "space.json")
        self.api = AtomSpaceAPI.create()
        self.kind = self.api.kind("TestNode")
        self.node = self.api.create_node("kept", kind=self.kind)

    def test_unserializable_prop_fails_before_touching_disk(self):
        self.api.save(self.path)
        with open(self.path, "rb") as handle:
            original_bytes = handle.read()
        self.api.create_node(
            "bad", kind=self.kind, props={"oops": object()}
        )
        with self.assertRaises(TypeError):
            self.api.save(self.path)
        with open(self.path, "rb") as handle:
            self.assertEqual(handle.read(), original_bytes)
        # The untouched file still loads as the original graph.
        loaded = AtomSpaceAPI.load(self.path)
        self.assertEqual(loaded.find_by_label("kept"), [self.node])
        self.assertEqual(loaded.find_by_label("bad"), [])

    def test_failed_save_leaves_no_temp_files(self):
        self.api.create_node(
            "bad", kind=self.kind, props={"oops": object()}
        )
        with self.assertRaises(TypeError):
            self.api.save(self.path)
        leftovers = [
            name for name in os.listdir(self.tmp.name)
            if name.endswith(".tmp")
        ]
        self.assertEqual(leftovers, [])


class RoundTripTests(unittest.TestCase):
    def test_round_trip_preserves_structure_state_and_metadata(self):
        api = AtomSpaceAPI.create()
        kind = api.kind("Thing")
        other_kind = api.kind("Place")
        a = api.create_node(
            "a", kind=kind,
            props={"n": 3, "tags": ["x", "y"], "flag": True,
                   "note": None, "meta": {"k": "v"}, "pi": 3.5},
        )
        b = api.create_node("b", kind=kind)
        c = api.create_node("c", kind=other_kind)
        predicate = api.predicate("Rel", arity=2, roles=("l", "r"))
        link = api.create_predicate(predicate, a, b, confidence=0.75)
        ligature = api.create_ligature("Bond", a, c)
        transition = api.transition(a, b)
        current = api.make_current(link)
        api.set_confidence(b, 0.25)
        doomed = api.create_node("doomed", kind=kind)
        doomed_link = api.create_predicate(predicate, doomed, a)
        api.delete(doomed)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "space.json")
            api.save(path)
            loaded = AtomSpaceAPI.load(path)

        # Labels, structure, relationships.
        self.assertEqual(loaded.find_by_label("a"), [a])
        self.assertTrue(loaded.has_predicate(predicate, a, b))
        self.assertEqual(loaded.predicate_args(link), (a, b))
        self.assertIn(ligature, loaded.in_ligatures(a))
        self.assertEqual(loaded.transition_args(transition), (a, b))
        # Props with JSON-native values survive intact.
        node = loaded.get(a)
        self.assertEqual(
            dict(node.props),
            {"n": 3, "tags": ["x", "y"], "flag": True,
             "note": None, "meta": {"k": "v"}, "pi": 3.5},
        )
        # Confidence metadata.
        self.assertEqual(loaded.confidence(link), 0.75)
        self.assertEqual(loaded.confidence(b), 0.25)
        # Current state.
        self.assertEqual(
            [r.atom.id for r in loaded.find_predicates(
                loaded.current_predicate, link)],
            [current],
        )
        # Deletion state: tombstoned atoms stay tombstoned.
        self.assertIsNone(loaded.get(doomed))
        self.assertTrue(loaded.get_raw(doomed).deleted)
        self.assertIsNone(loaded.get(doomed_link))
        # New writes after load do not collide with loaded ids.
        fresh = loaded.create_node("fresh", kind=kind)
        self.assertGreater(fresh, doomed_link)


if __name__ == "__main__":
    unittest.main()
