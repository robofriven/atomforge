"""General logical relationship vocabulary and its rule semantics.

These relations hold between statement atoms -- assertions that are
themselves atoms and can therefore be arguments.  This module is
general-purpose: domain modules (obligations, preferences, knowledge)
may depend on it, and it depends on none of them.
"""

from __future__ import annotations

from typing import Dict, Optional
from weakref import WeakKeyDictionary

from ...atoms import AtomId
from ...facade import AtomSpaceAPI
from ...rules.generic import RuleSet, Symmetric, Transitive


_LOGIC_SPECS = {
    "Contradicts": ("statement", "statement"),
    "Implies": ("premise", "conclusion"),
    "Supports": ("evidence", "statement"),
}

_INSTALLATIONS: "WeakKeyDictionary[AtomSpaceAPI, LogicPredicates]" = (
    WeakKeyDictionary()
)


class LogicPredicates:
    """Installed logical vocabulary bound to one :class:`AtomSpaceAPI`."""

    def __init__(self, api: AtomSpaceAPI) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self.api = api
        self.predicates: Dict[str, AtomId] = {}
        for name, roles in _LOGIC_SPECS.items():
            predicate = api.predicate(name, arity=2, roles=roles)
            self.predicates[name] = predicate
            setattr(self, name, predicate)

        self.rules = RuleSet(api)
        self._install_rules()

    def __getitem__(self, name: str) -> AtomId:
        return self.predicates[name]

    def _install_rules(self) -> None:
        # Contradiction is mutual: if A contradicts B, B contradicts A.
        self.rules.register(self.Contradicts, Symmetric())
        # Implication chains: A -> B and B -> C satisfy a query for A -> C.
        self.rules.register(self.Implies, Transitive())

    def relate(
        self,
        predicate: AtomId,
        left: AtomId,
        right: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert one logical relationship using this vocabulary's rules."""
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


def install(api: AtomSpaceAPI) -> LogicPredicates:
    """Install and return a logical vocabulary for ``api``."""
    installed = _INSTALLATIONS.get(api)
    if installed is None:
        installed = LogicPredicates(api)
        _INSTALLATIONS[api] = installed
    return installed


install_logic_predicates = install
Logic = LogicPredicates

__all__ = [
    "LogicPredicates", "Logic", "install",
    "install_logic_predicates",
]
