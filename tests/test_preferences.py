"""Permanent tests for the preferences predicate module.

Covers the adopted design: scale-based inference at query time (never
materialized), explicit Prefers overriding inferred ranking, automatic
Contradicts on conflicting assertions, and supersession via Transition.
"""

import unittest

from atomforge import AtomSpaceAPI
from atomforge.infrastructure import UnknownAtomError
from atomforge.stdagent.logic import install as install_logic
from atomforge.stdagent.preferences import install


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.pref = install(self.api)
        self.logic = install_logic(self.api)
        self.kind = self.api.kind("Thing")
        self.elena = self.api.create_node("Elena", kind=self.kind)
        self.shrimp = self.api.create_node("Shrimp", kind=self.kind)
        self.steak = self.api.create_node("Steak", kind=self.kind)
        self.tofu = self.api.create_node("Tofu", kind=self.kind)
        self.liver = self.api.create_node("Liver", kind=self.kind)

    def contradicts_between(self, left, right):
        return bool(
            self.api.find_predicates(self.logic.Contradicts, left, right)
        )

    # -- vocabulary / query-time implication -------------------------------

    def test_vocabulary(self):
        self.assertEqual(
            set(self.pref.predicates),
            {"Loves", "Likes", "Indifferent", "Dislikes", "Hates", "Prefers"},
        )

    def test_loves_answers_likes_without_materializing(self):
        self.pref.relate(self.pref.Loves, self.elena, self.shrimp)
        self.assertTrue(self.pref.has(self.pref.Likes, self.elena, self.shrimp))
        self.assertFalse(
            self.api.has_predicate(self.pref.Likes, self.elena, self.shrimp)
        )

    def test_hates_answers_dislikes(self):
        self.pref.relate(self.pref.Hates, self.elena, self.liver)
        self.assertTrue(
            self.pref.has(self.pref.Dislikes, self.elena, self.liver)
        )

    def test_no_cross_side_implication(self):
        self.pref.relate(self.pref.Likes, self.elena, self.shrimp)
        self.assertFalse(
            self.pref.has(self.pref.Indifferent, self.elena, self.shrimp)
        )

    # -- ranking ------------------------------------------------------------

    def test_rank_uses_full_scale_including_indifferent(self):
        self.pref.relate(self.pref.Loves, self.elena, self.shrimp)
        self.pref.relate(self.pref.Indifferent, self.elena, self.tofu)
        self.pref.relate(self.pref.Hates, self.elena, self.liver)
        self.assertEqual(self.pref.rank(self.elena, self.shrimp), 2)
        self.assertEqual(self.pref.rank(self.elena, self.tofu), 0)
        self.assertEqual(self.pref.rank(self.elena, self.liver), -2)
        self.assertIsNone(self.pref.rank(self.elena, self.steak))

    def test_opposing_extremes_cancel_rank_to_none(self):
        self.pref.relate(self.pref.Loves, self.elena, self.shrimp)
        self.pref.relate(self.pref.Hates, self.elena, self.shrimp)
        self.assertIsNone(self.pref.rank(self.elena, self.shrimp))

    def test_inferred_preferred_follows_scale(self):
        self.pref.relate(self.pref.Loves, self.elena, self.shrimp)
        self.pref.relate(self.pref.Likes, self.elena, self.steak)
        self.assertEqual(
            self.pref.preferred(self.elena, self.shrimp, self.steak),
            self.shrimp,
        )

    def test_explicit_prefers_overrides_scale(self):
        loves_shrimp = self.pref.relate(self.pref.Loves, self.elena, self.shrimp)
        likes_steak = self.pref.relate(self.pref.Likes, self.elena, self.steak)
        self.pref.relate(self.pref.Prefers, likes_steak, loves_shrimp)
        self.assertEqual(
            self.pref.preferred(self.elena, self.steak, self.shrimp),
            self.steak,
        )

    def test_prefers_is_transitive_for_has(self):
        st1 = self.pref.relate(self.pref.Likes, self.elena, self.shrimp)
        st2 = self.pref.relate(self.pref.Indifferent, self.elena, self.steak)
        st3 = self.pref.relate(self.pref.Dislikes, self.elena, self.tofu)
        self.pref.relate(self.pref.Prefers, st1, st2)
        self.pref.relate(self.pref.Prefers, st2, st3)
        self.assertTrue(self.pref.has(self.pref.Prefers, st1, st3))
        self.assertFalse(self.api.has_predicate(self.pref.Prefers, st1, st3))

    # -- automatic contradiction recording ---------------------------------

    def test_opposing_stance_auto_contradicts_each_existing_side(self):
        likes = self.pref.relate(self.pref.Likes, self.elena, self.shrimp)
        loves = self.pref.relate(self.pref.Loves, self.elena, self.shrimp)
        # Same side: no contradiction between Likes and Loves.
        self.assertFalse(self.contradicts_between(likes, loves))
        hates = self.pref.relate(self.pref.Hates, self.elena, self.shrimp)
        self.assertTrue(self.contradicts_between(hates, likes))
        self.assertTrue(self.contradicts_between(hates, loves))
        # Both originals survive.
        self.assertIsNotNone(self.api.get(likes))
        self.assertIsNotNone(self.api.get(hates))

    def test_indifferent_contradicts_any_stance(self):
        likes = self.pref.relate(self.pref.Likes, self.elena, self.steak)
        indiff = self.pref.relate(self.pref.Indifferent, self.elena, self.steak)
        self.assertTrue(self.contradicts_between(indiff, likes))

    def test_prefers_fighting_scale_auto_records_contradiction(self):
        bob = self.api.create_node("Bob", kind=self.kind)
        cod = self.api.create_node("Cod", kind=self.kind)
        peas = self.api.create_node("Peas", kind=self.kind)
        likes_cod = self.pref.relate(self.pref.Likes, bob, cod)
        dislikes_peas = self.pref.relate(self.pref.Dislikes, bob, peas)
        explicit = self.pref.relate(self.pref.Prefers, dislikes_peas, likes_cod)
        pairs = self.pref.contradictions(bob, peas, cod)
        self.assertIn((explicit, likes_cod), pairs)
        self.assertTrue(self.contradicts_between(explicit, likes_cod))

    def test_opposing_explicit_prefers_contradict_each_other(self):
        st_a = self.pref.relate(self.pref.Likes, self.elena, self.shrimp)
        st_b = self.pref.relate(self.pref.Likes, self.elena, self.steak)
        first = self.pref.relate(self.pref.Prefers, st_a, st_b)
        second = self.pref.relate(self.pref.Prefers, st_b, st_a)
        self.assertTrue(self.contradicts_between(second, first))

    # -- supersession --------------------------------------------------------

    def test_superseding_at_assertion_time_makes_transition_not_contradiction(self):
        likes = self.pref.relate(self.pref.Likes, self.elena, self.shrimp)
        hates = self.pref.relate(
            self.pref.Hates, self.elena, self.shrimp, supersedes=likes
        )
        self.assertFalse(self.contradicts_between(hates, likes))
        from atomforge.atoms import Transition
        transition_atoms = [
            result.atom
            for result in self.api.search(atom_type=Transition)
            if result.atom.args == (likes, hates)
        ]
        self.assertEqual(len(transition_atoms), 1)

    def test_post_hoc_supersede_clears_contradiction(self):
        likes = self.pref.relate(self.pref.Likes, self.elena, self.shrimp)
        hates = self.pref.relate(self.pref.Hates, self.elena, self.shrimp)
        self.assertTrue(self.contradicts_between(hates, likes))
        contradicts_id = self.api.find_predicates(
            self.logic.Contradicts, hates, likes
        )[0].atom.id
        self.pref.supersede(likes, hates)
        self.assertIsNone(self.api.get(contradicts_id))

    def test_superseding_unknown_atom_fails_before_writing(self):
        likes = self.pref.relate(self.pref.Likes, self.elena, self.shrimp)
        with self.assertRaises(UnknownAtomError):
            self.pref.relate(
                self.pref.Hates, self.elena, self.shrimp, supersedes=99999
            )
        self.assertFalse(
            self.api.has_predicate(self.pref.Hates, self.elena, self.shrimp)
        )

    def test_superseding_wrong_target_fails_before_writing(self):
        other = self.pref.relate(self.pref.Likes, self.elena, self.steak)
        with self.assertRaises(TypeError):
            self.pref.relate(
                self.pref.Hates, self.elena, self.shrimp, supersedes=other
            )
        self.assertFalse(
            self.api.has_predicate(self.pref.Hates, self.elena, self.shrimp)
        )


if __name__ == "__main__":
    unittest.main()
