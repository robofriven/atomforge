import ast
import inspect
import json
import tempfile
import unittest
from pathlib import Path

from atomforge import (
    AlreadyDeletedError, AtomSpaceAPI, DuplicateCurrentError,
    GraphInvariantError, InvalidAtomOperationError, InvalidConfidenceError,
    Intersection, KindAtom, Ligature, MalformedPersistenceError, Node,
    Predicate, PredicateAtom,
    SchemaVersionError,
    SearchResult, StructuralSearchResult, UnknownAtomError, UnknownPredicateError,
    Transition,
)
from atomforge.core import AtomSpace
from atomforge.renderer import Renderer


def create_test_node(space, label, **kwargs):
    kind = kwargs.pop("kind", None)
    if kind is None:
        kind = space.kind("TestNode")
    return space.create_node(label, kind=kind, **kwargs)


class CoreTests(unittest.TestCase):
    def test_core_vocabulary_and_single_id_space(self):
        api = AtomSpaceAPI.create()
        self.assertEqual(api.current_predicate, 1)
        self.assertEqual(api.delete_predicate, 2)
        self.assertEqual(api.get(1).label, "Current")
        self.assertEqual(api.get(2).label, "Delete")
        kind = api.kind("Thing")
        predicate = api.predicate("Related", arity=5)
        node = create_test_node(api, "node", kind=kind)
        ligature = api.create_ligature("Local", node)
        link = api.create_predicate(
            predicate, node, kind, predicate, ligature, api.current_predicate
        )
        self.assertIsInstance(api.get(kind), KindAtom)
        self.assertIsInstance(api.get(predicate), PredicateAtom)
        self.assertIsInstance(api.get(node), Node)
        self.assertIsInstance(api.get(ligature), Ligature)
        self.assertIsInstance(api.get(link), Predicate)
        with self.assertRaises(UnknownAtomError):
            api.get(0)
        with self.assertRaises(UnknownPredicateError):
            api.create_predicate("Undeclared", node)

    def test_structural_link_contracts(self):
        api = AtomSpaceAPI.create()
        anti = api.predicate("Anti", arity=2, anti_reflexive=True)
        acyclic = api.predicate("Acyclic", arity=2, acyclic=True)
        left, right = create_test_node(api, "left"), create_test_node(api, "right")
        with self.assertRaises(TypeError):
            api.create_link(anti, left)
        with self.assertRaises(ValueError):
            api.create_link(anti, left, left)
        api.create_link(acyclic, left, right)
        with self.assertRaises(ValueError):
            api.create_link(acyclic, right, left)
        with self.assertRaises(UnknownAtomError):
            api.create_link(anti, left, 9999)

    def test_node_kind_and_predicate_definition_are_type_checked(self):
        api = AtomSpaceAPI.create()
        kind = api.kind("Thing")
        definition = api.predicate("Unary", arity=1)
        with self.assertRaises(TypeError):
            api.create_node("untyped")
        with self.assertRaises(UnknownAtomError):
            api.create_node("zero-kind", kind=0)
        deleted_kind = api.kind("DeletedKind")
        api.delete(deleted_kind)
        with self.assertRaises(UnknownAtomError):
            api.create_node("deleted-kind", kind=deleted_kind)
        node = create_test_node(api, "typed", kind=kind)
        application = api.create_predicate(definition, node)
        self.assertEqual(api.get(node).kind, kind)
        self.assertIsInstance(api.get(application), Predicate)
        with self.assertRaises(UnknownAtomError):
            create_test_node(api, "wrong", kind=definition)
        with self.assertRaises(UnknownPredicateError):
            api.create_predicate(kind, node)

    def test_confidence_is_mutable_metadata_on_structurally_immutable_atoms(self):
        api = AtomSpaceAPI.create()
        with self.assertRaises(InvalidConfidenceError):
            create_test_node(api, "zero", confidence=0)
        atom = create_test_node(api, "atom")
        api.set_confidence(atom, 0)
        self.assertEqual(api.confidence(atom), 0)
        api.set_confidence(atom, 1)
        self.assertEqual(api.confidence(atom), 1)
        for value in (-0.1, 1.1, float("nan")):
            with self.assertRaises(InvalidConfidenceError):
                api.set_confidence(atom, value)
        self.assertFalse(hasattr(api, "mutate"))
        self.assertFalse(hasattr(api, "remove_mutable"))

    def test_delete_assertion_hides_atom_but_raw_history_remains(self):
        api = AtomSpaceAPI.create()
        atom = create_test_node(api, "historical")
        delete_assertion = api.delete(atom)
        deletion = api.get(delete_assertion)
        self.assertIsInstance(deletion, Predicate)
        self.assertEqual(deletion.predicate, api.delete_predicate)
        self.assertEqual(deletion.args, (atom,))
        self.assertIsNone(api.get(atom))
        raw = api.get_raw(atom)
        self.assertEqual(raw.atom.label, "historical")
        self.assertTrue(raw.deleted)
        self.assertEqual(raw.confidence, 1)
        self.assertFalse(api.search(label="historical"))
        self.assertEqual(api.search_raw(label="historical")[0].atom_id, atom)
        with self.assertRaises(AlreadyDeletedError):
            api.delete(atom)

    def test_delete_is_core_owned_and_protects_its_own_tombstones(self):
        api = AtomSpaceAPI.create()
        atom = create_test_node(api, "atom")
        with self.assertRaises(InvalidAtomOperationError):
            api.create_link(api.delete_predicate, atom)
        with self.assertRaises(InvalidAtomOperationError):
            api.create_link(api.current_predicate, atom)
        assertion = api.delete(atom)
        self.assertIsNone(api.get(atom))
        with self.assertRaises(InvalidAtomOperationError):
            api.delete(assertion)
        with self.assertRaises(InvalidAtomOperationError):
            api.delete(api.current_predicate)
        with self.assertRaises(InvalidAtomOperationError):
            api.delete(api.delete_predicate)

    def test_core_predicate_names_are_reserved(self):
        api = AtomSpaceAPI.create()
        for name in ("Current", "Delete", "Transition"):
            with self.assertRaises(InvalidAtomOperationError):
                api.predicate(name)
            with self.assertRaises(InvalidAtomOperationError):
                api.predicate(name, arity=2, intern=False)

    def test_transition_is_a_reserved_core_relationship_form(self):
        api = AtomSpaceAPI.create()
        with self.assertRaises(InvalidAtomOperationError):
            api.kind("Transition")
        with self.assertRaises(InvalidAtomOperationError):
            api.predicate("Transition", arity=2)

    def test_transition_representation_and_current_transfer(self):
        api = AtomSpaceAPI.create()
        before = create_test_node(api, "before")
        after = create_test_node(api, "after")
        old_current = api.make_current(before)

        transition = api.transition(
            before, after, label="state changed", confidence=0.6
        )

        transition_atom = api.get(transition)
        self.assertIsInstance(transition_atom, Transition)
        self.assertNotIsInstance(transition_atom, Node)
        self.assertEqual(transition_atom.args, (before, after))
        self.assertEqual(transition_atom.before, before)
        self.assertEqual(transition_atom.after, after)
        self.assertEqual(transition_atom.label, "state changed")
        self.assertEqual(api.confidence(transition), 0.6)
        self.assertEqual(api.transition_args(transition), (before, after))
        self.assertEqual(api.in_transitions(before), {transition})
        self.assertEqual(api.in_transitions(after), {transition})
        self.assertEqual(Renderer(api).render(transition), "Transition(before, after)")
        traversed = {result.matched_id for result in api.traverse(before)}
        self.assertTrue({transition, after}.issubset(traversed))
        with self.assertRaises(UnknownAtomError):
            api.get_raw(old_current)
        self.assertFalse(api.has_link(api.current_predicate, before))
        self.assertTrue(api.has_link(api.current_predicate, after))
        labels = {result.atom.label for result in api.search()}
        self.assertNotIn("TransitionFrom", labels)
        self.assertNotIn("TransitionTo", labels)

    def test_historical_transition_does_not_move_current(self):
        api = AtomSpaceAPI.create()
        active = create_test_node(api, "active")
        before = create_test_node(api, "historical before")
        after = create_test_node(api, "historical after")
        api.make_current(active)

        api.transition(before, after)

        self.assertTrue(api.has_link(api.current_predicate, active))
        self.assertFalse(api.has_link(api.current_predicate, before))
        self.assertFalse(api.has_link(api.current_predicate, after))

    def test_transition_connects_state_atoms_not_current_assertions(self):
        api = AtomSpaceAPI.create()
        in_predicate = api.predicate("In", arity=2)
        elena = create_test_node(api, "Elena")
        tavern = create_test_node(api, "Tavern")
        street = create_test_node(api, "Street")
        old_state = api.create_predicate(in_predicate, elena, tavern)
        new_state = api.create_predicate(in_predicate, elena, street)
        current_assertion = api.make_current(old_state)

        transition = api.transition(old_state, new_state)

        self.assertEqual(api.transition_args(transition), (old_state, new_state))
        self.assertNotIn(current_assertion, api.transition_args(transition))
        self.assertTrue(api.has_link(api.current_predicate, new_state))

    def test_transition_to_already_current_state_avoids_duplicate_current(self):
        api = AtomSpaceAPI.create()
        before = create_test_node(api, "before")
        after = create_test_node(api, "after")
        api.make_current(before)
        existing = api.make_current(after)

        api.transition(before, after)

        self.assertFalse(api.has_link(api.current_predicate, before))
        self.assertEqual(
            api.find_links(api.current_predicate, after)[0].matched_id,
            existing,
        )

    def test_transition_structure_is_deleted_as_one_unit(self):
        api = AtomSpaceAPI.create()
        before = create_test_node(api, "before")
        after = create_test_node(api, "after")
        transition = api.transition(before, after)

        api.delete(before)

        self.assertIsNone(api.get(transition))
        self.assertTrue(api.get_raw(transition).deleted)

    def test_current_removal_is_physical_and_recreatable(self):
        api = AtomSpaceAPI.create()
        first, second = create_test_node(api, "first"), create_test_node(api, "second")
        first_current = api.make_current(first)
        second_current = api.make_current(second)
        self.assertNotEqual(first_current, second_current)
        with self.assertRaises(DuplicateCurrentError):
            api.make_current(first)
        predicate = api.predicate("P", arity=1)
        with self.assertRaises(InvalidAtomOperationError):
            api.create_link(predicate, first_current)
        with self.assertRaises(InvalidAtomOperationError):
            api.create_ligature("Illegal", first_current)
        with self.assertRaises(InvalidAtomOperationError):
            api.make_current(first_current)
        relation = api.create_ligature("Unrelated", first, second)
        self.assertIsNone(api.remove_current(first))
        with self.assertRaises(UnknownAtomError):
            api.get_raw(first_current)
        self.assertIsNotNone(api.get(first))
        with self.assertRaises(InvalidAtomOperationError):
            api.remove_current(first)
        replacement = api.make_current(first)
        self.assertNotEqual(replacement, first_current)
        self.assertIsNotNone(api.get(relation))

    def test_ligature_is_named_topology_without_relation_type_index(self):
        api = AtomSpaceAPI.create()
        predicate = api.predicate("Global", arity=2)
        person = create_test_node(api, "person")
        side = create_test_node(api, "left")
        arm = api.create_ligature("Arm", person, side, confidence=0.7)
        relation = api.get(arm)
        self.assertIsInstance(relation, Ligature)
        self.assertEqual(relation.name, "Arm")
        self.assertEqual(api.connected(arm), (person, side))
        self.assertEqual(api.in_ligatures(person), {arm})
        self.assertEqual(api.links_of(predicate), set())
        self.assertEqual(api.search(predicate=predicate), [])
        core = AtomSpace()
        a, b = create_test_node(core, "a"), create_test_node(core, "b")
        ligature_id = core.create_ligature("Local", a, b)
        self.assertFalse(any(
            ligature_id in ids for ids in core._by_pred.values()
        ))

    def test_relationship_primitives_share_topology_but_not_predicate_index(self):
        api = AtomSpaceAPI.create()
        definition = api.predicate("Related", arity=2)
        left = create_test_node(api, "left")
        middle = create_test_node(api, "middle")
        right = create_test_node(api, "right")
        application = api.create_predicate(definition, left, middle)
        ligature = api.create_ligature("Local", middle, right)
        transition = api.transition(right, left)

        reached = {item.matched_id for item in api.traverse(left)}
        self.assertTrue(
            {application, ligature, transition, left, middle, right}.issubset(reached)
        )
        self.assertEqual(api.predicates_of(definition), {application})
        self.assertNotIn(ligature, api.predicates_of(definition))
        self.assertNotIn(transition, api.predicates_of(definition))
        self.assertEqual(api.search(predicate=definition)[0].atom, api.get(application))

    def test_ligature_validation_and_deletion(self):
        api = AtomSpaceAPI.create()
        atom = create_test_node(api, "atom")
        with self.assertRaises(ValueError):
            api.create_ligature("", atom)
        with self.assertRaises(ValueError):
            api.create_ligature("Empty")
        with self.assertRaises(UnknownAtomError):
            api.create_ligature("Missing", 9999)
        ligature = api.create_ligature("Local", atom)
        api.delete(ligature)
        self.assertIsNone(api.get(ligature))
        self.assertTrue(api.get_raw(ligature).deleted)
        self.assertEqual(api.in_ligatures(atom), set())

    def test_deleting_atom_cascades_all_live_incident_relationships(self):
        api = AtomSpaceAPI.create()
        predicate = api.predicate("Pair", arity=2)
        target = create_test_node(api, "target")
        other = create_test_node(api, "other")
        link = api.create_link(predicate, target, other)
        ligature = api.create_ligature("Local", target, other)
        relation_of_relation = api.create_ligature("Meta", link, ligature)
        api.make_current(target)
        api.delete(target)
        for atom_id in (target, link, ligature, relation_of_relation):
            self.assertIsNone(api.get(atom_id))
            self.assertTrue(api.get_raw(atom_id).deleted)
        self.assertEqual(api.in_links(other), set())
        self.assertEqual(api.in_ligatures(other), set())
        self.assertEqual(api.search(predicate=api.current_predicate), [])

    def test_deleted_link_identity_cannot_be_recreated(self):
        for dedup_predicates in (True, False):
            api = AtomSpaceAPI.create(dedup_predicates=dedup_predicates)
            predicate = api.predicate("Pair", arity=2)
            left, right = create_test_node(api, "left"), create_test_node(api, "right")
            link = api.create_link(predicate, left, right)
            api.delete(link)
            with self.assertRaises(InvalidAtomOperationError):
                api.create_link(predicate, left, right)

    def test_definition_deletion_requires_no_live_users(self):
        api = AtomSpaceAPI.create()
        kind = api.kind("ApplicationKind")
        typed = create_test_node(api, "typed", kind=kind)
        with self.assertRaises(InvalidAtomOperationError):
            api.delete(kind)
        predicate = api.predicate("ApplicationRelation", arity=1)
        node = create_test_node(api, "node")
        link = api.create_link(predicate, node)
        with self.assertRaises(InvalidAtomOperationError):
            api.delete(predicate)
        api.delete(typed)
        with self.assertRaises(InvalidAtomOperationError):
            api.delete(kind)
        api.delete(link)
        api.delete(predicate)
        self.assertIsNone(api.get(predicate))
        self.assertIsNone(api.get(link))
        self.assertTrue(api.get_raw(link).deleted)

    def test_deletion_closure_handles_topological_cycles(self):
        api = AtomSpaceAPI.create()
        left, right = create_test_node(api, "left"), create_test_node(api, "right")
        upper = api.create_ligature("Upper", left, right)
        lower = api.create_ligature("Lower", right, left)
        api.delete(left)
        for atom_id in (left, upper, lower):
            self.assertIsNone(api.get(atom_id))
            self.assertTrue(api.get_raw(atom_id).deleted)
        self.assertIsNotNone(api.get(right))

    def test_interned_immutable_structure_must_match(self):
        api = AtomSpaceAPI.create()
        predicate = api.predicate(
            "Structured", arity=2, roles=("left", "right"), acyclic=True
        )
        self.assertEqual(
            api.predicate(
                "Structured", arity=2, roles=("left", "right"), acyclic=True
            ),
            predicate,
        )
        with self.assertRaises(GraphInvariantError):
            api.predicate("Structured", arity=1)
        kind = api.kind("Thing")
        node = create_test_node(api, "interned", kind=kind, props={"x": 1}, intern=True)
        self.assertEqual(
            create_test_node(api, "interned", kind=kind, props={"x": 1}, intern=True),
            node,
        )
        with self.assertRaises(GraphInvariantError):
            create_test_node(api, "interned", kind=kind, props={"x": 2}, intern=True)
        with self.assertRaises(GraphInvariantError):
            create_test_node(api, "interned", intern=True)

    def test_raw_operations_do_not_call_logical_helpers(self):
        core = AtomSpace()
        predicate = core.predicate("P", arity=1)
        node = create_test_node(core, "node")
        link = core.create_link(predicate, node)
        core.delete(link)
        core.get = lambda atom_id: (_ for _ in ()).throw(
            AssertionError("raw operation called get()")
        )
        core._resolve_predicate = lambda value: (_ for _ in ()).throw(
            AssertionError("raw search called logical predicate resolver")
        )
        results = core.search_raw(predicate=predicate)
        self.assertEqual([result.atom_id for result in results], [link])
        self.assertIn(node, {result.atom_id for result in core.traverse_raw(node)})

    def test_local_incident_queries_ignore_unrelated_graph(self):
        core = AtomSpace()
        predicate = core.predicate("P", arity=2)
        target = create_test_node(core, "target")
        neighbor = create_test_node(core, "neighbor")
        link = core.create_link(predicate, target, neighbor)
        ligature = core.create_ligature("Local", target, neighbor)
        for index in range(100):
            unrelated = create_test_node(core, f"unrelated {index}")
            core.create_link(predicate, unrelated, neighbor)
            core.create_ligature("Other", unrelated, neighbor)

        class LocalOnly(dict):
            def get(self, key, default=None):
                if key != target:
                    raise AssertionError(f"consulted unrelated topology ID {key}")
                return super().get(key, default)

            def __iter__(self):
                raise AssertionError("iterated incoming topology")

            keys = items = values = __iter__

        core._incoming_relationships = LocalOnly(core._incoming_relationships)
        self.assertEqual(core.in_links(target), {link})
        self.assertEqual(core.in_links(target, predicate=predicate), {link})
        self.assertEqual(core.in_ligatures(target), {ligature})

    def test_traversal_distinguishes_logical_and_raw_deletion(self):
        api = AtomSpaceAPI.create()
        left = create_test_node(api, "left")
        middle = create_test_node(api, "middle")
        right = create_test_node(api, "right")
        first = api.create_ligature("First", left, middle)
        second = api.create_ligature("Second", middle, right)
        api.delete(middle)
        logical_ids = {result.atom.id for result in api.traverse(left)}
        raw = api.traverse_raw(left)
        raw_ids = {result.atom.id for result in raw}
        self.assertEqual(logical_ids, {left})
        self.assertNotIn(first, logical_ids)
        self.assertIn(right, raw_ids)
        self.assertTrue(next(r for r in raw if r.atom_id == middle).deleted)
        self.assertTrue(next(r for r in raw if r.atom_id == first).deleted)
        self.assertTrue(next(r for r in raw if r.atom_id == second).deleted)

    def test_traversal_reports_breadth_first_depths(self):
        api = AtomSpaceAPI.create()
        start = create_test_node(api, "start")
        middle = create_test_node(api, "middle")
        end = create_test_node(api, "end")
        first = api.create_ligature("First", start, middle)
        second = api.create_ligature("Second", middle, end)

        self.assertEqual(
            {item.matched_id: item.depth for item in api.traverse(start)},
            {start: 0, first: 1, middle: 2, second: 3, end: 4},
        )
        self.assertEqual(
            {item.atom_id: item.depth for item in api.traverse_raw(start)},
            {start: 0, first: 1, middle: 2, second: 3, end: 4},
        )
        self.assertEqual(
            {item.matched_id for item in api.traverse(start, max_depth=2)},
            {start, first, middle},
        )

    def test_logical_and_raw_traversal_do_not_cross_kind_edges(self):
        api = AtomSpaceAPI.create()
        kind = api.kind("SharedKind")
        start = create_test_node(api, "start", kind=kind)
        unrelated = create_test_node(api, "unrelated")
        bridge = api.create_ligature("DefinitionMetadata", kind, unrelated)

        self.assertEqual(
            {item.matched_id for item in api.traverse(start, max_depth=5)},
            {start},
        )
        self.assertEqual(
            {item.atom_id for item in api.traverse_raw(start, max_depth=5)},
            {start},
        )
        self.assertNotIn(bridge, {
            item.matched_id for item in api.traverse(start, max_depth=5)
        })

    def test_container_search_returns_depths_and_respects_maximum_depth(self):
        api = AtomSpaceAPI.create()
        container_kind = api.kind("Container")
        start = create_test_node(api, "start")
        near = create_test_node(api, "near", kind=container_kind)
        far = create_test_node(api, "far", kind=container_kind)
        api.create_ligature("Near", start, near)
        api.create_ligature("Far", near, far)

        self.assertEqual(
            api.containers(start, container_kind, max_depth=2),
            [StructuralSearchResult(near, 2)],
        )
        self.assertEqual(
            api.containers(start, container_kind, max_depth=4),
            [StructuralSearchResult(near, 2), StructuralSearchResult(far, 4)],
        )

    def test_container_search_does_not_escape_through_kind(self):
        api = AtomSpaceAPI.create()
        source_kind = api.kind("Source")
        container_kind = api.kind("Container")
        start = create_test_node(api, "start", kind=source_kind)
        hidden = create_test_node(api, "hidden", kind=container_kind)
        api.create_ligature("KindBridge", source_kind, hidden)
        self.assertEqual(api.containers(start, container_kind, max_depth=5), [])

    def test_nearest_hub_returns_all_and_only_hubs_at_minimum_depth(self):
        api = AtomSpaceAPI.create()
        hub_kind = api.kind("Hub")
        start = create_test_node(api, "start")
        left = create_test_node(api, "left", kind=hub_kind)
        right = create_test_node(api, "right", kind=hub_kind)
        farther = create_test_node(api, "farther", kind=hub_kind)
        api.create_ligature("Left", start, left)
        api.create_ligature("Right", start, right)
        api.create_ligature("Farther", left, farther)

        self.assertEqual(
            set(api.nearest_hub(start, max_depth=4)),
            {StructuralSearchResult(left, 2), StructuralSearchResult(right, 2)},
        )
        self.assertEqual(api.nearest_hub(start, max_depth=1), [])

    def test_nearest_hub_handles_start_no_hub_and_kind_boundary(self):
        api = AtomSpaceAPI.create()
        hub_kind = api.kind("Hub")
        hub = create_test_node(api, "hub", kind=hub_kind)
        self.assertEqual(
            api.nearest_hub(hub, max_depth=0),
            [StructuralSearchResult(hub, 0)],
        )
        isolated = create_test_node(api, "isolated")
        self.assertEqual(api.nearest_hub(isolated, max_depth=10), [])
        source_kind = api.kind("Source")
        source = create_test_node(api, "source", kind=source_kind)
        api.create_ligature("KindBridge", source_kind, hub)
        self.assertEqual(api.nearest_hub(source, max_depth=5), [])

    def test_traversal_has_no_redirect_options(self):
        api = AtomSpaceAPI.create()
        node = create_test_node(api, "node")
        with self.assertRaises(TypeError):
            api.traverse(node, follow_redirects=True)
        with self.assertRaises(TypeError):
            api.traverse_raw(node, follow_redirects=True)

    def test_intersection_of_two_seeds(self):
        api = AtomSpaceAPI.create()
        left, right = create_test_node(api, "left"), create_test_node(api, "right")
        shared = api.create_ligature("Shared", left, right)

        self.assertEqual(
            api.intersection([left, right], max_depth=1),
            [
                Intersection(
                    atom_id=shared,
                    seeds={left, right},
                    depths={left: 1, right: 1},
                )
            ],
        )

    def test_intersection_returns_every_shared_atom(self):
        api = AtomSpaceAPI.create()
        left, right = create_test_node(api, "left"), create_test_node(api, "right")
        first = api.create_ligature("First", left, right)
        second = api.create_ligature("Second", left, right)

        intersections = api.intersection([left, right], max_depth=1)
        self.assertEqual({result.atom_id for result in intersections}, {first, second})

    def test_intersection_of_three_seeds(self):
        api = AtomSpaceAPI.create()
        seeds = {create_test_node(api, str(index)) for index in range(3)}
        shared = api.create_ligature("Shared", *seeds)

        result = api.intersection(seeds, max_depth=1)
        self.assertEqual([item.atom_id for item in result], [shared])
        self.assertEqual(result[0].seeds, seeds)
        self.assertEqual(result[0].depths, {seed: 1 for seed in seeds})

    def test_intersection_marks_unreached_seed_with_minus_one(self):
        api = AtomSpaceAPI.create()
        left, right = create_test_node(api, "left"), create_test_node(api, "right")
        isolated = create_test_node(api, "isolated")
        shared = api.create_ligature("Shared", left, right)

        result = api.intersection([left, right, isolated], max_depth=1)
        self.assertEqual([item.atom_id for item in result], [shared])
        self.assertEqual(
            result[0].depths, {left: 1, right: 1, isolated: -1}
        )
        self.assertEqual(result[0].seeds, {left, right, isolated})

    def test_intersection_can_be_empty(self):
        api = AtomSpaceAPI.create()
        seeds = [create_test_node(api, "left"), create_test_node(api, "right")]
        self.assertEqual(api.intersection(seeds, max_depth=3), [])

    def test_intersection_respects_maximum_depth(self):
        api = AtomSpaceAPI.create()
        left, right = create_test_node(api, "left"), create_test_node(api, "right")
        middle = create_test_node(api, "middle")
        api.create_ligature("LeftMiddle", left, middle)
        api.create_ligature("RightMiddle", right, middle)

        self.assertEqual(api.intersection([left, right], max_depth=1), [])
        at_depth_two = api.intersection([left, right], max_depth=2)
        self.assertEqual([item.atom_id for item in at_depth_two], [middle])
        self.assertEqual(at_depth_two[0].depths, {left: 2, right: 2})

    def test_intersection_does_not_escape_through_kind_edges(self):
        api = AtomSpaceAPI.create()
        shared_kind = api.kind("Shared")
        left = create_test_node(api, "left", kind=shared_kind)
        right = create_test_node(api, "right", kind=shared_kind)
        unrelated = create_test_node(api, "unrelated")
        api.create_ligature("KindMetadata", shared_kind, unrelated)

        self.assertEqual(api.intersection([left, right], max_depth=5), [])

    def test_renderer_hides_deleted_atoms_and_renders_relationship_types(self):
        api = AtomSpaceAPI.create()
        predicate = api.predicate("Pair", arity=2)
        left, right = create_test_node(api, "left"), create_test_node(api, "right")
        link = api.create_link(predicate, left, right)
        ligature = api.create_ligature("Arm", left, right)
        renderer = Renderer(api)
        self.assertEqual(renderer.render(link), "Pair(left, right)")
        self.assertEqual(renderer.render(ligature), "Arm(left, right)")
        api.delete(ligature)
        self.assertEqual(renderer.render(ligature), "<deleted>")

    def test_renderer_repeats_variadic_roles(self):
        api = AtomSpaceAPI.create()
        bundle = api.predicate(
            "Bundle", arity=-1, roles=("head", "member"),
            template="{head}: {join:member}",
        )
        head = create_test_node(api, "result")
        members = [create_test_node(api, value) for value in ("a", "b", "c")]
        link = api.create_link(bundle, head, *members)
        self.assertEqual(
            Renderer(api).render_pretty(link), "result: a, b, and c"
        )

    def test_persistence_round_trip_preserves_core_state_machinery(self):
        api = AtomSpaceAPI.create()
        kind = api.kind("K")
        deleted = create_test_node(api, "deleted", kind=kind, confidence=0.5)
        live = create_test_node(api, "live", kind=kind)
        definition = api.predicate("Stored", arity=1)
        application = api.create_predicate(definition, live)
        ligature = api.create_ligature("Local", deleted, live)
        api.delete(deleted)
        current = api.make_current(live)
        historical_before = create_test_node(api, "historical before")
        historical_after = create_test_node(api, "historical after")
        transition = api.transition(historical_before, historical_after)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            api.save(path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("mutable", data)
            self.assertNotIn("redirects", data)
            self.assertNotIn("phantoms", data)
            loaded = AtomSpaceAPI.load(path)
            self.assertIsNone(loaded.get(deleted))
            self.assertTrue(loaded.get_raw(deleted).deleted)
            self.assertEqual(loaded.confidence(live), 1)
            self.assertEqual(loaded.current_predicate, api.current_predicate)
            self.assertEqual(loaded.delete_predicate, api.delete_predicate)
            self.assertIsInstance(loaded.get(kind), KindAtom)
            self.assertIsInstance(loaded.get(definition), PredicateAtom)
            self.assertIsInstance(loaded.get(live), Node)
            self.assertIsInstance(loaded.get(application), Predicate)
            self.assertIsInstance(loaded.get(transition), Transition)
            self.assertEqual(
                loaded.transition_args(transition),
                (historical_before, historical_after),
            )
            self.assertIsNotNone(loaded.get(current))
            self.assertIsNone(loaded.get(ligature))
            self.assertTrue(loaded.get_raw(ligature).deleted)
            self.assertIsInstance(loaded.get_raw(ligature).atom, Ligature)
            self.assertNotIn("deleted_ids", data)
            stored_types = {atom["type"] for atom in data["atoms"]}
            self.assertTrue({
                "Node", "Predicate", "Ligature", "Transition",
                "KindAtom", "PredicateAtom",
            }.issubset(stored_types))
            self.assertNotIn("Link", stored_types)

    def test_persistence_requires_current_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            path.write_text(json.dumps({}), encoding="utf-8")
            with self.assertRaises(SchemaVersionError):
                AtomSpaceAPI.load(path)
            path.write_text(json.dumps({"schema_version": 6}), encoding="utf-8")
            with self.assertRaises(SchemaVersionError):
                AtomSpaceAPI.load(path)

    def test_persistence_rejects_missing_or_invalid_node_kind(self):
        api = AtomSpaceAPI.create()
        kind = api.kind("Thing")
        node = api.create_node("node", kind=kind)
        definition = api.predicate("Definition", arity=0)

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "base.json"
            api.save(base)
            original = json.loads(base.read_text(encoding="utf-8"))

            for invalid_kind in (0, definition, 9999):
                with self.subTest(kind=invalid_kind):
                    data = json.loads(json.dumps(original))
                    stored_node = next(
                        atom for atom in data["atoms"] if atom["id"] == node
                    )
                    stored_node["kind"] = invalid_kind
                    path = Path(directory) / f"invalid-kind-{invalid_kind}.json"
                    path.write_text(json.dumps(data), encoding="utf-8")
                    with self.assertRaises(GraphInvariantError):
                        AtomSpaceAPI.load(path)

            missing = json.loads(json.dumps(original))
            stored_node = next(
                atom for atom in missing["atoms"] if atom["id"] == node
            )
            stored_node.pop("kind")
            path = Path(directory) / "missing-kind.json"
            path.write_text(json.dumps(missing), encoding="utf-8")
            with self.assertRaises(MalformedPersistenceError):
                AtomSpaceAPI.load(path)

            deleted_kind = json.loads(json.dumps(original))
            assertion_id = deleted_kind["next_id"]
            deleted_kind["next_id"] += 1
            deleted_kind["atoms"].append({
                "args": [kind],
                "created_at_utc": "2026-01-01T00:00:00Z",
                "id": assertion_id,
                "label": None,
                "predicate": api.delete_predicate,
                "type": "Predicate",
            })
            deleted_kind["confidence"][str(assertion_id)] = 1.0
            path = Path(directory) / "deleted-kind.json"
            path.write_text(json.dumps(deleted_kind), encoding="utf-8")
            with self.assertRaises(GraphInvariantError):
                AtomSpaceAPI.load(path)

    def test_persistence_rejects_live_relationship_at_deleted_atom(self):
        api = AtomSpaceAPI.create()
        target, other = create_test_node(api, "target"), create_test_node(api, "other")
        api.create_ligature("Local", target, other)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.json"
            api.save(path)
            data = json.loads(path.read_text(encoding="utf-8"))
            assertion_id = data["next_id"]
            data["next_id"] += 1
            data["atoms"].append({
                "args": [target],
                "created_at_utc": "2026-01-01T00:00:00Z",
                "id": assertion_id,
                "label": None,
                "predicate": api.delete_predicate,
                "type": "Predicate",
            })
            data["confidence"][str(assertion_id)] = 1.0
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(GraphInvariantError):
                AtomSpaceAPI.load(path)

    def test_persistence_rejects_reserved_identity_and_current_arguments(self):
        api = AtomSpaceAPI.create()
        node = create_test_node(api, "node")
        current = api.make_current(node)
        predicate = api.predicate("Domain", arity=1)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "base.json"
            api.save(base)

            reserved = json.loads(base.read_text(encoding="utf-8"))
            for atom in reserved["atoms"]:
                if atom["id"] == predicate:
                    atom["label"] = "Current"
            reserved_path = Path(directory) / "reserved.json"
            reserved_path.write_text(json.dumps(reserved), encoding="utf-8")
            with self.assertRaises(GraphInvariantError):
                AtomSpaceAPI.load(reserved_path)

            illegal = json.loads(base.read_text(encoding="utf-8"))
            ligature_id = illegal["next_id"]
            illegal["next_id"] += 1
            illegal["atoms"].append({
                "args": [current],
                "created_at_utc": "2026-01-01T00:00:00Z",
                "id": ligature_id,
                "label": None,
                "name": "Illegal",
                "type": "Ligature",
            })
            illegal["confidence"][str(ligature_id)] = 1.0
            illegal_path = Path(directory) / "current-argument.json"
            illegal_path.write_text(json.dumps(illegal), encoding="utf-8")
            with self.assertRaises(GraphInvariantError):
                AtomSpaceAPI.load(illegal_path)

            malformed_transition = json.loads(base.read_text(encoding="utf-8"))
            transition_id = malformed_transition["next_id"]
            malformed_transition["next_id"] += 1
            malformed_transition["atoms"].append({
                "args": [node],
                "created_at_utc": "2026-01-01T00:00:00Z",
                "id": transition_id,
                "label": None,
                "type": "Transition",
            })
            malformed_transition["confidence"][str(transition_id)] = 1.0
            malformed_path = Path(directory) / "malformed-transition.json"
            malformed_path.write_text(
                json.dumps(malformed_transition), encoding="utf-8"
            )
            with self.assertRaises(GraphInvariantError):
                AtomSpaceAPI.load(malformed_path)

            current_transition = json.loads(base.read_text(encoding="utf-8"))
            transition_id = current_transition["next_id"]
            current_transition["next_id"] += 1
            current_transition["atoms"].append({
                "args": [current, node],
                "created_at_utc": "2026-01-01T00:00:00Z",
                "id": transition_id,
                "label": None,
                "type": "Transition",
            })
            current_transition["confidence"][str(transition_id)] = 1.0
            current_path = Path(directory) / "current-transition.json"
            current_path.write_text(
                json.dumps(current_transition), encoding="utf-8"
            )
            with self.assertRaises(GraphInvariantError):
                AtomSpaceAPI.load(current_path)

    def test_facade_is_explicit_and_has_no_removed_operations(self):
        for method_name, method in inspect.getmembers(
            AtomSpaceAPI, predicate=inspect.isfunction
        ):
            if method_name.startswith("_"):
                continue
            signature = inspect.signature(method)
            self.assertFalse(any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in signature.parameters.values()
            ))
        api = AtomSpaceAPI.create()
        for removed in (
            "mutate", "remove_mutable", "register_phantom",
            "add", "check", "retrieve",
        ):
            self.assertFalse(hasattr(api, removed))

    def test_production_modules_do_not_access_core_private_storage(self):
        package = Path(__file__).parents[1] / "atomforge"
        forbidden = {
            "_atoms", "_confidence", "_incoming_relationships", "_by_pred",
            "_predicate_key_index", "_label_index", "_kind_intern",
            "_pred_intern", "_resolve_kind", "_resolve_predicate",
        }
        violations = []
        for path in package.glob("*.py"):
            if path.name == "core.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in forbidden:
                    violations.append(f"{path.name}:{node.lineno}:{node.attr}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
