"""Permanent tests for the speech predicate module."""

import unittest

from atomforge import AtomSpaceAPI
from atomforge.infrastructure import UnknownAtomError
from atomforge.stdagent.speech import install


class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.speech = install(self.api)
        self.kind = self.api.kind("Person")
        self.robert = self.api.create_node("Robert", kind=self.kind)
        self.elena = self.api.create_node("Elena", kind=self.kind)

    def test_vocabulary_is_exactly_says(self):
        self.assertEqual(set(self.speech.predicates), {"Says"})

    def test_install_is_idempotent(self):
        self.assertIs(install(self.api), self.speech)

    def test_say_with_text_mints_a_claim_node(self):
        saying = self.speech.say(self.robert, "the deposits come back")
        self.assertTrue(self.speech.is_saying(saying))
        self.assertEqual(self.speech.speaker_of(saying), self.robert)
        claim = self.speech.claim_of(saying)
        atom = self.api.get(claim)
        self.assertEqual(atom.label, "the deposits come back")
        self.assertEqual(atom.kind, self.speech.claim_kind)

    def test_same_text_resolves_to_the_same_claim_atom(self):
        first = self.speech.say(self.robert, "yours, completely")
        second = self.speech.say(self.elena, "yours, completely")
        self.assertNotEqual(first, second)  # different speakers
        self.assertEqual(
            self.speech.claim_of(first), self.speech.claim_of(second)
        )

    def test_same_saying_dedups_to_one_atom(self):
        first = self.speech.say(self.robert, "I'll bring the soup")
        second = self.speech.say(self.robert, "I'll bring the soup")
        self.assertEqual(first, second)

    def test_say_with_proposition_atom_claim(self):
        likes = self.api.predicate("Likes", arity=2)
        steak = self.api.create_node("Steak", kind=self.kind)
        proposition = self.api.create_predicate(likes, self.elena, steak)
        saying = self.speech.say(self.robert, proposition)
        self.assertEqual(self.speech.claim_of(saying), proposition)

    def test_say_with_unknown_claim_raises(self):
        with self.assertRaises(UnknownAtomError):
            self.speech.say(self.robert, 999999)

    def test_say_with_deleted_claim_raises(self):
        claim = self.speech.claim_node("soon forgotten")
        self.api.delete(claim)
        with self.assertRaises(UnknownAtomError):
            self.speech.say(self.robert, claim)

    def test_empty_claim_text_refused(self):
        with self.assertRaises(TypeError):
            self.speech.say(self.robert, "")

    def test_has_and_sayings_by(self):
        saying = self.speech.say(self.robert, "meet at the chapel")
        claim = self.speech.claim_of(saying)
        self.assertTrue(self.speech.has(self.speech.Says, self.robert, claim))
        self.assertFalse(self.speech.has(self.speech.Says, self.elena, claim))
        self.assertEqual(self.speech.sayings_by(self.robert), [saying])
        self.assertEqual(self.speech.sayings_of(claim), [saying])

    def test_speaker_of_rejects_non_saying(self):
        with self.assertRaises(TypeError):
            self.speech.speaker_of(self.robert)

    def test_relate_rejects_foreign_predicate(self):
        other = self.api.predicate("Other", arity=2)
        with self.assertRaises(TypeError):
            self.speech.relate(other, self.robert, self.elena)


if __name__ == "__main__":
    unittest.main()
