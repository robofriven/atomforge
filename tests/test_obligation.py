"""Permanent tests for the obligation predicate module."""

import unittest

from atomforge import AtomSpaceAPI
from atomforge.infrastructure import InvalidAtomOperationError, UnknownAtomError
from atomforge.stdagent.obligation import install


class ObligationTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.obl = install(self.api)
        self.kind = self.api.kind("Thing")
        self.elena = self.api.create_node("Elena", kind=self.kind)
        self.clients = self.api.create_node("Clients", kind=self.kind)
        self.deposits = self.api.create_node("Deposits", kind=self.kind)
        self.plan = self.api.create_node("Plan", kind=self.kind)

    def ligatures_from(self, atom_id):
        from atomforge.atoms import Ligature
        return [
            atom for atom in (
                self.api.get(lig_id)
                for lig_id in self.api.in_ligatures(atom_id)
            )
            if isinstance(atom, Ligature)
        ]

    def test_vocabulary_is_exactly_the_twelve(self):
        self.assertEqual(
            set(self.obl.predicates),
            {"Desires", "Wants", "Needs", "HasTo", "Obligated", "Promises",
             "AgreesTo", "Acquiesces", "Should", "Shall", "Must", "Will"},
        )

    def test_install_is_idempotent(self):
        self.assertIs(install(self.api), self.obl)

    def test_wants_needs_no_requirements(self):
        atom = self.obl.relate(self.obl.Wants, self.elena, self.plan)
        self.assertTrue(self.obl.has(self.obl.Wants, self.elena, self.plan))
        self.assertEqual(self.ligatures_from(atom), [])

    def test_obligated_without_reason_is_refused(self):
        with self.assertRaises(TypeError):
            self.obl.relate(self.obl.Obligated, self.elena, self.clients)
        self.assertFalse(
            self.obl.has(self.obl.Obligated, self.elena, self.clients)
        )

    def test_obligated_with_reason_records_reason_ligature(self):
        atom = self.obl.relate(
            self.obl.Obligated, self.elena, self.clients,
            reason=self.deposits,
        )
        self.assertTrue(
            self.obl.has(self.obl.Obligated, self.elena, self.clients)
        )
        ligatures = self.ligatures_from(atom)
        self.assertEqual(len(ligatures), 1)
        self.assertEqual(ligatures[0].name, "Reason")
        self.assertEqual(ligatures[0].args, (atom, self.deposits))

    def test_shall_requires_consequence(self):
        with self.assertRaises(TypeError):
            self.obl.relate(self.obl.Shall, self.elena, self.plan)
        atom = self.obl.relate(
            self.obl.Shall, self.elena, self.plan,
            consequence=self.deposits,
        )
        names = [lig.name for lig in self.ligatures_from(atom)]
        self.assertEqual(names, ["Consequence"])

    def test_unexpected_requirement_is_refused(self):
        with self.assertRaises(TypeError):
            self.obl.relate(
                self.obl.Wants, self.elena, self.plan, reason=self.deposits
            )

    def test_unknown_requirement_atom_is_refused_with_its_name(self):
        with self.assertRaises(UnknownAtomError) as caught:
            self.obl.relate(
                self.obl.Obligated, self.elena, self.clients, reason=99999
            )
        self.assertIn("names unknown atom", str(caught.exception))
        self.assertFalse(
            self.obl.has(self.obl.Obligated, self.elena, self.clients)
        )

    def test_current_assertion_as_reason_fails_atomically(self):
        # Regression: this used to raise *after* the Obligated atom was
        # created, leaving an obligation with no reason behind.
        base = self.api.create_predicate(
            self.api.predicate("Q", arity=2), self.elena, self.plan
        )
        current = self.api.make_current(base)
        with self.assertRaises(InvalidAtomOperationError):
            self.obl.relate(
                self.obl.Obligated, self.elena, self.clients, reason=current
            )
        self.assertFalse(
            self.obl.has(self.obl.Obligated, self.elena, self.clients)
        )

    def test_foreign_predicate_is_refused(self):
        banana = self.api.predicate("Banana", arity=2)
        with self.assertRaises(TypeError):
            self.obl.relate(banana, self.elena, self.plan)


if __name__ == "__main__":
    unittest.main()
