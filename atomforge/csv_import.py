from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

from .core import AtomSpace
from .atoms import AtomId


@dataclass
class ImportReport:
    links_created: int = 0
    nodes_created: int = 0
    created_node_labels: List[str] | None = None

    def __post_init__(self) -> None:
        if self.created_node_labels is None:
            self.created_node_labels = []

    def __str__(self) -> str:
        lines = [
            "ImportReport:",
            f"  Links created : {self.links_created}",
            f"  Nodes created : {self.nodes_created}",
        ]
        if self.created_node_labels:
            lines.append("  Auto-created node labels:")
            for lbl in self.created_node_labels:
                lines.append(f"    - {lbl}")
        return "\n".join(lines)


def _first_nonempty(values: Iterable[str]) -> Optional[str]:
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s != "":
            return s
    return None


def import_links_csv(
    space: AtomSpace,
    path: Union[str, Path],
    *,
    predicate_col: str = "predicate",
    label_col: str = "label",
    arg_prefix: str = "arg",
    create_missing_nodes: bool = True,
    default_kind: str = "Entity",
) -> ImportReport:
    """
    Excel-friendly link importer.

    Expected columns:
      - predicate (required)
      - arg1..argN (any count; blanks ignored)
      - label (optional; link label)

    Behavior:
      - Any referenced arg label not found -> auto-create Node(label, kind=default_kind)
        if create_missing_nodes=True.
    """
    path = Path(path)
    report = ImportReport()

    # Cache label->id for consistency + speed
    label_cache: Dict[str, AtomId] = {}

    def resolve_node(label: str) -> AtomId:
        lbl = label.strip()
        if lbl in label_cache:
            return label_cache[lbl]

        hits = space.find_by_label(lbl)
        if hits:
            label_cache[lbl] = hits[0]
            return hits[0]

        if not create_missing_nodes:
            raise KeyError(f"links.csv references unknown label {lbl!r}")

        nid = space.add.node(lbl, kind=default_kind, intern=True)
        label_cache[lbl] = nid
        report.nodes_created += 1
        report.created_node_labels.append(lbl)
        return nid

    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")

        fieldnames = [fn.strip() for fn in reader.fieldnames if fn]

        if predicate_col not in fieldnames:
            raise ValueError(f"CSV missing required column {predicate_col!r}")

        # Sort arg columns numerically: arg1, arg2, arg3...
        def arg_sort_key(name: str) -> int:
            tail = name[len(arg_prefix) :]
            try:
                return int(tail)
            except Exception:
                return 10**9

        arg_cols = sorted(
            [fn for fn in fieldnames if fn.startswith(arg_prefix)],
            key=arg_sort_key,
        )

        for row_i, row in enumerate(reader, start=2):  # 2 = first data row
            pred = _first_nonempty([row.get(predicate_col, "")])
            if not pred:
                # Allow blank rows
                continue

            arg_labels: List[str] = []
            for c in arg_cols:
                v = row.get(c, "")
                if v is None:
                    continue
                s = str(v).strip()
                if s != "":
                    arg_labels.append(s)

            if not arg_labels:
                raise ValueError(
                    f"Row {row_i}: predicate {pred!r} has no args (need arg1...)"
                )

            arg_ids: Tuple[AtomId, ...] = tuple(resolve_node(lbl) for lbl in arg_labels)

            link_label = None
            if label_col in fieldnames:
                link_label = _first_nonempty([row.get(label_col, "")])

            try:
                space.add.link(pred, *arg_ids, label=link_label)
            except KeyError as e:
                raise KeyError(f"Row {row_i}: {e}") from e

            report.links_created += 1

    return report
