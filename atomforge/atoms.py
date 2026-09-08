"""Immutable data shapes for AtomForge's single AtomId space.

Node is a thing. Predicate is a predicate-backed, globally indexed relationship.
Transition is a Core-owned binary state-change relationship. Ligature is a
named semantic relationship discovered through topology.
KindAtom defines Node categories, and PredicateAtom defines Predicate forms.
Enforcement, storage, and indexing belong to Core.
"""

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
    """A canonical category that may be referenced by ``Node.kind``."""

    pass


@dataclass(frozen=True, slots=True)
class PredicateAtom(Atom):
    """The structural form of stored ``Predicate`` applications.

    arity:
      - >= 0 means fixed-arity
      - -1 means variadic (n-ary)

    roles:
      - OPTIONAL, descriptive labels for argument positions (slot names).
      - Do not need to be unique.
      - For variadic predicates, roles can be used as a prefix:
          roles=("head","member") -> slot0=head; slot>=1 repeats "member"
    """

    arity: int = -1
    roles: Tuple[Role, ...] = field(default_factory=tuple)
    template: Optional[str] = None

    # Structural constraints (safe to keep here; enforcement belongs in AtomSpace)
    anti_reflexive: bool = False  # disallow repeated args (when enforced)
    acyclic: bool = False  # disallow cycles for binary Predicates (when enforced)

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


@dataclass(frozen=True, slots=True, kw_only=True)
class Node(Atom):
    """A thing with a required ``KindAtom`` reference and immutable properties."""

    kind: AtomId
    props: Tuple[Tuple[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Predicate(Atom):
    """An application of a PredicateAtom to ordered AtomId arguments."""

    predicate: AtomId = 0
    args: Tuple[AtomId, ...] = field(default_factory=tuple)

    @property
    def arity(self) -> int:
        return len(self.args)


# Transitional source-compatibility name. Stored type information and public
# terminology use Predicate.
Link = Predicate


@dataclass(frozen=True, slots=True)
class Transition(Atom):
    """A Core-owned state change directly connecting ``before`` to ``after``."""

    args: Tuple[AtomId, AtomId] = (0, 0)

    @property
    def arity(self) -> int:
        return len(self.args)

    @property
    def before(self) -> AtomId:
        return self.args[0]

    @property
    def after(self) -> AtomId:
        return self.args[1]


@dataclass(frozen=True, slots=True)
class Ligature(Atom):
    """A named semantic relationship reached only through graph topology.

    Its name belongs to this relationship atom. It has no PredicateAtom and no
    global relation-type index.
    """

    name: str = ""
    args: Tuple[AtomId, ...] = field(default_factory=tuple)

    @property
    def arity(self) -> int:
        return len(self.args)


@dataclass(frozen=True, slots=True)
class RawAtomResult:
    atom: Atom
    atom_id: AtomId
    confidence: float
    deleted: bool
    depth: int = 0


@dataclass(frozen=True, slots=True)
class SearchResult:
    atom: Atom
    matched_id: AtomId


@dataclass(frozen=True, slots=True)
class TraversalResult:
    atom: Atom
    matched_id: AtomId
    depth: int = 0


@dataclass
class Intersection:
    atom_id: AtomId
    seeds: set[AtomId]
    depths: dict[AtomId, int]


@dataclass(frozen=True, slots=True)
class StructuralSearchResult:
    atom_id: AtomId
    depth: int
