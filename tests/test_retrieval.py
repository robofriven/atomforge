import unittest

from atomforge import AtomSpaceAPI, UnknownAtomError
from atomforge.retrieval import StructuralRetriever, retrieve


class StructuralRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.container_kind = self.api.kind("Container")
        self.retriever = StructuralRetriever(self.api)

    def connected_context(self, name, *candidates):
        container = self.api.create_node(name, kind=self.container_kind)
        intersection = self.api.create_ligature(
            f"{name} intersection", *candidates
        )
        membership = self.api.create_ligature(
            f"{name} context", intersection, container
        )
        return container, intersection, membership

    def test_two_candidates_find_intersection_container_and_depths(self):
        left = self.api.create_node("left")
        right = self.api.create_node("right")
        container, intersection, membership = self.connected_context(
            "context", left, right
        )

        result = retrieve(
            self.api,
            [right, left],
            container_definition_id=self.container_kind,
            intersection_depth=1,
            container_depth=2,
            retrieval_depth=2,
        )

        self.assertEqual(result.candidate_atom_ids, (left, right))
        found = next(item for item in result.intersections
                     if item.atom_id == intersection)
        self.assertEqual(found.candidate_depths, ((left, 1), (right, 1)))
        self.assertEqual(found.coverage, 2)
        self.assertEqual(found.combined_depth, 2)
        evidence = next(item for item in result.container_evidence
                        if item.container_atom_id == container)
        self.assertEqual(evidence.intersection_atom_id, intersection)
        self.assertEqual(evidence.intersection_depth, 2)
        self.assertEqual(result.selected_container_atom_ids, (container,))
        self.assertIn(membership, result.retrieved_atom_ids)

    def test_more_candidate_coverage_ranks_before_less(self):
        first = self.api.create_node("first")
        second = self.api.create_node("second")
        third = self.api.create_node("third")
        broad = self.api.create_ligature("broad", first, second, third)
        narrow = self.api.create_ligature("narrow", first, second)

        intersections = self.retriever.find_intersections(
            (first, second, third), max_depth=1
        )
        self.assertEqual(intersections[0].atom_id, broad)
        self.assertEqual(intersections[0].coverage, 3)
        self.assertTrue(any(item.atom_id == narrow and item.coverage == 2
                            for item in intersections))
        self.assertEqual(
            self.retriever.select_intersections(intersections),
            (intersections[0],),
        )

    def test_shorter_combined_depth_ranks_higher(self):
        left = self.api.create_node("left")
        right = self.api.create_node("right")
        near = self.api.create_ligature("near", left, right)
        middle_left = self.api.create_node("middle left")
        middle_right = self.api.create_node("middle right")
        self.api.create_ligature("left path", left, middle_left)
        self.api.create_ligature("right path", right, middle_right)
        far = self.api.create_ligature("far", middle_left, middle_right)

        intersections = self.retriever.find_intersections(
            (left, right), max_depth=4
        )
        self.assertLess(
            next(x.combined_depth for x in intersections if x.atom_id == near),
            next(x.combined_depth for x in intersections if x.atom_id == far),
        )
        self.assertIn(near, {
            item.atom_id
            for item in self.retriever.select_intersections(intersections)
        })

    def test_tied_intersections_and_tied_containers_are_retained(self):
        left = self.api.create_node("left")
        right = self.api.create_node("right")
        first_intersection = self.api.create_ligature("first", left, right)
        second_intersection = self.api.create_ligature("second", left, right)
        first_container = self.api.create_node(
            "first context", kind=self.container_kind
        )
        second_container = self.api.create_node(
            "second context", kind=self.container_kind
        )
        self.api.create_ligature(
            "first membership", first_intersection, first_container
        )
        self.api.create_ligature(
            "second membership", second_intersection, second_container
        )

        result = self.retriever.retrieve(
            [left, right],
            container_definition_id=self.container_kind,
            intersection_depth=1,
            container_depth=2,
            retrieval_depth=1,
        )
        self.assertEqual(
            {item.atom_id for item in result.relevant_intersections},
            {first_intersection, second_intersection},
        )
        self.assertEqual(
            set(result.selected_container_atom_ids),
            {first_container, second_container},
        )

    def test_multiple_intersections_can_support_same_container(self):
        left = self.api.create_node("left")
        right = self.api.create_node("right")
        container = self.api.create_node("context", kind=self.container_kind)
        for name in ("first", "second"):
            intersection = self.api.create_ligature(name, left, right)
            self.api.create_ligature(name + " membership", intersection, container)

        result = self.retriever.retrieve(
            [left, right],
            container_definition_id=self.container_kind,
            intersection_depth=1,
            container_depth=2,
            retrieval_depth=1,
        )
        self.assertEqual(result.selected_container_atom_ids, (container,))
        self.assertEqual(len(result.ranked_containers[0].evidence), 2)

    def test_no_intersection_and_no_container_are_explicit(self):
        left = self.api.create_node("left")
        right = self.api.create_node("right")
        empty = self.retriever.retrieve(
            [left, right],
            container_definition_id=self.container_kind,
            intersection_depth=2,
            container_depth=2,
            retrieval_depth=2,
        )
        self.assertEqual(empty.intersections, ())
        self.assertEqual(empty.selected_container_atom_ids, ())

        self.api.create_ligature("intersection", left, right)
        no_container = self.retriever.retrieve(
            [left, right],
            container_definition_id=self.container_kind,
            intersection_depth=1,
            container_depth=2,
            retrieval_depth=2,
        )
        self.assertTrue(no_container.intersections)
        self.assertEqual(no_container.container_evidence, ())

    def test_bounded_retrieval_excludes_unrelated_region(self):
        left = self.api.create_node("left")
        right = self.api.create_node("right")
        container, _, _ = self.connected_context("context", left, right)
        unrelated = self.api.create_node("unrelated")
        unrelated_link = self.api.create_ligature("remote", left, unrelated)

        result = self.retriever.retrieve(
            [left, right],
            container_definition_id=self.container_kind,
            intersection_depth=1,
            container_depth=2,
            retrieval_depth=2,
        )
        subgraph = next(x for x in result.subgraphs
                        if x.container_atom_id == container)
        self.assertNotIn(unrelated, subgraph.atom_ids)
        self.assertNotIn(unrelated_link, subgraph.atom_ids)

    def test_kind_boundary_is_respected_end_to_end(self):
        shared_kind = self.api.kind("Shared")
        left = self.api.create_node("left", kind=shared_kind)
        right = self.api.create_node("right", kind=shared_kind)
        hidden_container = self.api.create_node(
            "hidden", kind=self.container_kind
        )
        self.api.create_ligature(
            "kind metadata", shared_kind, hidden_container
        )

        result = self.retriever.retrieve(
            [left, right],
            container_definition_id=self.container_kind,
            intersection_depth=4,
            container_depth=4,
            retrieval_depth=4,
        )
        self.assertEqual(result.intersections, ())
        self.assertEqual(result.subgraphs, ())

    def test_overlapping_contexts_use_intersection_before_container_search(self):
        person = self.api.create_node("person")
        object_one = self.api.create_node("object one")
        object_two = self.api.create_node("object two")
        relevant, _, _ = self.connected_context(
            "relevant", person, object_one
        )
        irrelevant, _, _ = self.connected_context(
            "irrelevant", person, object_two
        )

        result = self.retriever.retrieve(
            [person, object_one],
            container_definition_id=self.container_kind,
            intersection_depth=1,
            container_depth=2,
            retrieval_depth=2,
        )
        self.assertEqual(result.selected_container_atom_ids, (relevant,))
        self.assertNotIn(irrelevant, result.retrieved_atom_ids)

    def test_invalid_candidates_and_depths_are_rejected(self):
        valid = self.api.create_node("valid")
        with self.assertRaises(UnknownAtomError):
            self.retriever.retrieve(
                [valid, 99999],
                container_definition_id=self.container_kind,
                intersection_depth=1,
                container_depth=1,
                retrieval_depth=1,
            )
        with self.assertRaises(ValueError):
            self.retriever.retrieve(
                [],
                container_definition_id=self.container_kind,
                intersection_depth=1,
                container_depth=1,
                retrieval_depth=1,
            )
        with self.assertRaises(ValueError):
            self.retriever.retrieve(
                [valid],
                container_definition_id=self.container_kind,
                intersection_depth=-1,
                container_depth=1,
                retrieval_depth=1,
            )


if __name__ == "__main__":
    unittest.main()
