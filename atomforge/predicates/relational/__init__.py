"""Relational predicate vocabulary and its domain-level rule semantics."""

from __future__ import annotations

from typing import Dict, Optional
from weakref import WeakKeyDictionary

from ...atoms import AtomId
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
    "Own": ("owner", "thing"),
    "PartOf": ("part", "whole"),
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
        for name in ("In", "Above", "PartOf", "North", "East"):
            self.rules.register(self.predicates[name], Transitive())

        self.rules.register(self.Below, Inverse(self.Above))
        self.rules.register(self.South, Inverse(self.North))
        self.rules.register(self.West, Inverse(self.East))

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
