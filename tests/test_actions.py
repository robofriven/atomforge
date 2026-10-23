"""Permanent tests for the action-verb module (Use/Wears/Play/Gives)."""

import unittest

from atomforge import AtomSpaceAPI
from atomforge.infrastructure import (
    InvalidAtomOperationError, UnknownAtomError,
)
from atomforge.stdagent.actions import install
from atomforge.stdagent.acts import install as install_acts
from atomforge.stdagent.possession import install as install_possession


class ActionVerbTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.actions = install(self.api)
        self.acts = install_acts(self.api)
        person = self.api.kind("Person")
        self.robert = self.api.create_node("Robert", kind=person)
        self.elena = self.api.create_node("Elena", kind=person)
        object_kind = self.api.kind("Object")
        self.ring = self.api.create_node("emerald ring", kind=object_kind)
        self.claw = self.api.create_node("claw machine", kind=object_kind)
        self.hammer = self.api.create_node("hammer", kind=object_kind)

    def test_vocabulary_is_exact(self):
        self.assertEqual(set(self.actions.predicates),
                         {"Use", "Wears", "Play", "Gives"})

    def test_install_is_idempotent(self):
        self.assertIs(install(self.api), self.actions)

    def test_use_wears_play_assert(self):
        self.actions.use(self.robert, self.hammer)
        self.actions.wears(self.elena, self.ring)
        self.actions.play(self.elena, self.claw)
        self.assertTrue(self.actions.has(
            self.actions.Use, self.robert, self.hammer))
        self.assertTrue(self.actions.has(
            self.actions.Wears, self.elena, self.ring))
        self.assertTrue(self.actions.has(
            self.actions.Play, self.elena, self.claw))
        # The verbs are distinct relations, not one smeared "with".
        self.assertFalse(self.actions.has(
            self.actions.Use, self.elena, self.claw))

    def test_object_verbs_reject_unknown_atoms(self):
        with self.assertRaises(UnknownAtomError):
            self.actions.use(999999, self.hammer)
        with self.assertRaises(UnknownAtomError):
            self.actions.wears(self.elena, 999999)
        with self.assertRaises(UnknownAtomError):
            self.actions.play(self.elena, 999999)

    def test_relate_dispatches_object_verbs(self):
        self.actions.relate(self.actions.Use, self.robert, self.hammer)
        self.assertTrue(self.actions.has(
            self.actions.Use, self.robert, self.hammer))

    def test_foreign_predicate_refused(self):
        other = self.api.predicate("Other", arity=2)
        with self.assertRaises(TypeError):
            self.actions.relate(other, self.robert, self.elena)
        with self.assertRaises(TypeError):
            self.actions.has(other, self.robert, self.elena)


class GivesTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.actions = install(self.api)
        self.acts = install_acts(self.api)
        person = self.api.kind("Person")
        self.robert = self.api.create_node("Robert", kind=person)
        self.elena = self.api.create_node("Elena", kind=person)
        self.ring = self.api.create_node(
            "emerald ring", kind=self.api.kind("Object"))
        self.massage = self.acts.act_node("massage")

    def test_give_object_payload(self):
        application = self.actions.give(
            self.robert, self.elena, self.ring)
        self.assertTrue(self.actions.has(
            self.actions.Gives, self.robert, self.elena))
        self.assertEqual(self.actions.payload_of(application), self.ring)
        self.assertEqual(
            self.actions.givings_from(self.robert), [application])
        self.assertEqual(
            self.actions.givings_to(self.elena), [application])

    def test_give_act_payload(self):
        application = self.actions.give(
            self.robert, self.elena, self.massage)
        self.assertEqual(
            self.actions.payload_of(application), self.massage)

    def test_give_requires_payload(self):
        # There is no payload-free path: relate() refuses Gives.
        with self.assertRaises(TypeError):
            self.actions.relate(
                self.actions.Gives, self.robert, self.elena)
        self.assertEqual(self.actions.givings_from(self.robert), [])
        # And give() itself will not run without one.
        with self.assertRaises(TypeError):
            self.actions.give(self.robert, self.elena)

    def test_self_giving_refused(self):
        with self.assertRaises(TypeError):
            self.actions.give(self.robert, self.robert, self.ring)
        self.assertEqual(self.actions.givings_from(self.robert), [])

    def test_payload_must_be_a_node(self):
        kind_atom = self.api.kind("Object")
        with self.assertRaises(TypeError):
            self.actions.give(self.robert, self.elena, kind_atom)
        saying = self.actions.use(self.robert, self.ring)
        with self.assertRaises(TypeError):
            self.actions.give(self.robert, self.elena, saying)

    def test_give_rejects_unknown_atoms(self):
        with self.assertRaises(UnknownAtomError):
            self.actions.give(999999, self.elena, self.ring)
        with self.assertRaises(UnknownAtomError):
            self.actions.give(self.robert, self.elena, 999999)

    def test_payload_of_rejects_non_gives(self):
        use_atom = self.actions.use(self.robert, self.ring)
        with self.assertRaises(TypeError):
            self.actions.payload_of(use_atom)

    def test_custody_receipt_chains_transition_to_holds(self):
        application = self.actions.give(
            self.robert, self.elena, self.ring)
        transition = self.actions.custody_receipt(application)
        before, after = self.api.transition_args(transition)
        self.assertEqual(before, application)
        possession = install_possession(self.api)
        holds_atom = self.api.get(after)
        self.assertEqual(holds_atom.predicate, possession.Holds)
        self.assertEqual(holds_atom.args, (self.elena, self.ring))
        self.assertTrue(possession.has(
            possession.Holds, self.elena, self.ring))

    def test_custody_receipt_refuses_act_payload(self):
        application = self.actions.give(
            self.robert, self.elena, self.massage)
        with self.assertRaises(TypeError):
            self.actions.custody_receipt(application)


if __name__ == "__main__":
    unittest.main()
