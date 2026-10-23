"""Permanent tests for Conviction and its certainty chain.

Conviction is the epistemic module's non-tier category: a reading
treated as given, carrying a 0-100 certainty kept as a running total
of Transition-chained, cause-named records.  These tests pin the
lifecycle: assertion only with a genesis record, evidence moving
the dial in both directions with the cause named, the negation lock
above zero, relinquishment at zero, promotion as the displacement
mechanism, falling back to Believes, and premise use at Believes
strength.
"""

import unittest

from atomforge import AtomSpaceAPI
from atomforge.infrastructure import (
    InvalidAtomOperationError,
    UnknownAtomError,
)
from atomforge.stdagent.epistemic import install
from atomforge.stdagent.logic import install as install_logic
from atomforge.stdagent.speech import install as install_speech


class ConvictionTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.epi = install(self.api)
        self.speech = install_speech(self.api)
        self.logic = install_logic(self.api)
        self.kind = self.api.kind("Thing")
        self.elena = self.api.create_node("Elena", kind=self.kind)
        self.reading = self.speech.claim_node(
            "he studies her like a person, not a problem")
        self.opposed = self.speech.claim_node(
            "he studies her like a problem to solve")
        self.scene = self.api.create_node(
            "Scene: the long talk", kind=self.kind)
        self.counter_fact = self.speech.claim_node(
            "he reached for the checklist mid-sentence")

    def convict_reading(self, certainty=85):
        return self.epi.convict(
            self.elena, self.reading,
            certainty=certainty, cause=self.scene, on="W1D3")

    # -- assertion shape -----------------------------------------------------

    def test_convict_creates_atom_and_genesis_certainty(self):
        atom = self.convict_reading()
        self.assertTrue(self.epi.is_conviction(atom))
        self.assertEqual(
            self.epi.conviction_of(self.elena, self.reading), atom)
        self.assertEqual(
            self.epi.certainty_of(self.elena, self.reading), 85)

    def test_conviction_is_not_a_tier(self):
        self.convict_reading()
        self.assertIsNone(self.epi.tier_of(self.elena, self.reading))
        self.assertFalse(self.epi.holds(self.elena, self.reading))

    def test_relate_refuses_conviction(self):
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Conviction, self.elena, self.reading)

    def test_convict_refuses_unknown_cause(self):
        with self.assertRaises(UnknownAtomError):
            self.epi.convict(
                self.elena, self.reading, certainty=50, cause=999999)

    def test_genesis_certainty_must_be_1_to_100(self):
        for bad in (0, 101, -5):
            with self.assertRaises(TypeError):
                self.epi.convict(
                    self.elena, self.reading,
                    certainty=bad, cause=self.scene)
        with self.assertRaises(TypeError):
            self.epi.convict(
                self.elena, self.reading,
                certainty="high", cause=self.scene)

    def test_second_convict_while_standing_refused(self):
        self.convict_reading()
        with self.assertRaises(InvalidAtomOperationError):
            self.convict_reading(certainty=40)

    # -- the dial --------------------------------------------------------------

    def test_confirming_evidence_raises_and_counter_lowers(self):
        self.convict_reading(70)
        self.epi.adjust_certainty(
            self.elena, self.reading, delta=10, cause=self.scene)
        self.assertEqual(
            self.epi.certainty_of(self.elena, self.reading), 80)
        self.epi.adjust_certainty(
            self.elena, self.reading, delta=-35,
            cause=self.counter_fact)
        self.assertEqual(
            self.epi.certainty_of(self.elena, self.reading), 45)

    def test_adjust_to_absolute_value(self):
        self.convict_reading(70)
        record = self.epi.adjust_certainty(
            self.elena, self.reading, to=25, cause=self.counter_fact)
        self.assertEqual(
            self.epi.certainty_of(self.elena, self.reading), 25)
        self.assertIsNotNone(record)

    def test_adjust_requires_exactly_one_of_delta_or_to(self):
        self.convict_reading()
        with self.assertRaises(TypeError):
            self.epi.adjust_certainty(
                self.elena, self.reading, cause=self.scene)
        with self.assertRaises(TypeError):
            self.epi.adjust_certainty(
                self.elena, self.reading, cause=self.scene,
                delta=5, to=50)

    def test_adjust_out_of_range_refused_and_chain_unchanged(self):
        self.convict_reading(90)
        with self.assertRaises(TypeError):
            self.epi.adjust_certainty(
                self.elena, self.reading, delta=20, cause=self.scene)
        self.assertEqual(
            self.epi.certainty_of(self.elena, self.reading), 90)
        self.assertEqual(
            len(self.epi.certainty_history(self.elena, self.reading)), 1)

    def test_history_walks_values_causes_and_dates(self):
        self.convict_reading(70)
        self.epi.adjust_certainty(
            self.elena, self.reading, delta=-30,
            cause=self.counter_fact, on="W1D6")
        history = self.epi.certainty_history(self.elena, self.reading)
        self.assertEqual([h[0] for h in history], [70, 40])
        self.assertEqual(history[0][1], self.scene)
        self.assertEqual(history[0][2], "W1D3")
        self.assertEqual(history[1][1], self.counter_fact)
        self.assertEqual(history[1][2], "W1D6")

    def test_history_of_no_conviction_is_empty(self):
        self.assertEqual(
            self.epi.certainty_history(self.elena, self.reading), [])
        self.assertIsNone(
            self.epi.certainty_of(self.elena, self.reading))

    # -- the lock, relinquishment, re-adoption --------------------------------

    def test_negation_lock_and_opposed_conviction(self):
        self.logic.relate(
            self.logic.Contradicts, self.reading, self.opposed)
        self.convict_reading(80)
        self.assertTrue(
            self.epi.negation_locked(self.elena, self.reading))
        with self.assertRaises(InvalidAtomOperationError):
            self.epi.convict(
                self.elena, self.opposed, certainty=60, cause=self.scene)

    def test_relinquishment_unlocks_and_readoption_chains_on(self):
        self.convict_reading(60)
        self.epi.adjust_certainty(
            self.elena, self.reading, to=0, cause=self.counter_fact)
        self.assertEqual(
            self.epi.certainty_of(self.elena, self.reading), 0)
        self.assertFalse(
            self.epi.negation_locked(self.elena, self.reading))
        with self.assertRaises(InvalidAtomOperationError):
            self.epi.adjust_certainty(
                self.elena, self.reading, delta=10, cause=self.scene)
        self.epi.convict(
            self.elena, self.reading, certainty=30, cause=self.scene)
        self.assertEqual(
            self.epi.certainty_of(self.elena, self.reading), 30)
        values = [h[0] for h in
                  self.epi.certainty_history(self.elena, self.reading)]
        self.assertEqual(values, [60, 0, 30])

    def test_opposed_conviction_allowed_after_relinquishment(self):
        self.logic.relate(
            self.logic.Contradicts, self.reading, self.opposed)
        self.convict_reading(80)
        self.epi.adjust_certainty(
            self.elena, self.reading, to=0, cause=self.counter_fact)
        self.epi.convict(
            self.elena, self.opposed, certainty=55, cause=self.scene)
        self.assertEqual(
            self.epi.certainty_of(self.elena, self.opposed), 55)

    # -- migration -------------------------------------------------------------

    def test_promote_hardens_a_belief_with_transition(self):
        self.epi.relate(self.epi.Believes, self.elena, self.reading)
        atom = self.epi.promote(
            self.elena, self.reading, certainty=75, cause=self.scene)
        self.assertTrue(self.epi.is_conviction(atom))
        self.assertEqual(
            self.epi.certainty_of(self.elena, self.reading), 75)
        believes_atom = None
        for result in self.api.search(predicate=self.epi.Believes):
            if result.atom.args == (self.elena, self.reading):
                believes_atom = result.atom.id
        transitions = [
            self.api.transition_args(t)
            for t in self.api.in_transitions(atom)
        ]
        self.assertIn((believes_atom, atom), transitions)

    def test_promote_requires_believes(self):
        with self.assertRaises(InvalidAtomOperationError):
            self.epi.promote(
                self.elena, self.reading, certainty=50, cause=self.scene)
        self.epi.relate(
            self.epi.Suspects, self.elena, self.reading,
            evidence=(self.scene,))
        with self.assertRaises(InvalidAtomOperationError):
            self.epi.promote(
                self.elena, self.reading, certainty=50, cause=self.scene)

    def test_promotion_displaces_only_after_relinquishment(self):
        self.logic.relate(
            self.logic.Contradicts, self.reading, self.opposed)
        self.convict_reading(80)
        self.epi.relate(self.epi.Believes, self.elena, self.opposed)
        with self.assertRaises(InvalidAtomOperationError):
            self.epi.promote(
                self.elena, self.opposed, certainty=60, cause=self.scene)
        self.epi.adjust_certainty(
            self.elena, self.reading, to=0, cause=self.counter_fact)
        self.epi.promote(
            self.elena, self.opposed, certainty=60, cause=self.scene)
        self.assertEqual(
            self.epi.certainty_of(self.elena, self.opposed), 60)

    def test_fall_back_only_from_relinquished(self):
        self.convict_reading(50)
        with self.assertRaises(InvalidAtomOperationError):
            self.epi.fall_back(self.elena, self.reading)
        self.epi.adjust_certainty(
            self.elena, self.reading, to=0, cause=self.counter_fact)
        believes = self.epi.fall_back(self.elena, self.reading)
        self.assertEqual(
            self.epi.tier_of(self.elena, self.reading), "Believes")
        conviction = self.epi.conviction_of(self.elena, self.reading)
        transitions = [
            self.api.transition_args(t)
            for t in self.api.in_transitions(believes)
        ]
        self.assertIn((conviction, believes), transitions)

    def test_revise_refuses_conviction_atoms(self):
        atom = self.convict_reading()
        with self.assertRaises(TypeError):
            self.epi.revise(atom, "Believes")

    # -- premise use -----------------------------------------------------------

    def test_conviction_premise_concludes_at_believes(self):
        conviction = self.convict_reading(90)
        conclusion = self.speech.claim_node(
            "his attention in a room is diagnostic, not social")
        atom = self.epi.relate(
            self.epi.Believes, self.elena, conclusion,
            via="deduced", premises=(conviction,))
        self.assertIsNotNone(atom)
        self.assertIn(
            self.reading, self.epi.evidence_of(conclusion))

    def test_conviction_premise_cannot_buy_knows(self):
        conviction = self.convict_reading(90)
        conclusion = self.speech.claim_node(
            "his attention in a room is diagnostic, not social")
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Knows, self.elena, conclusion,
                via="deduced", premises=(conviction,))


if __name__ == "__main__":
    unittest.main()
