"""Permanent tests for the epistemic predicate module."""

import unittest

from atomforge import AtomSpaceAPI
from atomforge.atoms import Ligature
from atomforge.infrastructure import UnknownAtomError
from atomforge.stdagent.epistemic import install
from atomforge.stdagent.speech import install as install_speech


class EpistemicTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.epi = install(self.api)
        self.speech = install_speech(self.api)
        self.kind = self.api.kind("Thing")
        self.elena = self.api.create_node("Elena", kind=self.kind)
        self.robert = self.api.create_node("Robert", kind=self.kind)
        self.claim = self.speech.claim_node("the yellow rule stops him")
        self.ground = self.speech.claim_node("he stopped the one time she tried")
        self.scene = self.api.create_node("Scene: the Poe Bar", kind=self.kind)

    def ligature_names(self, atom_id):
        return [
            atom.name
            for atom in (
                self.api.get(lig_id)
                for lig_id in self.api.in_ligatures(atom_id)
            )
            if isinstance(atom, Ligature)
        ]

    def believe_ground(self):
        self.epi.relate(self.epi.Believes, self.elena, self.ground)

    # -- vocabulary / install ------------------------------------------------

    def test_vocabulary_is_exact(self):
        self.assertEqual(
            set(self.epi.predicates),
            {"Believes", "Suspects", "Knows", "EvidenceFor", "ModelError"},
        )

    def test_install_is_idempotent(self):
        self.assertIs(install(self.api), self.epi)

    def test_foreign_predicate_refused(self):
        other = self.api.predicate("Other", arity=2)
        with self.assertRaises(TypeError):
            self.epi.relate(other, self.elena, self.claim)

    def test_unknown_claim_refused(self):
        with self.assertRaises(UnknownAtomError):
            self.epi.relate(self.epi.Believes, self.elena, 999999)

    # -- the ladder ------------------------------------------------------------

    def test_believes_needs_no_evidence(self):
        atom = self.epi.relate(self.epi.Believes, self.elena, self.claim)
        self.assertTrue(self.epi.has(self.epi.Believes, self.elena, self.claim))
        self.assertEqual(self.epi.tier_of(self.elena, self.claim), "Believes")
        self.assertIsNotNone(atom)

    def test_suspects_without_ground_refused(self):
        with self.assertRaises(TypeError):
            self.epi.relate(self.epi.Suspects, self.elena, self.claim)

    def test_suspects_with_evidence_records_ground(self):
        self.epi.relate(
            self.epi.Suspects, self.elena, self.claim, evidence=(self.ground,)
        )
        self.assertEqual(self.epi.evidence_of(self.claim), [self.ground])

    def test_knows_without_evidence_refused(self):
        with self.assertRaises(TypeError):
            self.epi.relate(self.epi.Knows, self.elena, self.claim)

    def test_knows_with_unbelieved_evidence_refused(self):
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Knows, self.elena, self.claim,
                evidence=(self.ground,),
            )

    def test_knows_with_believed_evidence(self):
        self.believe_ground()
        self.epi.relate(
            self.epi.Knows, self.elena, self.claim, evidence=(self.ground,)
        )
        self.assertEqual(self.epi.tier_of(self.elena, self.claim), "Knows")
        self.assertEqual(self.epi.evidence_of(self.claim), [self.ground])

    def test_knows_implies_believes_at_query_time_only(self):
        self.believe_ground()
        self.epi.relate(
            self.epi.Knows, self.elena, self.claim, evidence=(self.ground,)
        )
        self.assertTrue(self.epi.has(self.epi.Believes, self.elena, self.claim))
        # Not materialized: raw assertion lookup for Believes is empty.
        self.assertFalse(
            self.api.has_predicate(self.epi.Believes, self.elena, self.claim)
        )

    def test_second_order_claim_wrapping(self):
        likes = self.api.predicate("Likes", arity=2)
        steak = self.api.create_node("Steak", kind=self.kind)
        his_stance = self.api.create_predicate(likes, self.robert, steak)
        self.epi.relate(self.epi.Believes, self.elena, his_stance)
        self.assertTrue(self.epi.holds(self.elena, his_stance))
        self.assertFalse(self.epi.holds(self.robert, his_stance))

    # -- acquisition modes -----------------------------------------------------

    def test_learned_requires_teacher(self):
        saying = self.speech.say(self.robert, self.claim)
        with self.assertRaises(TypeError):
            self.epi.relate(self.epi.Believes, self.elena, saying, via="learned")

    def test_learned_teacher_must_match_speaker(self):
        saying = self.speech.say(self.robert, self.claim)
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Believes, self.elena, saying,
                via="learned", teacher=self.elena,
            )

    def test_learned_records_teacher_ligature(self):
        saying = self.speech.say(self.robert, self.claim)
        atom = self.epi.relate(
            self.epi.Believes, self.elena, saying,
            via="learned", teacher=self.robert,
        )
        self.assertIn("Teacher", self.ligature_names(atom))

    def test_discovered_requires_scene_and_grounds_claim(self):
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Believes, self.elena, self.claim, via="discovered"
            )
        self.epi.relate(
            self.epi.Knows, self.elena, self.claim,
            via="discovered", scene=self.scene,
        )
        self.assertIn(self.scene, self.epi.evidence_of(self.claim))

    # -- discovered via declaration: witnessed performatives -------------

    def performative_claim(self):
        permits = self.api.predicate("Permits", arity=2)
        act = self.api.create_node("sleep-use", kind=self.kind)
        return self.api.create_predicate(permits, self.robert, act)

    def test_knows_via_witnessed_declaration(self):
        claim = self.performative_claim()
        saying = self.speech.say(
            self.robert, "blanket permission while you sleep, except anal"
        )
        self.epi.relate(
            self.epi.Knows, self.elena, claim,
            via="discovered", declaration=saying,
        )
        self.assertEqual(self.epi.tier_of(self.elena, claim), "Knows")
        self.assertIn(saying, self.epi.evidence_of(claim))

    def test_declaration_is_self_warranting(self):
        # Elena need not hold any stance on the saying itself: she was
        # there when the permission was created, as with a scene.
        claim = self.performative_claim()
        saying = self.speech.say(self.robert, "you may, whenever")
        self.assertIsNone(self.epi.tier_of(self.elena, saying))
        self.epi.relate(
            self.epi.Knows, self.elena, claim,
            via="discovered", declaration=saying,
        )

    def test_declaration_speaker_must_be_the_bound_party(self):
        claim = self.performative_claim()
        hearsay = self.speech.say(self.elena, "he said it is allowed")
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Knows, self.elena, claim,
                via="discovered", declaration=hearsay,
            )
        self.assertIsNone(self.epi.tier_of(self.elena, claim))

    def test_declaration_must_be_a_saying(self):
        claim = self.performative_claim()
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Knows, self.elena, claim,
                via="discovered", declaration=self.claim,
            )

    def test_declaration_claim_must_be_a_predicate(self):
        saying = self.speech.say(self.robert, "the yellow rule stops him")
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Knows, self.elena, self.claim,
                via="discovered", declaration=saying,
            )

    def test_discovered_takes_scene_or_declaration_not_both(self):
        claim = self.performative_claim()
        saying = self.speech.say(self.robert, "you may, whenever")
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Knows, self.elena, claim,
                via="discovered", scene=self.scene, declaration=saying,
            )

    def test_declaration_requires_the_discovered_mode(self):
        claim = self.performative_claim()
        saying = self.speech.say(self.robert, "you may, whenever")
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Knows, self.elena, claim, declaration=saying,
            )
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Believes, self.elena, claim,
                via="learned", teacher=self.robert, declaration=saying,
            )

    def test_inferred_only_enters_at_suspects(self):
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Knows, self.elena, self.claim,
                via="inferred", sources=(self.ground,),
                evidence=(self.ground,),
            )
        atom = self.epi.relate(
            self.epi.Suspects, self.elena, self.claim,
            via="inferred", sources=(self.ground,),
        )
        self.assertIn("Source", self.ligature_names(atom))

    def test_deduced_requires_held_premises(self):
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Believes, self.elena, self.claim,
                via="deduced", premises=(self.ground,),
            )

    def test_deduced_tier_capped_by_weakest_premise(self):
        self.believe_ground()
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Knows, self.elena, self.claim,
                via="deduced", premises=(self.ground,),
                evidence=(self.ground,),
            )
        atom = self.epi.relate(
            self.epi.Believes, self.elena, self.claim,
            via="deduced", premises=(self.ground,),
        )
        self.assertIn("Premise", self.ligature_names(atom))

    def test_deduced_from_known_premise_can_know(self):
        self.believe_ground()
        inner = self.speech.claim_node("inner premise")
        self.epi.relate(self.epi.Believes, self.elena, inner)
        self.epi.relate(
            self.epi.Knows, self.elena, self.ground, evidence=(inner,)
        )
        self.epi.relate(
            self.epi.Knows, self.elena, self.claim,
            via="deduced", premises=(self.ground,),
            evidence=(self.ground,),
        )
        self.assertEqual(self.epi.tier_of(self.elena, self.claim), "Knows")

    def test_deduced_knows_from_known_premise_needs_no_separate_evidence(self):
        self.believe_ground()
        inner = self.speech.claim_node("inner premise")
        self.epi.relate(self.epi.Believes, self.elena, inner)
        self.epi.relate(
            self.epi.Knows, self.elena, self.ground, evidence=(inner,)
        )
        atom = self.epi.relate(
            self.epi.Knows, self.elena, self.claim,
            via="deduced", premises=(self.ground,),
        )
        self.assertEqual(self.epi.tier_of(self.elena, self.claim), "Knows")
        self.assertIn("Premise", self.ligature_names(atom))

    def test_deduced_believes_from_known_premise(self):
        self.believe_ground()
        inner = self.speech.claim_node("inner premise")
        self.epi.relate(self.epi.Believes, self.elena, inner)
        self.epi.relate(
            self.epi.Knows, self.elena, self.ground, evidence=(inner,)
        )
        self.epi.relate(
            self.epi.Believes, self.elena, self.claim,
            via="deduced", premises=(self.ground,),
        )
        self.assertEqual(self.epi.tier_of(self.elena, self.claim), "Believes")

    def test_mode_arguments_without_via_refused(self):
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Believes, self.elena, self.claim,
                teacher=self.robert,
            )

    # -- revision ----------------------------------------------------------------

    def test_revise_promotes_with_transition(self):
        old = self.epi.relate(self.epi.Believes, self.elena, self.claim)
        self.epi.relate(self.epi.Believes, self.elena, self.ground)
        new = self.epi.revise(old, "Knows", evidence=(self.ground,))
        transitions = self.api.in_transitions(old)
        self.assertTrue(transitions)
        args = self.api.transition_args(next(iter(transitions)))
        self.assertEqual(args, (old, new))
        self.assertEqual(self.epi.tier_of(self.elena, self.claim), "Knows")

    def test_revise_demotes_knows_to_believes(self):
        self.believe_ground()
        known = self.epi.relate(
            self.epi.Knows, self.elena, self.claim, evidence=(self.ground,)
        )
        self.epi.revise(known, "Believes")
        self.assertTrue(self.epi.holds(self.elena, self.claim))

    def test_supersede_mismatched_claim_refused(self):
        old = self.epi.relate(self.epi.Believes, self.elena, self.claim)
        other_claim = self.speech.claim_node("a different claim")
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.Suspects, self.elena, other_claim,
                evidence=(self.ground,), supersedes=old,
            )

    # -- evidence ------------------------------------------------------------------

    def test_evidence_for_standalone_and_relate_path(self):
        atom = self.epi.relate(self.epi.EvidenceFor, self.claim, self.scene)
        self.assertIsNotNone(atom)
        self.assertEqual(self.epi.evidence_of(self.claim), [self.scene])
        with self.assertRaises(TypeError):
            self.epi.relate(
                self.epi.EvidenceFor, self.claim, self.ground, via="learned"
            )


if __name__ == "__main__":
    unittest.main()
