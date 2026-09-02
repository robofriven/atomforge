"""Minimal CSV graph-fixture loader."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Union

from .atoms import AtomId, Node
from .facade import AtomSpaceAPI


@dataclass
class ImportReport:
    ligatures_created: int = 0
    nodes_created: int = 0
    created_node_labels: List[str] = field(default_factory=list)


def import_links_csv(
    space: AtomSpaceAPI, path: Union[str, Path]
) -> ImportReport:
    """Load binary Ligatures from a four-column CSV fixture."""
    report = ImportReport()
    label_cache: Dict[str, AtomId] = {}

    def resolve_node(label: str) -> AtomId:
        if label in label_cache:
            return label_cache[label]
        for atom_id in space.find_by_label(label):
            if isinstance(space.get(atom_id), Node):
                label_cache[label] = atom_id
                return atom_id
        atom_id = space.create_node(label, intern=True)
        label_cache[label] = atom_id
        report.nodes_created += 1
        report.created_node_labels.append(label)
        return atom_id

    with Path(path).open("r", newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        expected_columns = ["relationship_name", "atom_a", "atom_b", "type"]
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")
        if reader.fieldnames != expected_columns:
            raise ValueError(
                "CSV columns must be relationship_name, atom_a, atom_b, type"
            )

        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"Row {row_number}: expected exactly four fields")
            values = {
                column: (row.get(column) or "").strip()
                for column in expected_columns
            }
            for column in expected_columns:
                if not values[column]:
                    raise ValueError(f"Row {row_number}: missing required field {column!r}")

            relationship_type = values["type"]
            if relationship_type == "P":
                raise NotImplementedError(
                    "CSV predicate loading is not implemented"
                )
            if relationship_type != "L":
                raise ValueError(
                    f"Row {row_number}: invalid relationship type "
                    f"{relationship_type!r}; expected 'L' or 'P'"
                )

            atom_a = resolve_node(values["atom_a"])
            atom_b = resolve_node(values["atom_b"])
            space.create_ligature(
                values["relationship_name"], atom_a, atom_b
            )
            report.ligatures_created += 1

    return report
