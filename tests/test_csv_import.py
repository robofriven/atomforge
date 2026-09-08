import tempfile
import unittest
from pathlib import Path

from atomforge import AtomSpaceAPI, Ligature, Node
from atomforge.csv_import import import_links_csv


class CsvGraphFixtureTests(unittest.TestCase):
    def load(self, content: str):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "graph.csv"
        path.write_text(content, encoding="utf-8")
        api = AtomSpaceAPI.create()
        node_kind = api.kind("ImportedNode")
        report = import_links_csv(api, path, node_kind=node_kind)
        return api, report

    def test_creates_binary_ligature_and_referenced_nodes(self):
        api, report = self.load(
            "relationship_name,atom_a,atom_b,type\nArm,John,LeftArm,L\n"
        )

        self.assertEqual(report.ligatures_created, 1)
        self.assertEqual(report.nodes_created, 2)
        john = api.find_by_label("John")[0]
        arm = api.find_by_label("LeftArm")[0]
        relationships = api.search(atom_type=Ligature)
        self.assertIsInstance(api.get(john), Node)
        self.assertIsInstance(api.get(arm), Node)
        self.assertEqual(len(relationships), 1)
        relationship = relationships[0].atom
        self.assertEqual(relationship.name, "Arm")
        self.assertEqual(relationship.args, (john, arm))

    def test_reuses_an_existing_node(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "graph.csv"
        path.write_text(
            "relationship_name,atom_a,atom_b,type\nArm,John,LeftArm,L\n",
            encoding="utf-8",
        )
        api = AtomSpaceAPI.create()
        node_kind = api.kind("ImportedNode")
        john = api.create_node("John", kind=node_kind)

        report = import_links_csv(api, path, node_kind=node_kind)

        self.assertEqual(report.nodes_created, 1)
        self.assertEqual(api.search(atom_type=Ligature)[0].atom.args[0], john)

    def test_reuses_nodes_when_labels_repeat(self):
        api, report = self.load(
            "relationship_name,atom_a,atom_b,type\nFirst,A,B,L\nSecond,B,C,L\n"
        )

        self.assertEqual(report.nodes_created, 3)
        self.assertEqual(len(api.find_by_label("B")), 1)

    def test_loads_connected_graph_for_traversal_and_intersection(self):
        api, report = self.load(
            "relationship_name,atom_a,atom_b,type\n"
            "LeftPath,Left,Middle,L\nRightPath,Right,Middle,L\n"
        )
        left = api.find_by_label("Left")[0]
        right = api.find_by_label("Right")[0]
        middle = api.find_by_label("Middle")[0]

        self.assertEqual(report.ligatures_created, 2)
        self.assertIn(middle, {item.matched_id for item in api.traverse(left)})
        intersections = api.intersection([left, right], max_depth=2)
        self.assertEqual([item.atom_id for item in intersections], [middle])
        self.assertEqual(intersections[0].depths, {left: 2, right: 2})

    def test_predicate_rows_are_recognized_but_not_implemented(self):
        with self.assertRaisesRegex(
            NotImplementedError, "predicate loading is not implemented"
        ):
            self.load("relationship_name,atom_a,atom_b,type\nPartOf,Hand,John,P\n")

    def test_rejects_invalid_relationship_type(self):
        with self.assertRaisesRegex(ValueError, "invalid relationship type"):
            self.load("relationship_name,atom_a,atom_b,type\nArm,John,LeftArm,X\n")

    def test_rejects_each_missing_required_field(self):
        rows = [
            ",John,LeftArm,L",
            "Arm,,LeftArm,L",
            "Arm,John,,L",
            "Arm,John,LeftArm,",
        ]
        for row in rows:
            with (
                self.subTest(row=row),
                self.assertRaisesRegex(ValueError, "missing required field"),
            ):
                self.load("relationship_name,atom_a,atom_b,type\n" + row + "\n")

    def test_rejects_malformed_header(self):
        with self.assertRaisesRegex(ValueError, "CSV columns must be"):
            self.load("predicate,arg1,arg2\nArm,John,LeftArm\n")


if __name__ == "__main__":
    unittest.main()
