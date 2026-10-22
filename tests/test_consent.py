"""Permanent tests for the consent domain module."""

import unittest

from atomforge import AtomSpaceAPI
from atomforge.infrastructure import UnknownAtomError
from atomforge.stdagent.acts import install as install_acts
from atomforge.stdagent.logic import install as install_logic
from atomforge.stdagent.speech import install as install_speech
from atomforge.domain.consent import install


class ConsentTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.consent = install(self.api)
        self.acts = install_acts(self.api)
        self.speech = install_speech(self.api)
        self.logic = install_logic(self.api)
        self.kind = self.api.kind("Person")
        self.robert = self.api.create_node("Robert", kind=self.kind)
        self.elena = self.api.create_node("Elena", kind=self.kind)
        self.hug = self.acts.act_node("hug")
        self.photographs = self.acts.act_node("being photographed")

    def test_vocabulary_is_exactly_the_three(self):
        self.assertEqual(
            set(self.consent.predicates),
            {"HardLimit", "ConsentsTo", "Permits"},
        )

    def test_install_is_idempotent(self):
        self.assertIs(install(self.api), self.consent)

    def test_hard_limit_state(self):
        self.consent.relate(self.consent.HardLimit, self.elena, self.photographs)
        self.assertEqual(
            self.consent.consent_state(self.elena, self.photographs),
            "hard_limit",
        )
        self.assertEqual(
            len(self.consent.hard_limits_of(self.elena)), 1
        )

    def test_consents_and_permits_states(self):
        self.consent.relate(self.consent.ConsentsTo, self.elena, self.hug)
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug), "consents"
        )
        other = self.acts.act_node("holding hands")
        self.consent.relate(self.consent.Permits, self.elena, other)
        self.assertEqual(
            self.consent.consent_state(self.elena, other), "permits"
        )
        unasked = self.acts.act_node("slow dancing")
        self.assertIsNone(self.consent.consent_state(self.elena, unasked))

    def test_consent_rejects_non_act_target(self):
        steak = self.api.create_node("Steak", kind=self.kind)
        with self.assertRaises(TypeError):
            self.consent.relate(self.consent.ConsentsTo, self.elena, steak)

    def test_consent_rejects_unknown_holder(self):
        with self.assertRaises(UnknownAtomError):
            self.consent.relate(self.consent.ConsentsTo, 999999, self.hug)

    def test_exclusions_are_data_on_the_consent_atom(self):
        no_lights = self.speech.claim_node("with the lights on")
        consent = self.consent.relate(
            self.consent.ConsentsTo, self.elena, self.hug,
            excludes=(no_lights,),
        )
        self.assertEqual(self.consent.exclusions_of(consent), [no_lights])
        # And the consent itself still stands, qualified, not absent.
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug), "consents"
        )

    def test_exclusion_of_the_act_itself_is_refused(self):
        with self.assertRaises(TypeError):
            self.consent.relate(
                self.consent.ConsentsTo, self.elena, self.hug,
                excludes=(self.hug,),
            )

    def test_unknown_exclusion_is_refused_and_writes_nothing(self):
        with self.assertRaises(UnknownAtomError):
            self.consent.relate(
                self.consent.ConsentsTo, self.elena, self.hug,
                excludes=(999999,),
            )
        self.assertIsNone(self.consent.consent_state(self.elena, self.hug))

    def test_declaration_grounds_the_consent_in_evidence(self):
        saying = self.speech.say(self.elena, "hugs are always fine")
        consent = self.consent.relate(
            self.consent.ConsentsTo, self.elena, self.hug,
            declaration=saying,
        )
        grounds = self.consent.epistemic.evidence_of(consent)
        self.assertEqual(grounds, [saying])

    def test_someone_elses_words_cannot_declare_my_consent(self):
        saying = self.speech.say(self.robert, "she said hugs are fine")
        with self.assertRaises(TypeError):
            self.consent.relate(
                self.consent.ConsentsTo, self.elena, self.hug,
                declaration=saying,
            )
        self.assertIsNone(self.consent.consent_state(self.elena, self.hug))

    def test_non_saying_declaration_is_refused(self):
        with self.assertRaises(TypeError):
            self.consent.relate(
                self.consent.ConsentsTo, self.elena, self.hug,
                declaration=self.hug,
            )

    def test_conflict_is_preserved_and_reported(self):
        limit = self.consent.relate(
            self.consent.HardLimit, self.elena, self.photographs
        )
        consent = self.consent.relate(
            self.consent.ConsentsTo, self.elena, self.photographs
        )
        # Both stand; neither was erased or silently preferred.
        self.assertTrue(
            self.consent.has(
                self.consent.HardLimit, self.elena, self.photographs
            )
        )
        self.assertTrue(
            self.consent.has(
                self.consent.ConsentsTo, self.elena, self.photographs
            )
        )
        self.assertEqual(
            self.consent.consent_state(self.elena, self.photographs),
            "conflicted",
        )
        contradictions = self.api.find_predicates(
            self.logic.Contradicts, consent, limit
        )
        self.assertEqual(len(contradictions), 1)

    def test_permits_against_hard_limit_also_conflicts(self):
        self.consent.relate(
            self.consent.HardLimit, self.elena, self.photographs
        )
        self.consent.relate(
            self.consent.Permits, self.elena, self.photographs
        )
        self.assertEqual(
            self.consent.consent_state(self.elena, self.photographs),
            "conflicted",
        )

    def test_relate_rejects_foreign_predicate(self):
        other = self.api.predicate("Other", arity=2)
        with self.assertRaises(TypeError):
            self.consent.relate(other, self.elena, self.hug)


if __name__ == "__main__":
    unittest.main()
