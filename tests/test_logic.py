"""Permanent tests for the logic predicate module."""

import unittest

from atomforge import AtomSpaceAPI
from atomforge.stdagent.logic import install


class LogicTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.logic = install(self.api)
        self.kind = self.api.kind("Thing")
        self.a = self.api.create_node("a", kind=self.kind)
        self.b = self.api.create_node("b", kind=self.kind)
        self.c = self.api.create_node("c", kind=self.kind)
        predicate = self.api.predicate("Claim", arity=2)
        self.s1 = self.api.create_predicate(predicate, self.a, self.b)
        self.s2 = self.api.create_predicate(predicate, self.b, self.c)
        self.s3 = self.api.create_predicate(predicate, self.a, self.c)

    def test_vocabulary(self):
        self.assertEqual(
            set(self.logic.predicates),
            {"Contradicts", "Implies", "Supports"},
        )

    def test_install_is_idempotent(self):
        self.assertIs(install(self.api), self.logic)

    def test_contradicts_is_symmetric_at_query_time_only(self):
        self.logic.relate(self.logic.Contradicts, self.s1, self.s2)
        self.assertTrue(
            self.logic.has(self.logic.Contradicts, self.s2, self.s1)
        )
        self.assertFalse(
            self.api.has_predicate(self.logic.Contradicts, self.s2, self.s1)
        )

    def test_implies_is_transitive_at_query_time_only(self):
        self.logic.relate(self.logic.Implies, self.s1, self.s2)
        self.logic.relate(self.logic.Implies, self.s2, self.s3)
        self.assertTrue(self.logic.has(self.logic.Implies, self.s1, self.s3))
        self.assertFalse(
            self.api.has_predicate(self.logic.Implies, self.s1, self.s3)
        )

    def test_supports_is_directional(self):
        self.logic.relate(self.logic.Supports, self.s1, self.s2)
        self.assertTrue(self.logic.has(self.logic.Supports, self.s1, self.s2))
        self.assertFalse(self.logic.has(self.logic.Supports, self.s2, self.s1))


if __name__ == "__main__":
    unittest.main()
