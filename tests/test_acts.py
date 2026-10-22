"""Permanent tests for the act predicate module."""

import unittest

from atomforge import AtomSpaceAPI
from atomforge.infrastructure import UnknownAtomError
from atomforge.stdagent.acts import install
from atomforge.stdagent.relational import install as install_relational


class ActsTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.acts = install(self.api)
        self.kind = self.api.kind("Person")
        self.robert = self.api.create_node("Robert", kind=self.kind)
        self.elena = self.api.create_node("Elena", kind=self.kind)

    def test_vocabulary_is_exactly_does(self):
        self.assertEqual(set(self.acts.predicates), {"Does"})

    def test_install_is_idempotent(self):
        self.assertIs(install(self.api), self.acts)

    def test_act_node_dedups_same_text(self):
        first = self.acts.act_node("hug")
        second = self.acts.act_node("hug")
        self.assertEqual(first, second)
        self.assertTrue(self.acts.is_act(first))
        atom = self.api.get(first)
        self.assertEqual(atom.kind, self.acts.act_kind)

    def test_act_node_rejects_empty_text(self):
        with self.assertRaises(TypeError):
            self.acts.act_node("")

    def test_act_node_does_not_steal_other_kinds(self):
        feeling_kind = self.api.kind("Feeling")
        feeling = self.api.create_node("embrace", kind=feeling_kind)
        act = self.acts.act_node("embrace")
        self.assertNotEqual(act, feeling)

    def test_do_with_text_mints_and_attaches(self):
        atom_id = self.acts.do(self.elena, "hug")
        act = self.acts.act_node("hug")
        self.assertTrue(self.acts.has(self.acts.Does, self.elena, act))
        self.assertEqual(self.acts.acts_of(self.elena), [act])
        self.assertEqual(self.acts.occurrences(act), [atom_id])

    def test_one_canonical_act_many_actors(self):
        act = self.acts.act_node("hug")
        self.acts.do(self.robert, act)
        self.acts.do(self.elena, act)
        self.assertEqual(
            set(self.acts.actors_of(act)), {self.robert, self.elena}
        )
        self.assertEqual(len(self.acts.occurrences(act)), 2)

    def test_do_rejects_non_act_node(self):
        steak = self.api.create_node("Steak", kind=self.kind)
        with self.assertRaises(TypeError):
            self.acts.do(self.elena, steak)

    def test_do_rejects_unknown_actor(self):
        with self.assertRaises(UnknownAtomError):
            self.acts.do(999999, "hug")

    def test_relate_rejects_foreign_predicate(self):
        other = self.api.predicate("Other", arity=2)
        with self.assertRaises(TypeError):
            self.acts.relate(other, self.robert, self.elena)


class ActHierarchyTests(unittest.TestCase):
    """Kind checks are IsA-aware: a node under a subkind of Act
    validates as an act only while the IsA edge is asserted."""

    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.acts = install(self.api)
        self.rel = install_relational(self.api)
        self.kind = self.api.kind("Person")
        self.elena = self.api.create_node("Elena", kind=self.kind)
        self.sex_act_kind = self.api.kind("SexAct")
        self.rimming = self.api.create_node("rimming", kind=self.sex_act_kind)

    def test_subkind_node_is_not_an_act_until_linked(self):
        self.assertFalse(self.acts.is_act(self.rimming))
        with self.assertRaises(TypeError):
            self.acts.do(self.elena, self.rimming)
        self.rel.relate(self.rel.IsA, self.sex_act_kind, self.acts.act_kind)
        self.assertTrue(self.acts.is_act(self.rimming))
        self.acts.do(self.elena, self.rimming)
        self.assertTrue(self.acts.has(self.acts.Does, self.elena, self.rimming))

    def test_act_node_dedup_finds_subkind_node(self):
        self.rel.relate(self.rel.IsA, self.sex_act_kind, self.acts.act_kind)
        self.assertEqual(self.acts.act_node("rimming"), self.rimming)


if __name__ == "__main__":
    unittest.main()
