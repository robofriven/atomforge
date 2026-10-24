"""Permanent tests for the action-verb module (Use/Wears/Play/Gives)."""

import unittest

from atomforge import AtomSpaceAPI
from atomforge.infrastructure import (
    InvalidAtomOperationError, UnknownAtomError,
)
from atomforge.stdagent.actions import install
from atomforge.stdagent.acts import UnapprovedTermError
from atomforge.stdagent.acts import install as install_acts
from atomforge.stdagent.possession import install as install_possession
from atomforge.stdagent.relational import install as install_relational


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

    def test_payload_must_be_act_or_object(self):
        # A person is a Node, but a person is not a payload: the
        # kind gate refuses what the bare Node check used to allow.
        with self.assertRaises(TypeError):
            self.actions.give(self.robert, self.elena, self.robert)
        self.assertEqual(self.actions.givings_from(self.robert), [])


class ObjectFactoryTests(unittest.TestCase):
    """object_node: the Object kind's registrar — label in,
    deduplicated Object node out, minting ungated."""

    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.actions = install(self.api)
        person = self.api.kind("Person")
        self.robert = self.api.create_node("Robert", kind=person)
        self.elena = self.api.create_node("Elena", kind=person)

    def test_object_node_mints_object_kind(self):
        ring = self.actions.object_node("emerald ring")
        atom = self.api.get(ring)
        self.assertEqual(atom.kind, self.actions.object_kind)
        self.assertTrue(self.actions.is_object(ring))

    def test_object_node_dedups_by_label(self):
        first = self.actions.object_node("claw machine")
        second = self.actions.object_node("claw machine")
        self.assertEqual(first, second)
        matches = [
            atom_id for atom_id in self.api.find_by_label("claw machine")
            if self.actions.is_object(atom_id)
        ]
        self.assertEqual(matches, [first])

    def test_object_node_resolves_hand_minted_object(self):
        # A node minted directly under the Object kind (the way the
        # older fixtures do it) is the same object the factory
        # resolves — dedup is by label and kind, not by birthplace.
        hand = self.api.create_node(
            "hammer", kind=self.api.kind("Object"))
        self.assertEqual(self.actions.object_node("hammer"), hand)

    def test_object_node_ignores_same_label_other_kind(self):
        planet = self.api.create_node(
            "Mercury", kind=self.api.kind("Person"))
        thing = self.actions.object_node("Mercury")
        self.assertNotEqual(thing, planet)
        self.assertTrue(self.actions.is_object(thing))
        self.assertFalse(self.actions.is_object(planet))
        self.assertEqual(self.actions.object_node("Mercury"), thing)

    def test_object_node_rejects_bad_labels(self):
        with self.assertRaises(TypeError):
            self.actions.object_node("")
        with self.assertRaises(TypeError):
            self.actions.object_node(None)
        with self.assertRaises(TypeError):
            self.actions.object_node(42)

    def test_object_minting_is_not_vocabulary_gated(self):
        # Instances are ungated — the exact opposite of act terms,
        # whose labels must be in the approved vocabulary.
        with self.assertRaises(UnapprovedTermError):
            self.actions.acts.act_node("flibbertigibbet")
        thing = self.actions.object_node("flibbertigibbet")
        self.assertTrue(self.actions.is_object(thing))

    def test_is_object_rejects_non_objects(self):
        self.assertFalse(self.actions.is_object(self.robert))
        self.assertFalse(
            self.actions.is_object(self.actions.acts.act_node("massage")))


class ObjectKindGateTests(unittest.TestCase):
    """The verbs' object slots are kind-gated, IsA-aware: subkinds
    of Object pass, everything else is refused."""

    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.actions = install(self.api)
        self.rel = install_relational(self.api)
        person = self.api.kind("Person")
        self.robert = self.api.create_node("Robert", kind=person)
        self.elena = self.api.create_node("Elena", kind=person)

    def _toy(self, label):
        toy_kind = self.api.kind("Toy")
        if not self.rel.has(self.rel.IsA, toy_kind,
                            self.actions.object_kind):
            self.rel.relate(
                self.rel.IsA, toy_kind, self.actions.object_kind)
        return self.api.create_node(label, kind=toy_kind)

    def test_object_verbs_refuse_person_as_object(self):
        for verb in (self.actions.use, self.actions.wears,
                     self.actions.play):
            with self.assertRaises(TypeError):
                verb(self.robert, self.elena)

    def test_object_verbs_refuse_act_term_as_object(self):
        massage = self.actions.acts.act_node("massage")
        for verb in (self.actions.use, self.actions.wears,
                     self.actions.play):
            with self.assertRaises(TypeError):
                verb(self.robert, massage)

    def test_object_verbs_accept_factory_objects(self):
        hammer = self.actions.object_node("hammer")
        self.actions.use(self.robert, hammer)
        self.assertTrue(self.actions.has(
            self.actions.Use, self.robert, hammer))

    def test_object_subkind_passes_the_gates(self):
        vibe = self._toy("vibe")
        self.assertTrue(self.actions.is_object(vibe))
        self.actions.use(self.robert, vibe)
        self.assertTrue(self.actions.has(
            self.actions.Use, self.robert, vibe))
        # ... including as a Gives payload with a custody receipt.
        application = self.actions.give(self.robert, self.elena, vibe)
        self.assertEqual(
            self.actions.payload_of(application), vibe)
        transition = self.actions.custody_receipt(application)
        _before, after = self.api.transition_args(transition)
        possession = install_possession(self.api)
        self.assertEqual(self.api.get(after).predicate, possession.Holds)


if __name__ == "__main__":
    unittest.main()
