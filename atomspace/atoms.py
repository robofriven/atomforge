# atoms.py
# Core atom definitions (no AtomSpace here).
#
# One ID space. Everything is an Atom:
#   - Nodes are atoms
#   - Links (statements) are atoms
#   - KindAtoms (node categories) are atoms
#   - PredicateAtoms (statement forms) are atoms
#
# This file defines data shapes only. Enforcement/validation belongs in AtomSpace.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

AtomId = int
Role = str  # descriptive slot label (NOT a type system)


@dataclass(frozen=True, slots=True)
class Atom:
    """Base identity. label is for humans/debugging; it is not identity."""

    id: AtomId
    label: Optional[str] = None
    created_at_utc: str = ""  # ISO-8601, e.g. "2026-02-02T01:23:45Z"


@dataclass(frozen=True, slots=True)
class KindAtom(Atom):
    """
    Canonical kind/category for nodes (Entity, Class, TimeInstant, Proposition, ...).
    Still "just an atom". AtomSpace decides how (or if) to enforce.
    """

    pass


@dataclass(frozen=True, slots=True)
class PredicateAtom(Atom):
    """
    The 'idea of a relationship': IsA, HasA, Wants, Believes, Not, Because...

    arity:
      - >= 0 means fixed-arity
      - -1 means variadic (n-ary)

    roles:
      - OPTIONAL, descriptive labels for argument positions (slot names).
      - Do NOT need to be unique. Example: Between could use ("thing","thing","thing").
      - For variadic predicates, roles can be used as a prefix:
          Because(conclusion, e1, e2, e3...)
          roles=("conclusion","evidence") -> slot0=conclusion; slot>=1 repeats "evidence"
    """

    arity: int = -1
    roles: Tuple[Role, ...] = field(default_factory=tuple)

    # Structural constraints (safe to keep here; enforcement belongs in AtomSpace)
    anti_reflexive: bool = False  # disallow repeated args (when enforced)
    acyclic: bool = False  # disallow cycles (typically for IsA/PartOf) (when enforced)

    def check_arity(self, n_args: int) -> None:
        if self.arity != -1 and n_args != self.arity:
            raise TypeError(
                f"{self.label or 'Predicate'} expects arity {self.arity}, got {n_args}"
            )

    def role_for_index(self, i: int) -> Optional[Role]:
        """
        Descriptive role label for argument position i, if any.

        Behavior:
          - roles empty -> None
          - i < len(roles) -> roles[i]
          - variadic and i >= len(roles) -> repeat last role
          - fixed-arity and i >= len(roles) -> None (partial role annotations)
        """
        if not self.roles:
            return None
        if i < len(self.roles):
            return self.roles[i]
        if self.arity == -1:
            return self.roles[-1]
        return None


@dataclass(frozen=True, slots=True)
class Node(Atom):
    """
    A 'thing' in the graph (Greg, Potato, Tuesday).
    kind points to a KindAtom.
    props is optional metadata; keep it immutable (tuple) for hashability.
    """

    kind: AtomId = 0
    props: Tuple[Tuple[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Link(Atom):
    """
    A statement/hyperedge: predicate(args...)
    predicate points to a PredicateAtom.
    args can be any atoms (nodes, links, predicates, kinds... everything is an atom).
    """

    predicate: AtomId = 0
    args: Tuple[AtomId, ...] = field(default_factory=tuple)

    @property
    def arity(self) -> int:
        return len(self.args)
