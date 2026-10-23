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

    def test_vocabulary_is_exact(self):
        self.assertEqual(set(self.acts.predicates), {
            "Does", "Restrains", "EjaculatesOn", "EjaculatesIn",
            "SquirtsOn", "SquirtsIn", "Orgasms",
        })

    def test_install_is_idempotent(self):
        self.assertIs(install(self.api), self.acts)

    def test_act_node_dedups_same_text(self):
        first = self.acts.act_node("hugging")
        second = self.acts.act_node("hugging")
        self.assertEqual(first, second)
        self.assertTrue(self.acts.is_act(first))
        atom = self.api.get(first)
        self.assertEqual(atom.kind, self.acts.act_kind)

    def test_act_node_rejects_empty_text(self):
        with self.assertRaises(TypeError):
            self.acts.act_node("")

    def test_act_node_does_not_steal_other_kinds(self):
        feeling_kind = self.api.kind("Feeling")
        feeling = self.api.create_node("hugging", kind=feeling_kind)
        act = self.acts.act_node("hugging")
        self.assertNotEqual(act, feeling)

    def test_do_with_text_mints_and_attaches(self):
        atom_id = self.acts.do(self.elena, "hugging")
        act = self.acts.act_node("hugging")
        self.assertTrue(self.acts.has(self.acts.Does, self.elena, act))
        self.assertEqual(self.acts.acts_of(self.elena), [act])
        self.assertEqual(self.acts.occurrences(act), [atom_id])

    def test_one_canonical_act_many_actors(self):
        act = self.acts.act_node("hugging")
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


class RestraintAndResponseTests(unittest.TestCase):
    """Restrains (a state, provisional home) and the sex response
    predicates: closed class, suffixed pairs, unary Orgasms."""

    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.acts = install(self.api)
        self.kind = self.api.kind("Person")
        self.robert = self.api.create_node("Robert", kind=self.kind)
        self.elena = self.api.create_node("Elena", kind=self.kind)
        part_kind = self.api.kind("BodyPart")
        self.chest = self.api.create_node("chest", kind=part_kind)

    def test_restrain_asserts_the_state(self):
        self.acts.restrain(self.elena, self.robert)
        self.assertTrue(self.acts.has(
            self.acts.Restrains, self.elena, self.robert))
        self.assertFalse(self.acts.has(
            self.acts.Restrains, self.robert, self.elena))

    def test_restrain_via_relate(self):
        self.acts.relate(self.acts.Restrains, self.elena, self.robert)
        self.assertTrue(self.acts.has(
            self.acts.Restrains, self.elena, self.robert))

    def test_restrain_rejects_unknown_atoms(self):
        with self.assertRaises(UnknownAtomError):
            self.acts.restrain(999999, self.robert)
        with self.assertRaises(UnknownAtomError):
            self.acts.restrain(self.elena, 999999)

    def test_ejaculates_pairs(self):
        self.acts.ejaculates_on(self.robert, self.chest)
        self.acts.ejaculates_in(self.robert, self.elena)
        self.assertTrue(self.acts.has(
            self.acts.EjaculatesOn, self.robert, self.chest))
        self.assertTrue(self.acts.has(
            self.acts.EjaculatesIn, self.robert, self.elena))
        # On and In are different predicates, never interchangeable.
        self.assertFalse(self.acts.has(
            self.acts.EjaculatesIn, self.robert, self.chest))
        self.assertFalse(self.acts.has(
            self.acts.EjaculatesOn, self.robert, self.elena))

    def test_squirts_pairs(self):
        cup = self.api.create_node(
            "skull cup", kind=self.api.kind("Object"))
        self.acts.squirts_on(self.elena, cup)
        self.acts.squirts_in(self.elena, self.robert)
        self.assertTrue(self.acts.has(
            self.acts.SquirtsOn, self.elena, cup))
        self.assertTrue(self.acts.has(
            self.acts.SquirtsIn, self.elena, self.robert))

    def test_responses_reject_unknown_target(self):
        with self.assertRaises(UnknownAtomError):
            self.acts.ejaculates_on(self.robert, 999999)
        with self.assertRaises(UnknownAtomError):
            self.acts.squirts_on(999999, self.chest)

    def test_orgasms_is_unary(self):
        self.acts.orgasms(self.elena)
        self.assertTrue(self.acts.has_orgasm(self.elena))
        self.assertFalse(self.acts.has_orgasm(self.robert))

    def test_orgasms_refused_through_binary_paths(self):
        with self.assertRaises(TypeError):
            self.acts.relate(
                self.acts.Orgasms, self.elena, self.robert)
        with self.assertRaises(TypeError):
            self.acts.has(self.acts.Orgasms, self.elena, self.robert)

    def test_foreign_predicate_still_refused(self):
        other = self.api.predicate("Other", arity=2)
        with self.assertRaises(TypeError):
            self.acts.relate(other, self.robert, self.elena)
        with self.assertRaises(TypeError):
            self.acts.has(other, self.robert, self.elena)


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


class VocabularyFactoryTests(unittest.TestCase):
    """The v3 gated factory: SexAct is a real kind, term minting
    follows the approved vocabulary, and anything else is queued as
    a proposal instead of silently minted."""

    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.acts = install(self.api)
        self.rel = install_relational(self.api)
        self.kind = self.api.kind("Person")
        self.elena = self.api.create_node("Elena", kind=self.kind)
        self.robert = self.api.create_node("Robert", kind=self.kind)

    def test_packaged_vocabulary_is_loaded(self):
        terms = self.acts.vocabulary_terms()
        self.assertIn("fellatio", terms)
        self.assertIn("hugging", terms)
        # Superseded by the 2026-10-23 response rulings: a response
        # is not a term.
        self.assertNotIn("simultaneous orgasm", terms)
        self.assertNotIn("plastic wrap cocoon", terms)

    def test_sex_act_term_mints_under_sex_act_kind(self):
        fellatio = self.acts.act_node("fellatio")
        atom = self.api.get(fellatio)
        self.assertEqual(atom.kind, self.acts.sex_act_kind)
        self.assertTrue(self.acts.is_act(fellatio))

    def test_kind_level_isa_asserted_on_first_sex_mint(self):
        self.assertFalse(self.rel.has(
            self.rel.IsA, self.acts.sex_act_kind, self.acts.act_kind))
        self.acts.act_node("fellatio")
        self.assertTrue(self.rel.has(
            self.rel.IsA, self.acts.sex_act_kind, self.acts.act_kind))

    def test_term_taxonomy_isa_among_term_nodes(self):
        fellatio = self.acts.act_node("fellatio")
        oral = self.acts.act_node("oral")
        self.assertTrue(self.rel.is_a(fellatio, oral))
        self.assertTrue(self.rel.is_a(fellatio, self.acts.sex_act_kind))
        self.assertTrue(self.rel.is_a(oral, self.acts.sex_act_kind))
        # A hub mints on demand, kinded SexAct, parented on the kind.
        self.assertEqual(self.api.get(oral).kind, self.acts.sex_act_kind)

    def test_multi_parent_term(self):
        rimming = self.acts.act_node("rimming")
        self.assertTrue(self.rel.is_a(rimming, self.acts.act_node("oral")))
        self.assertTrue(self.rel.is_a(rimming, self.acts.act_node("anal")))

    def test_general_act_term_parents(self):
        kissing = self.acts.act_node("kissing")
        affection = self.acts.act_node("affection")
        self.assertEqual(self.api.get(kissing).kind, self.acts.act_kind)
        self.assertTrue(self.rel.is_a(kissing, affection))
        self.assertTrue(self.rel.is_a(affection, self.acts.act_kind))

    def test_does_covers_sex_act_by_inheritance(self):
        self.acts.do(self.elena, "fellatio")
        act = self.acts.act_node("fellatio")
        self.assertTrue(self.acts.has(self.acts.Does, self.elena, act))

    def test_unapproved_label_is_refused_and_queued(self):
        from atomforge.stdagent.acts import UnapprovedTermError
        with self.assertRaises(UnapprovedTermError):
            self.acts.act_node("rimming (on Elena)")
        with self.assertRaises(TypeError):  # it is a TypeError refusal
            self.acts.act_node("underwater basket weaving")
        self.assertEqual(
            self.acts.proposals(),
            ["rimming (on Elena)", "underwater basket weaving"])
        # Nothing was minted for the refused labels.
        self.assertEqual(self.api.find_by_label("underwater basket weaving"),
                         [])

    def test_do_with_unapproved_text_refuses_and_queues(self):
        with self.assertRaises(TypeError):
            self.acts.do(self.elena, "fellatio — at dawn, twice")
        self.assertIn("fellatio — at dawn, twice", self.acts.proposals())
        self.assertEqual(self.acts.acts_of(self.elena), [])

    def test_standing_node_resolves_without_vocabulary(self):
        # Consent-exempt pattern: an act node already in the graph
        # resolves by label even though its label is not a term.
        exempt = self.api.create_node(
            "sleep-use", kind=self.acts.act_kind)
        self.assertEqual(self.acts.act_node("sleep-use"), exempt)
        self.assertEqual(self.acts.proposals(), [])

    def test_approve_term_admits_queued_label(self):
        with self.assertRaises(TypeError):
            self.acts.act_node("tickling")
        self.acts.approve_term("tickling")
        self.assertEqual(self.acts.proposals(), [])
        node = self.acts.act_node("tickling")
        self.assertTrue(self.acts.is_act(node))
        self.acts.do(self.elena, node)

    def test_fixture_vocabulary_install(self):
        api = AtomSpaceAPI.create()
        acts = install(api, vocabulary=("skipping",))
        node = acts.act_node("skipping")
        self.assertTrue(acts.is_act(node))
        with self.assertRaises(TypeError):
            acts.act_node("fellatio")

    def test_conflicting_second_install_refused(self):
        with self.assertRaises(TypeError):
            install(self.api, vocabulary=("skipping",))
        # A vocabulary-free re-install returns the same installation.
        self.assertIs(install(self.api), self.acts)


if __name__ == "__main__":
    unittest.main()
