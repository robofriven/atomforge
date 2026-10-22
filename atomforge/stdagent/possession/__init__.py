"""Possession predicate vocabulary: title and custody are separate axes.

Presupposes holders — agents (and institutions) that can own things
and hold things.  The settled position this module encodes: ``Has``
was retired because it smuggled at least five relations under one
name, and its legitimate possession slice splits in two, because
having and owning are not the same relation:

- ``Own(owner, item)`` — title.  The owner holds the rights in the
  item, whether or not they physically have it.  A landlord Owns the
  rented-out house the whole time the tenant lives in it.
- ``Holds(holder, item)`` — custody.  The holder physically has the
  item, whether or not it is theirs.  A tenant Holds the apartment; a
  borrower Holds the book.

PROVISIONAL NAME: ``Holds`` for the custody predicate is the
assistant's choice, not Robert's — the custody axis was approved but
its predicate name was never pinned.  It is marked here so it can be
vetoed or renamed cheaply: a rename touches this module's spec table
and its tests, nothing else, because every other module refers to
custody only through composition (below), never by name.

Composition, not machinery, covers the compound cases:

- A lease is custody plus agreement: ``Holds(tenant, apartment)``
  alongside obligation's ``AgreesTo(tenant, terms, proposal=lease)``.
- Borrowing is custody plus a promise to return: ``Holds(borrower,
  book)`` alongside obligation's ``Promises(borrower, return,
  promisee=owner)``.

This module deliberately records no inference between the axes:
``Own`` does not imply ``Holds``, ``Holds`` does not imply ``Own``,
and no ``has()`` answer crosses from one to the other.  Whether the
owner also holds a thing is a fact to assert, not a default to assume.

Depends on Core only.  The composition examples are exercised against
the obligation module in this module's tests; obligation does not
depend on this module.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from weakref import WeakKeyDictionary

from ...atoms import AtomId, Predicate
from ...facade import AtomSpaceAPI
from ...infrastructure import InvalidAtomOperationError, UnknownAtomError
from ...rules.generic import RuleSet


_POSSESSION_SPECS = {
    "Own": ("owner", "item"),
    "Holds": ("holder", "item"),
}

_INSTALLATIONS: "WeakKeyDictionary[AtomSpaceAPI, PossessionPredicates]" = (
    WeakKeyDictionary()
)


class PossessionPredicates:
    """Installed possession vocabulary bound to one :class:`AtomSpaceAPI`."""

    def __init__(self, api: AtomSpaceAPI) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self.api = api
        self.predicates: Dict[str, AtomId] = {}
        for name, roles in _POSSESSION_SPECS.items():
            predicate = api.predicate(name, arity=2, roles=roles)
            self.predicates[name] = predicate
            setattr(self, name, predicate)
        self._names = {predicate: name for name, predicate in self.predicates.items()}

        self.rules = RuleSet(api)

    def __getitem__(self, name: str) -> AtomId:
        return self.predicates[name]

    # -- preflight -----------------------------------------------------------

    def _check_atom(self, atom_id: AtomId, role: str) -> None:
        """Preflight one argument: it must exist, be live, and be usable
        as a relationship argument (Core refuses Current assertions)."""
        try:
            raw = self.api.get_raw(atom_id)
        except UnknownAtomError:
            raise UnknownAtomError(
                f"possession {role} names unknown atom {atom_id!r}"
            ) from None
        if raw.deleted:
            raise UnknownAtomError(
                f"possession {role} names deleted atom {atom_id!r}"
            )
        atom = raw.atom
        if (
            isinstance(atom, Predicate)
            and atom.predicate == self.api.current_predicate
        ):
            raise InvalidAtomOperationError(
                f"possession {role} names a Current assertion, which "
                "cannot be a relationship argument"
            )

    # -- assertion -----------------------------------------------------------

    def own(
        self,
        owner: AtomId,
        item: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert ``Own(owner, item)``: title, regardless of custody."""
        self._check_atom(owner, "owner")
        self._check_atom(item, "item")
        return self.rules.create_predicate(
            self.Own, owner, item, label=label, confidence=confidence
        )

    def hold(
        self,
        holder: AtomId,
        item: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert ``Holds(holder, item)``: custody, regardless of title."""
        self._check_atom(holder, "holder")
        self._check_atom(item, "item")
        return self.rules.create_predicate(
            self.Holds, holder, item, label=label, confidence=confidence
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
        """Assert one possession predicate (``Own`` or ``Holds``)."""
        name = self._names.get(predicate)
        if name is None:
            raise TypeError("predicate is not part of the possession vocabulary")
        if name == "Own":
            return self.own(left, right, label=label, confidence=confidence)
        return self.hold(left, right, label=label, confidence=confidence)

    create_predicate = relate
    create_link = relate

    def has(self, predicate: AtomId, left: AtomId, right: AtomId) -> bool:
        if predicate not in self._names:
            raise TypeError("predicate is not part of the possession vocabulary")
        return self.rules.has_predicate(predicate, left, right)

    has_predicate = has
    has_link = has

    # -- inspection ------------------------------------------------------------

    def _sweep(self, predicate: AtomId, index: int, match: AtomId) -> List[AtomId]:
        found: List[AtomId] = []
        for result in self.api.search(predicate=predicate):
            atom = result.atom
            if isinstance(atom, Predicate) and atom.args[index] == match:
                found.append(atom.args[1 - index])
        return found

    def owned_by(self, owner: AtomId) -> List[AtomId]:
        """Return every item this owner holds title to."""
        return self._sweep(self.Own, 0, owner)

    def owners_of(self, item: AtomId) -> List[AtomId]:
        """Return every owner holding title to this item."""
        return self._sweep(self.Own, 1, item)

    def held_by(self, holder: AtomId) -> List[AtomId]:
        """Return every item in this holder's custody."""
        return self._sweep(self.Holds, 0, holder)

    def holders_of(self, item: AtomId) -> List[AtomId]:
        """Return every holder with custody of this item."""
        return self._sweep(self.Holds, 1, item)


def install(api: AtomSpaceAPI) -> PossessionPredicates:
    """Install and return a possession vocabulary for ``api``."""
    installed = _INSTALLATIONS.get(api)
    if installed is None:
        installed = PossessionPredicates(api)
        _INSTALLATIONS[api] = installed
    return installed


install_possession_predicates = install
Possession = PossessionPredicates

__all__ = [
    "PossessionPredicates", "Possession", "install",
    "install_possession_predicates",
]
