"""Permanent tests for the possession predicate module."""

import unittest

from atomforge import AtomSpaceAPI
from atomforge.infrastructure import UnknownAtomError
from atomforge.stdagent.obligation import install as install_obligation
from atomforge.stdagent.possession import install


class PossessionTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.possession = install(self.api)
        self.kind = self.api.kind("Person")
        self.thing = self.api.kind("Thing")
        self.landlord = self.api.create_node("Landlord", kind=self.kind)
        self.tenant = self.api.create_node("Tenant", kind=self.kind)
        self.apartment = self.api.create_node("Apartment", kind=self.thing)

    def test_vocabulary_is_exactly_own_and_holds(self):
        self.assertEqual(set(self.possession.predicates), {"Own", "Holds"})

    def test_install_is_idempotent(self):
        self.assertIs(install(self.api), self.possession)

    def test_own_without_holding(self):
        # The landlord owns the rented-out house without having it.
        self.possession.own(self.landlord, self.apartment)
        self.assertTrue(
            self.possession.has(
                self.possession.Own, self.landlord, self.apartment
            )
        )
        self.assertFalse(
            self.possession.has(
                self.possession.Holds, self.landlord, self.apartment
            )
        )

    def test_hold_without_owning(self):
        # The tenant has the apartment without owning it.
        self.possession.hold(self.tenant, self.apartment)
        self.assertTrue(
            self.possession.has(
                self.possession.Holds, self.tenant, self.apartment
            )
        )
        self.assertFalse(
            self.possession.has(
                self.possession.Own, self.tenant, self.apartment
            )
        )

    def test_no_inference_crosses_the_axes(self):
        self.possession.own(self.landlord, self.apartment)
        self.possession.hold(self.tenant, self.apartment)
        self.assertEqual(self.possession.owners_of(self.apartment), [self.landlord])
        self.assertEqual(self.possession.holders_of(self.apartment), [self.tenant])
        self.assertEqual(self.possession.owned_by(self.landlord), [self.apartment])
        self.assertEqual(self.possession.held_by(self.tenant), [self.apartment])
        self.assertEqual(self.possession.held_by(self.landlord), [])
        self.assertEqual(self.possession.owned_by(self.tenant), [])

    def test_lease_is_custody_plus_agreement(self):
        # Composition, not machinery: Holds from this module, AgreesTo
        # from obligation, over one shared lease-terms atom.
        obligation = install_obligation(self.api)
        terms = self.api.create_node("lease terms", kind=self.thing)
        self.possession.hold(self.tenant, self.apartment)
        self.possession.own(self.landlord, self.apartment)
        agreed = obligation.relate(
            obligation.AgreesTo, self.tenant, terms, proposal=terms
        )
        self.assertTrue(
            obligation.has(obligation.AgreesTo, self.tenant, terms)
        )
        self.assertIsNotNone(agreed)

    def test_borrowing_is_custody_plus_a_promise(self):
        obligation = install_obligation(self.api)
        book = self.api.create_node("Book", kind=self.thing)
        returning = self.api.create_node("return the book", kind=self.thing)
        self.possession.own(self.landlord, book)
        self.possession.hold(self.tenant, book)
        obligation.relate(
            obligation.Promises, self.tenant, returning,
            promisee=self.landlord,
        )
        self.assertTrue(
            obligation.has(obligation.Promises, self.tenant, returning)
        )
        # The promise did not move title, and custody did not either.
        self.assertEqual(self.possession.owners_of(book), [self.landlord])
        self.assertEqual(self.possession.holders_of(book), [self.tenant])

    def test_own_rejects_unknown_item(self):
        with self.assertRaises(UnknownAtomError):
            self.possession.own(self.landlord, 999999)

    def test_hold_rejects_deleted_holder(self):
        ghost = self.api.create_node("Ghost", kind=self.kind)
        self.api.delete(ghost)
        with self.assertRaises(UnknownAtomError):
            self.possession.hold(ghost, self.apartment)

    def test_relate_rejects_foreign_predicate(self):
        other = self.api.predicate("Other", arity=2)
        with self.assertRaises(TypeError):
            self.possession.relate(other, self.landlord, self.apartment)

    def test_same_assertion_dedups(self):
        first = self.possession.own(self.landlord, self.apartment)
        second = self.possession.own(self.landlord, self.apartment)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
