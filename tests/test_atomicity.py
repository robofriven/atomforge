"""Regression tests: failed writes, argument coercion, atomicity.

These pin the fixes from the 2026-10-20 code review: a rejected write
must leave no trace in the space, atom ids are never silently coerced,
and multi-write operations validate before they mutate.
"""

import unittest

from atomforge import AtomSpaceAPI
from atomforge.core import AtomSpace
from atomforge.infrastructure import (
    AtomForgeError,
    InvalidConfidenceError,
    UnknownAtomError,
)


def atom_count(core):
    return len(core._atoms)


class FailedWriteTests(unittest.TestCase):
    def setUp(self):
        self.core = AtomSpace()
        self.kind = self.core.kind("TestNode")

    def test_bad_confidence_node_leaves_no_phantom(self):
        before = atom_count(self.core)
        with self.assertRaises(InvalidConfidenceError):
            self.core.create_node("ghost", kind=self.kind, confidence=0)
        self.assertEqual(atom_count(self.core), before)
        self.assertEqual(self.core.find_by_label("ghost"), [])
        # search must not crash on the rejected atom, and the space
        # must still round-trip through save/load.
        self.assertEqual(self.core.search(label="ghost"), [])
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "space.json")
            self.core.save(path)
            loaded = AtomSpace.load(path)
        self.assertEqual(atom_count(loaded), before)

    def test_bad_confidence_leaves_nothing_for_every_atom_type(self):
        node_a = self.core.create_node("a", kind=self.kind)
        node_b = self.core.create_node("b", kind=self.kind)
        predicate = self.core.predicate("Rel", arity=2)
        attempts = [
            lambda: self.core.kind("K2", confidence=2.0),
            lambda: self.core.predicate("P2", confidence=-1),
            lambda: self.core.create_node("n2", kind=self.kind, confidence=0),
            lambda: self.core.create_predicate(
                predicate, node_a, node_b, confidence=1.5
            ),
            lambda: self.core.create_ligature(
                "Lig", node_a, node_b, confidence=0
            ),
            lambda: self.core.transition(node_a, node_b, confidence=7),
        ]
        for attempt in attempts:
            before = atom_count(self.core)
            with self.assertRaises(InvalidConfidenceError):
                attempt()
            self.assertEqual(atom_count(self.core), before)

    def test_unknown_argument_leaves_nothing(self):
        node = self.core.create_node("a", kind=self.kind)
        predicate = self.core.predicate("Rel", arity=2)
        before = atom_count(self.core)
        with self.assertRaises(UnknownAtomError):
            self.core.create_predicate(predicate, node, 99999)
        self.assertEqual(atom_count(self.core), before)


class CoercionTests(unittest.TestCase):
    def setUp(self):
        self.core = AtomSpace()
        self.kind = self.core.kind("TestNode")
        self.a = self.core.create_node("a", kind=self.kind)
        self.b = self.core.create_node("b", kind=self.kind)
        self.predicate = self.core.predicate("Rel", arity=2)

    def test_float_args_are_refused_not_truncated(self):
        before = atom_count(self.core)
        with self.assertRaises(TypeError):
            self.core.create_predicate(
                self.predicate, float(self.a), float(self.b) + 0.9
            )
        self.assertEqual(atom_count(self.core), before)
        self.assertFalse(
            self.core.has_predicate(self.predicate, self.a, self.b)
        )

    def test_bool_and_string_ids_are_refused(self):
        with self.assertRaises(TypeError):
            self.core.create_predicate(self.predicate, True, self.b)
        with self.assertRaises(TypeError):
            self.core.create_ligature("Lig", str(self.a), self.b)
        with self.assertRaises(TypeError):
            self.core.get(float(self.a))
        with self.assertRaises(TypeError):
            self.core.get(True)
        with self.assertRaises(TypeError):
            self.core.find_predicates(self.predicate, float(self.a), self.b)

    def test_rules_layer_refuses_coercion_too(self):
        from atomforge.stdagent.relational import install

        api = AtomSpaceAPI.create()
        rel = install(api)
        kind = api.kind("TestNode")
        x = api.create_node("x", kind=kind)
        y = api.create_node("y", kind=kind)
        with self.assertRaises(TypeError):
            rel.relate(rel.Near, float(x), y)


class MultiWriteAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.core = AtomSpace()
        self.kind = self.core.kind("TestNode")

    def test_delete_aborted_by_validator_deletes_nothing(self):
        a = self.core.create_node("a", kind=self.kind)
        b = self.core.create_node("b", kind=self.kind)
        predicate = self.core.predicate("Rel", arity=2)
        link = self.core.create_predicate(predicate, a, b)
        self.core.make_current(b)

        def guard(space, pred, args):
            if pred.label == "Delete" and args[0] == link:
                raise RuntimeError("refuse to delete the link")

        self.core.add_validator(guard)
        with self.assertRaises(RuntimeError):
            self.core.delete(b)
        # Nothing was deleted, and the Current assertion survived:
        # the preflight must fail before any physical removal.
        self.assertIsNotNone(self.core.get(b))
        self.assertIsNotNone(self.core.get(link))
        self.assertEqual(len(self.core._current_matches(b)), 1)

    def test_failed_transition_moves_no_current(self):
        a = self.core.create_node("a", kind=self.kind)
        b = self.core.create_node("b", kind=self.kind)
        self.core.make_current(a)
        before = atom_count(self.core)
        with self.assertRaises(InvalidConfidenceError):
            self.core.transition(a, b, confidence=0)
        self.assertEqual(atom_count(self.core), before)
        self.assertEqual(len(self.core._current_matches(a)), 1)
        self.assertEqual(len(self.core._current_matches(b)), 0)


if __name__ == "__main__":
    unittest.main()
