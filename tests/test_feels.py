"""Permanent tests for the feels predicate module."""

import unittest

from atomforge import AtomSpaceAPI
from atomforge.infrastructure import UnknownAtomError
from atomforge.stdagent.feels import install


class FeelsTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.feels = install(self.api)
        self.kind = self.api.kind("Person")
        self.robert = self.api.create_node("Robert", kind=self.kind)
        self.elena = self.api.create_node("Elena", kind=self.kind)

    def test_vocabulary_is_exactly_feels_and_because(self):
        self.assertEqual(set(self.feels.predicates), {"Feels", "Because"})

    def test_install_is_idempotent(self):
        self.assertIs(install(self.api), self.feels)

    def test_feeling_node_dedups_same_text(self):
        first = self.feels.feeling_node("insecure")
        second = self.feels.feeling_node("insecure")
        self.assertEqual(first, second)
        self.assertTrue(self.feels.is_feeling(first))
        atom = self.api.get(first)
        self.assertEqual(atom.kind, self.feels.feeling_kind)

    def test_feeling_node_never_normalizes(self):
        # The library does not merge twins: naming discipline is the
        # caller's, and two texts stay two atoms even when adjacent.
        tired_hungry = self.feels.feeling_node("tiredandhungry")
        hungry_tired = self.feels.feeling_node("hungryandtired")
        self.assertNotEqual(tired_hungry, hungry_tired)

    def test_feeling_node_rejects_empty_text(self):
        with self.assertRaises(TypeError):
            self.feels.feeling_node("")

    def test_feeling_node_does_not_steal_a_claim_with_same_label(self):
        other_kind = self.api.kind("Claim")
        claim = self.api.create_node("calm", kind=other_kind)
        feeling = self.feels.feeling_node("calm")
        self.assertNotEqual(feeling, claim)
        self.assertTrue(self.feels.is_feeling(feeling))

    def test_feel_with_text_mints_and_attaches(self):
        atom_id = self.feels.feel(self.elena, "insecure")
        feeling = self.feels.feeling_node("insecure")
        self.assertTrue(
            self.feels.has(self.feels.Feels, self.elena, feeling)
        )
        self.assertEqual(self.feels.feeling_atoms_of(self.elena), [feeling])
        self.assertEqual(self.feels.feelings_of(self.elena), [atom_id])

    def test_feel_dedups_same_holder_and_feeling(self):
        first = self.feels.feel(self.elena, "safe")
        second = self.feels.feel(self.elena, "safe")
        self.assertEqual(first, second)

    def test_occurrences_are_the_feelings_history(self):
        feeling = self.feels.feeling_node("insecure")
        mine = self.feels.feel(self.elena, feeling)
        his = self.feels.feel(self.robert, feeling)
        self.assertEqual(set(self.feels.occurrences(feeling)), {mine, his})
        self.assertEqual(
            set(self.feels.holders_of(feeling)), {self.elena, self.robert}
        )

    def test_feel_rejects_non_feeling_node(self):
        steak = self.api.create_node("Steak", kind=self.kind)
        with self.assertRaises(TypeError):
            self.feels.feel(self.elena, steak)

    def test_feel_rejects_unknown_holder(self):
        with self.assertRaises(UnknownAtomError):
            self.feels.feel(999999, "calm")

    def test_feel_rejects_deleted_feeling(self):
        feeling = self.feels.feeling_node("soon forgotten")
        self.api.delete(feeling)
        with self.assertRaises(UnknownAtomError):
            self.feels.feel(self.elena, feeling)

    def test_because_points_feeling_at_its_claim(self):
        claim_kind = self.api.kind("Claim")
        claim = self.api.create_node("he will leave", kind=claim_kind)
        feeling = self.feels.feeling_node("afraidhewillleave")
        self.feels.feel(self.elena, feeling)
        because = self.feels.because(feeling, claim)
        self.assertTrue(
            self.feels.has(self.feels.Because, feeling, claim)
        )
        self.assertEqual(self.feels.reasons_for(feeling), [claim])
        self.assertEqual(self.feels.explained_by(claim), [feeling])
        self.assertIsNotNone(because)

    def test_because_is_generic_not_feeling_private(self):
        deposits = self.api.create_node("the deposits", kind=self.kind)
        duty = self.api.create_node("the obligation", kind=self.kind)
        self.feels.because(duty, deposits)
        self.assertEqual(self.feels.reasons_for(duty), [deposits])

    def test_because_rejects_unknown_ground(self):
        feeling = self.feels.feeling_node("uneasy")
        with self.assertRaises(UnknownAtomError):
            self.feels.because(feeling, 999999)

    def test_relate_rejects_foreign_predicate(self):
        other = self.api.predicate("Other", arity=2)
        with self.assertRaises(TypeError):
            self.feels.relate(other, self.robert, self.elena)

    def test_has_rejects_foreign_predicate(self):
        other = self.api.predicate("Other", arity=2)
        with self.assertRaises(TypeError):
            self.feels.has(other, self.robert, self.elena)


if __name__ == "__main__":
    unittest.main()
