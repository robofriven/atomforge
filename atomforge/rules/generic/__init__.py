"""Generic, domain-independent binary predicate rules.

Rules are interpreted here, above Core.  Symmetric and transitive facts are
query-time consequences; they are not materialized as additional Predicates.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple, Union

from ...atoms import AtomId, Predicate, PredicateAtom
from ...facade import AtomSpaceAPI
from ...infrastructure import GraphInvariantError

NameOrId = Union[str, AtomId]
Arguments = Tuple[AtomId, ...]


@dataclass(frozen=True)
class Symmetric:
    """Declare that ``P(a, b)`` also satisfies a query for ``P(b, a)``."""


@dataclass(frozen=True)
class Transitive:
    """Declare that ``P(a, b)`` and ``P(b, c)`` satisfy ``P(a, c)``."""


@dataclass(frozen=True)
class Inverse:
    """Rewrite an inverse predicate to a canonical predicate.

    By default ``Inverse(target)`` maps ``Source(a, b)`` to
    ``target(b, a)`` for both assertions and semantic queries.
    """

    canonical_predicate: NameOrId
    swap_arguments: bool = True

    def canonicalize(self, args: Arguments) -> tuple[NameOrId, Arguments]:
        if len(args) != 2:
            raise TypeError("Inverse requires a binary predicate")
        return (
            self.canonical_predicate,
            (args[1], args[0]) if self.swap_arguments else args,
        )


class RuleSet:
    """Domain-layer rule registration, assertion, and semantic querying."""

    def __init__(self, api: AtomSpaceAPI) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self.api = api
        self._rules: Dict[AtomId, Tuple[object, ...]] = {}

    def register(self, predicate: AtomId, *rules: object) -> None:
        definition = self.api.get(predicate)
        if not isinstance(definition, PredicateAtom):
            raise TypeError("rules can only be assigned to a PredicateAtom")
        if definition.arity != 2:
            raise TypeError("generic relational rules require a binary predicate")
        if not all(isinstance(rule, (Symmetric, Transitive, Inverse)) for rule in rules):
            raise TypeError("unsupported generic rule")
        self._rules[predicate] = self._rules.get(predicate, ()) + tuple(rules)

    def rules_for(self, predicate: AtomId) -> Tuple[object, ...]:
        return self._rules.get(predicate, ())

    def canonicalize(
        self, predicate: AtomId, args: Iterable[AtomId]
    ) -> tuple[AtomId, Arguments]:
        current_predicate = predicate
        current_args = tuple(int(value) for value in args)
        seen = set()
        while True:
            state = (current_predicate, current_args)
            if state in seen:
                raise GraphInvariantError(
                    "predicate rules form a canonicalization cycle"
                )
            seen.add(state)
            inverse = next(
                (
                    rule
                    for rule in self.rules_for(current_predicate)
                    if isinstance(rule, Inverse)
                ),
                None,
            )
            if inverse is None:
                return current_predicate, current_args
            target, current_args = inverse.canonicalize(current_args)
            target_atom = self.api.get(target) if isinstance(target, int) else None
            if target_atom is None and isinstance(target, str):
                matches = [
                    result.atom
                    for result in self.api.search(
                        label=target, atom_type=PredicateAtom
                    )
                ]
                if len(matches) != 1:
                    raise GraphInvariantError(
                        f"canonical predicate {target!r} is not unique"
                    )
                target_atom = matches[0]
            if not isinstance(target_atom, PredicateAtom):
                raise TypeError("canonical target must be a PredicateAtom")
            current_predicate = target_atom.id

    def create_predicate(
        self,
        predicate: AtomId,
        *args: AtomId,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Store one asserted Predicate, canonicalizing when configured."""
        canonical_predicate, canonical_args = self.canonicalize(predicate, args)
        return self.api.create_predicate(
            canonical_predicate,
            *canonical_args,
            label=label,
            confidence=confidence,
        )

    def has_predicate(self, predicate: AtomId, *args: AtomId) -> bool:
        """Evaluate registered rules without writing inferred relationships."""
        canonical_predicate, wanted = self.canonicalize(predicate, args)
        if len(wanted) != 2:
            raise TypeError("generic relational rules require two arguments")
        if self.api.find_predicates(canonical_predicate, *wanted):
            return True
        rules = self.rules_for(canonical_predicate)
        symmetric = any(isinstance(rule, Symmetric) for rule in rules)
        transitive = any(isinstance(rule, Transitive) for rule in rules)

        adjacency: Dict[AtomId, set[AtomId]] = {}
        for result in self.api.search(
            predicate=canonical_predicate, atom_type=Predicate
        ):
            link = result.atom
            if len(link.args) != 2:
                continue
            left, right = link.args
            adjacency.setdefault(left, set()).add(right)
            if symmetric:
                adjacency.setdefault(right, set()).add(left)

        start, goal = wanted
        if not transitive:
            return goal in adjacency.get(start, set())

        pending = deque([start])
        seen = set()
        while pending:
            current = pending.popleft()
            if current in seen:
                continue
            seen.add(current)
            neighbors = adjacency.get(current, set())
            if goal in neighbors:
                return True
            pending.extend(neighbors - seen)
        return False

    create_link = create_predicate
    has_link = has_predicate


Canonicalize = Inverse
PredicateRules = RuleSet
SymmetricRule = Symmetric
TransitiveRule = Transitive
InverseRule = Inverse

__all__ = [
    "RuleSet", "PredicateRules", "Symmetric", "Transitive", "Inverse",
    "Canonicalize", "SymmetricRule", "TransitiveRule", "InverseRule",
]
