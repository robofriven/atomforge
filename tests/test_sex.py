"""Permanent tests for the sex domain module (response predicates
and the SexAct kind).

The response predicates moved here from stdagent/acts (library C3
overturned, 2026-10-24): stdagent does not need them.  Predicate
names, arities, and roles are identical to the old home — only the
module moved — so a brain written against the old install loads
against this one unchanged.
"""

import unittest

from atomforge import AtomSpaceAPI
from atomforge.domain.sex import install
from atomforge.infrastructure import UnknownAtomError
from atomforge.stdagent.acts import install as install_acts
from atomforge.stdagent.relational import install as install_relational


class SexResponseTests(unittest.TestCase):
    """The sex response predicates: closed class, suffixed pairs,
    unary Orgasms."""

    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.sex = install(self.api)
        self.kind = self.api.kind("Person")
        self.robert = self.api.create_node("Robert", kind=self.kind)
        self.elena = self.api.create_node("Elena", kind=self.kind)
        part_kind = self.api.kind("BodyPart")
        self.chest = self.api.create_node("chest", kind=part_kind)

    def test_vocabulary_is_exactly_the_five(self):
        self.assertEqual(
            set(self.sex.predicates),
            {
                "EjaculatesOn", "EjaculatesIn",
                "SquirtsOn", "SquirtsIn", "Orgasms",
            },
        )

    def test_install_is_idempotent(self):
        self.assertIs(install(self.api), self.sex)

    def test_ejaculates_pairs(self):
        self.sex.ejaculates_on(self.robert, self.chest)
        self.sex.ejaculates_in(self.robert, self.elena)
        self.assertTrue(self.sex.has(
            self.sex.EjaculatesOn, self.robert, self.chest))
        self.assertTrue(self.sex.has(
            self.sex.EjaculatesIn, self.robert, self.elena))
        # On and In are different predicates, never interchangeable.
        self.assertFalse(self.sex.has(
            self.sex.EjaculatesIn, self.robert, self.chest))
        self.assertFalse(self.sex.has(
            self.sex.EjaculatesOn, self.robert, self.elena))

    def test_squirts_pairs(self):
        cup = self.api.create_node(
            "skull cup", kind=self.api.kind("Object"))
        self.sex.squirts_on(self.elena, cup)
        self.sex.squirts_in(self.elena, self.robert)
        self.assertTrue(self.sex.has(
            self.sex.SquirtsOn, self.elena, cup))
        self.assertTrue(self.sex.has(
            self.sex.SquirtsIn, self.elena, self.robert))

    def test_responses_reject_unknown_target(self):
        with self.assertRaises(UnknownAtomError):
            self.sex.ejaculates_on(self.robert, 999999)
        with self.assertRaises(UnknownAtomError):
            self.sex.squirts_on(999999, self.chest)

    def test_orgasms_is_unary(self):
        self.sex.orgasms(self.elena)
        self.assertTrue(self.sex.has_orgasm(self.elena))
        self.assertFalse(self.sex.has_orgasm(self.robert))

    def test_orgasms_refused_through_binary_paths(self):
        with self.assertRaises(TypeError):
            self.sex.relate(
                self.sex.Orgasms, self.elena, self.robert)
        with self.assertRaises(TypeError):
            self.sex.has(self.sex.Orgasms, self.elena, self.robert)

    def test_foreign_predicate_still_refused(self):
        other = self.api.predicate("Other", arity=2)
        with self.assertRaises(TypeError):
            self.sex.relate(other, self.elena, self.robert)
        with self.assertRaises(TypeError):
            self.sex.has(other, self.elena, self.robert)


class SexMoveTests(unittest.TestCase):
    """The move itself: stdagent no longer exposes the responses,
    and the SexAct kind's home is this module."""

    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.acts = install_acts(self.api)
        self.sex = install(self.api)
        self.rel = install_relational(self.api)

    def test_acts_no_longer_exposes_response_predicates(self):
        for name in (
            "EjaculatesOn", "EjaculatesIn",
            "SquirtsOn", "SquirtsIn", "Orgasms",
        ):
            self.assertNotIn(name, self.acts.predicates)
            self.assertFalse(hasattr(self.acts, name))
        # A sex predicate through the acts paths is foreign.
        with self.assertRaises(TypeError):
            self.acts.relate(
                self.sex.EjaculatesOn, 1, 2)
        with self.assertRaises(TypeError):
            self.acts.has(self.sex.EjaculatesOn, 1, 2)

    def test_sex_act_kind_home(self):
        self.assertEqual(self.sex.sex_act_kind, self.api.kind("SexAct"))
        self.assertEqual(self.sex.act_kind, self.api.kind("Act"))
        self.assertFalse(self.rel.has(
            self.rel.IsA, self.sex.sex_act_kind, self.sex.act_kind))
        self.sex.ensure_sex_act_kind()
        self.assertTrue(self.rel.has(
            self.rel.IsA, self.sex.sex_act_kind, self.sex.act_kind))
        # Idempotent: a second call writes nothing new.
        self.sex.ensure_sex_act_kind()
        self.assertTrue(self.rel.has(
            self.rel.IsA, self.sex.sex_act_kind, self.sex.act_kind))

    def test_factory_and_sex_coexist_on_one_kind(self):
        # The acts factory still mints SexAct-kind terms from the
        # whole vocabulary by kind name, and they validate as acts
        # once the kind edge is asserted.
        fellatio = self.acts.act_node("fellatio")
        self.assertEqual(self.api.get(fellatio).kind,
                         self.sex.sex_act_kind)
        self.assertTrue(self.acts.is_act(fellatio))
        self.assertTrue(self.rel.is_a(fellatio, self.sex.sex_act_kind))


if __name__ == "__main__":
    unittest.main()
