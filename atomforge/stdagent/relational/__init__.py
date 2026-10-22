"""Relational predicate vocabulary and its domain-level rule semantics.

``IsA(specific, general)`` is the vocabulary's taxonomy predicate:
directional and transitive.  Asserting IsA(Catholic, Christian) and
IsA(Christian, Religion) makes IsA(Catholic, Religion) true at query
time — the inference is evaluated by the rules layer, never written
back as an atom — while the reverse stays false: a general category
is not thereby a member of its own subcategory.  A hierarchy admits
no self-loops and no cycles, so ``relate`` refuses those IsA
assertions before anything is written.  Kind atoms are ordinary
arguments here, so kind taxonomy is data in this same predicate —
IsA(SexAct-kind, Act-kind) — not a special mechanism.
:meth:`RelationalPredicates.is_a` answers the membership question
("is this atom at or below that category?"), identity included.
"""

from __future__ import annotations

from typing import Dict, Optional
from weakref import WeakKeyDictionary

from ...atoms import AtomId, KindAtom, Node
from ...facade import AtomSpaceAPI
from ...rules.generic import Inverse, RuleSet, Symmetric, Transitive


_RELATIONAL_SPECS = {
    "At": ("thing", "place"),
    "In": ("thing", "container"),
    "On": ("thing", "support"),
    "Near": ("thing", "thing"),
    "Above": ("thing", "thing"),
    "Below": ("thing", "thing"),
    "Ahead": ("thing", "thing"),
    "Behind": ("thing", "thing"),
    "Touch": ("thing", "thing"),
    "Attach": ("thing", "thing"),
    "Hold": ("holder", "thing"),
    "Wear": ("wearer", "thing"),
    "Own": ("owner", "item"),
    "PartOf": ("part", "whole"),
    "IsA": ("specific", "general"),
    "North": ("thing", "thing"),
    "South": ("thing", "thing"),
    "East": ("thing", "thing"),
    "West": ("thing", "thing"),
}

_INSTALLATIONS: "WeakKeyDictionary[AtomSpaceAPI, RelationalPredicates]" = (
    WeakKeyDictionary()
)


class RelationalPredicates:
    """Installed relational vocabulary bound to one :class:`AtomSpaceAPI`."""

    def __init__(self, api: AtomSpaceAPI) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self.api = api
        self.predicates: Dict[str, AtomId] = {}
        for name, roles in _RELATIONAL_SPECS.items():
            predicate = api.predicate(name, arity=2, roles=roles)
            self.predicates[name] = predicate
            setattr(self, name, predicate)

        self.rules = RuleSet(api)
        self._install_rules()

    def __getitem__(self, name: str) -> AtomId:
        return self.predicates[name]

    def _install_rules(self) -> None:
        for name in ("Near", "Touch", "Attach"):
            self.rules.register(self.predicates[name], Symmetric())
        for name in ("In", "Above", "PartOf", "IsA", "North", "East"):
            self.rules.register(self.predicates[name], Transitive())

        self.rules.register(self.Below, Inverse(self.Above))
        self.rules.register(self.South, Inverse(self.North))
        self.rules.register(self.West, Inverse(self.East))

    def _check_isa(self, specific: AtomId, general: AtomId) -> None:
        """Preflight one IsA assertion: a hierarchy admits no self-loop
        and no cycle.  The cycle check rides the transitive query —
        if ``general`` already reaches ``specific``, the new edge
        would close a loop and collapse the hierarchy at that pair.
        Checked before anything is written, so a refused assertion
        leaves the graph untouched."""
        if specific == general:
            raise TypeError("IsA cannot relate an atom to itself")
        if self.has(self.IsA, general, specific):
            raise TypeError(
                "IsA assertion would close a cycle in the hierarchy"
            )

    def relate(
        self,
        predicate: AtomId,
        left: AtomId,
        right: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert one relationship using this vocabulary's canonicalization."""
        if predicate == self.IsA:
            self._check_isa(left, right)
        return self.rules.create_predicate(
            predicate,
            left,
            right,
            label=label,
            confidence=confidence,
        )

    create_predicate = relate
    create_link = relate

    def has(self, predicate: AtomId, left: AtomId, right: AtomId) -> bool:
        """Query a relationship using rules without materializing inferences."""
        return self.rules.has_predicate(predicate, left, right)

    has_predicate = has
    has_link = has

    def is_a(self, specific: AtomId, general: AtomId) -> bool:
        """Answer taxonomy membership: ``specific`` is ``general``
        itself, or sits below it under asserted IsA edges.  Identity
        counts as membership at query time, unlike in assertion —
        relate() refuses a self-IsA as carrying no information."""
        return specific == general or self.has(self.IsA, specific, general)

    def kind_is_a(self, atom_id: AtomId, general_kind: AtomId) -> bool:
        """Answer whether an atom's kind sits at or below
        ``general_kind`` in the IsA hierarchy.  Accepts a Node (its
        kind is checked) or a KindAtom (checked directly); any other
        atom type is not kinded and answers False.  This is the
        hierarchy-aware replacement for ``atom.kind == some_kind``
        in module kind checks."""
        atom = self.api.get(atom_id)
        if isinstance(atom, KindAtom):
            kind = atom.id
        elif isinstance(atom, Node):
            kind = atom.kind
        else:
            return False
        return self.is_a(kind, general_kind)


def install(api: AtomSpaceAPI) -> RelationalPredicates:
    """Install and return a relational vocabulary for ``api``."""
    installed = _INSTALLATIONS.get(api)
    if installed is None:
        installed = RelationalPredicates(api)
        _INSTALLATIONS[api] = installed
    return installed


install_relational_predicates = install
Relational = RelationalPredicates

__all__ = [
    "RelationalPredicates", "Relational", "install",
    "install_relational_predicates",
]
