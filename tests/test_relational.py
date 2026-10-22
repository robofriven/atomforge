import unittest

from atomforge import AtomSpaceAPI
from atomforge.stdagent.relational import install
from atomforge.rules.generic import Inverse, RuleSet, Symmetric, Transitive


class GenericRuleTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.node_kind = self.api.kind("TestNode")
        self.a = self.api.create_node("a", kind=self.node_kind)
        self.b = self.api.create_node("b", kind=self.node_kind)
        self.c = self.api.create_node("c", kind=self.node_kind)
        self.rules = RuleSet(self.api)

    def test_symmetric_rule(self):
        related = self.api.predicate("Related", arity=2)
        self.rules.register(related, Symmetric())
        self.rules.create_predicate(related, self.a, self.b)
        self.assertTrue(self.rules.has_predicate(related, self.b, self.a))
        self.assertFalse(self.api.has_predicate(related, self.b, self.a))
        self.assertEqual(len(self.api.predicates_of(related)), 1)

    def test_transitive_rule(self):
        ancestor = self.api.predicate("Ancestor", arity=2)
        self.rules.register(ancestor, Transitive())
        self.rules.create_predicate(ancestor, self.a, self.b)
        self.rules.create_predicate(ancestor, self.b, self.c)
        self.assertTrue(self.rules.has_predicate(ancestor, self.a, self.c))
        self.assertFalse(self.api.has_predicate(ancestor, self.a, self.c))
        self.assertEqual(len(self.api.predicates_of(ancestor)), 2)

    def test_inverse_canonicalization_rule(self):
        canonical = self.api.predicate("Canonical", arity=2)
        inverse = self.api.predicate("Inverse", arity=2)
        self.rules.register(inverse, Inverse(canonical))
        link_id = self.rules.create_predicate(inverse, self.a, self.b)
        link = self.api.get(link_id)
        self.assertEqual((link.predicate, link.args), (canonical, (self.b, self.a)))
        self.assertTrue(self.rules.has_predicate(inverse, self.a, self.b))


class RelationalPredicateTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.rel = install(self.api)
        self.node_kind = self.api.kind("TestNode")
        self.a = self.api.create_node("a", kind=self.node_kind)
        self.b = self.api.create_node("b", kind=self.node_kind)
        self.c = self.api.create_node("c", kind=self.node_kind)

    def test_vocabulary_contains_only_relational_predicates(self):
        self.assertEqual(set(self.rel.predicates), {
            "At", "In", "On", "Near", "Above", "Below", "Ahead",
            "Behind", "Touch", "Attach", "Hold", "Wear", "Own",
            "PartOf", "IsA", "North", "South", "East", "West",
        })
        for removed in (
            "Action", "PickUp", "Drop", "Throw", "Give", "Transition",
            "TransitionAction", "transition",
        ):
            self.assertFalse(hasattr(self.rel, removed))

    def test_near_and_touch_are_symmetric_but_not_transitive(self):
        for predicate in (self.rel.Near, self.rel.Touch):
            self.rel.relate(predicate, self.a, self.b)
            self.rel.relate(predicate, self.b, self.c)
            self.assertTrue(self.rel.has(predicate, self.b, self.a))
            self.assertFalse(self.rel.has(predicate, self.a, self.c))
            self.assertEqual(len(self.api.predicates_of(predicate)), 2)

    def test_cardinal_directions_normalize_and_are_transitive(self):
        south = self.rel.relate(self.rel.South, self.a, self.b)
        west = self.rel.relate(self.rel.West, self.a, self.b)
        self.assertEqual(
            (self.api.get(south).predicate, self.api.get(south).args),
            (self.rel.North, (self.b, self.a)),
        )
        self.assertEqual(
            (self.api.get(west).predicate, self.api.get(west).args),
            (self.rel.East, (self.b, self.a)),
        )
        self.rel.relate(self.rel.North, self.a, self.b)
        self.rel.relate(self.rel.North, self.b, self.c)
        self.assertTrue(self.rel.has(self.rel.North, self.a, self.c))
        self.assertFalse(self.api.has_predicate(self.rel.North, self.a, self.c))

    def test_ahead_and_behind_have_no_simple_inverse_rule(self):
        self.rel.relate(self.rel.Behind, self.a, self.b)
        self.assertFalse(self.rel.has(self.rel.Ahead, self.b, self.a))

    def test_above_below_inverse_and_transitive(self):
        self.rel.relate(self.rel.Below, self.b, self.a)
        self.rel.relate(self.rel.Above, self.b, self.c)
        self.assertTrue(self.rel.has(self.rel.Above, self.a, self.b))
        self.assertTrue(self.rel.has(self.rel.Above, self.a, self.c))

    def test_isa_is_transitive_directional_and_not_materialized(self):
        catholic = self.api.create_node("Catholic", kind=self.node_kind)
        christian = self.api.create_node("Christian", kind=self.node_kind)
        religion = self.api.create_node("Religion", kind=self.node_kind)
        self.rel.relate(self.rel.IsA, catholic, christian)
        self.rel.relate(self.rel.IsA, christian, religion)
        # Closure is evaluated at query time...
        self.assertTrue(self.rel.has(self.rel.IsA, catholic, religion))
        # ...never written back as an atom.
        self.assertFalse(self.api.has_predicate(self.rel.IsA, catholic, religion))
        self.assertEqual(len(self.api.predicates_of(self.rel.IsA)), 2)
        # Directional: a Christian is not necessarily a Catholic.
        self.assertFalse(self.rel.has(self.rel.IsA, christian, catholic))
        self.assertFalse(self.rel.has(self.rel.IsA, religion, catholic))

    def test_isa_refuses_self_loops_and_cycles(self):
        with self.assertRaises(TypeError):
            self.rel.relate(self.rel.IsA, self.a, self.a)
        self.rel.relate(self.rel.IsA, self.a, self.b)
        self.rel.relate(self.rel.IsA, self.b, self.c)
        with self.assertRaises(TypeError):
            self.rel.relate(self.rel.IsA, self.c, self.a)
        with self.assertRaises(TypeError):
            self.rel.relate(self.rel.IsA, self.b, self.a)
        # Refusals wrote nothing.
        self.assertEqual(len(self.api.predicates_of(self.rel.IsA)), 2)

    def test_is_a_membership_includes_identity(self):
        d = self.api.create_node("d", kind=self.node_kind)
        self.rel.relate(self.rel.IsA, self.a, self.b)
        self.rel.relate(self.rel.IsA, self.b, self.c)
        self.assertTrue(self.rel.is_a(self.a, self.a))
        self.assertTrue(self.rel.is_a(self.a, self.c))
        self.assertFalse(self.rel.is_a(self.c, self.a))
        self.assertFalse(self.rel.is_a(self.a, d))

    def test_isa_over_kind_atoms(self):
        act_kind = self.api.kind("Act")
        sex_act_kind = self.api.kind("SexAct")
        self.rel.relate(self.rel.IsA, sex_act_kind, act_kind)
        self.assertTrue(self.rel.is_a(sex_act_kind, act_kind))
        self.assertFalse(self.rel.is_a(act_kind, sex_act_kind))
if __name__ == "__main__":
    unittest.main()
