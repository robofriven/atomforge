"""Act predicate vocabulary: acts as canonical atoms, not predicates.

Presupposes actors — agents that do things.  Act types are unbounded
vocabulary, like feelings: minting one predicate per act
(``Hugs``, ``ProposesTo``, ``DrivesTo``, ...) is the over-predicating
smell the feels module was built to avoid, with the same cure:

- An act type is a ``Node`` atom of kind ``Act``, minted on demand
  through :meth:`ActPredicates.act_node` — text in, deduplicated node
  out.  The same text always resolves to the same act atom: one
  canonical node per act type, however many occurrences point at it.
- The one mechanism predicate is ``Does(actor, act)``.

Occurrence counting and situated detail follow the canonical-act
pattern: an act node's occurrences are the ``Does`` atoms pointing at
it, and per-occurrence detail (duration, participants, manner) hangs
off the occurrence's evidence, not off new predicates on the act type.
The act node itself stays timeless: what the act *is*, never when one
instance of it happened.

Domain vocabularies that need to say things *about* act types —
consent is the standing example — take act nodes as arguments to their
own predicates; they do not subclass or extend this module.  This
module knows nothing about permission, preference, or obligation: a
``Does`` atom records that an actor does (or did, or characteristically
does) an act, and nothing about whether anyone wanted it done.

Minting discipline mirrors the feels module: callers match first
against existing act nodes and name a new act so the name is
self-describing.  The library never normalizes or merges act names.

Depends on Core only.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union
from weakref import WeakKeyDictionary

from ...atoms import AtomId, Node, Predicate
from ...facade import AtomSpaceAPI
from ...infrastructure import InvalidAtomOperationError, UnknownAtomError
from ...rules.generic import RuleSet


_ACT_SPECS = {
    "Does": ("actor", "act"),
}

_INSTALLATIONS: "WeakKeyDictionary[AtomSpaceAPI, ActPredicates]" = (
    WeakKeyDictionary()
)


class ActPredicates:
    """Installed act vocabulary bound to one :class:`AtomSpaceAPI`."""

    def __init__(self, api: AtomSpaceAPI) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self.api = api
        self.predicates: Dict[str, AtomId] = {}
        for name, roles in _ACT_SPECS.items():
            predicate = api.predicate(name, arity=2, roles=roles)
            self.predicates[name] = predicate
            setattr(self, name, predicate)
        self._names = {predicate: name for name, predicate in self.predicates.items()}
        self.act_kind = api.kind("Act")

        self.rules = RuleSet(api)

    def __getitem__(self, name: str) -> AtomId:
        return self.predicates[name]

    # -- act atoms -------------------------------------------------------------

    def act_node(self, text: str) -> AtomId:
        """Return the act atom for a piece of text, minting it if new.

        The same text always resolves to the same ``Act`` node.  The
        text is used exactly as given and is never normalized.
        """
        if not isinstance(text, str) or not text:
            raise TypeError("act text must be a non-empty string")
        for atom_id in self.api.find_by_label(text):
            atom = self.api.get(atom_id)
            if isinstance(atom, Node) and atom.kind == self.act_kind:
                return atom_id
        return self.api.create_node(text, kind=self.act_kind)

    def is_act(self, atom_id: AtomId) -> bool:
        """Return whether ``atom_id`` is a live ``Act`` node."""
        atom = self.api.get(atom_id)
        return isinstance(atom, Node) and atom.kind == self.act_kind

    def _resolve_act(self, act: Union[AtomId, str]) -> AtomId:
        if isinstance(act, str):
            return self.act_node(act)
        self._check_atom(act, "act")
        atom = self.api.get(act)
        if not (isinstance(atom, Node) and atom.kind == self.act_kind):
            raise TypeError(
                "Does target must be an Act node; mint one with act_node()"
            )
        return act

    def _check_atom(self, atom_id: AtomId, role: str) -> None:
        """Preflight one argument: it must exist, be live, and be usable
        as a relationship argument (Core refuses Current assertions)."""
        try:
            raw = self.api.get_raw(atom_id)
        except UnknownAtomError:
            raise UnknownAtomError(
                f"acts {role} names unknown atom {atom_id!r}"
            ) from None
        if raw.deleted:
            raise UnknownAtomError(
                f"acts {role} names deleted atom {atom_id!r}"
            )
        atom = raw.atom
        if (
            isinstance(atom, Predicate)
            and atom.predicate == self.api.current_predicate
        ):
            raise InvalidAtomOperationError(
                f"acts {role} names a Current assertion, which cannot "
                "be a relationship argument"
            )

    # -- assertion -------------------------------------------------------------

    def do(
        self,
        actor: AtomId,
        act: Union[AtomId, str],
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert ``Does(actor, act)`` and return the atom.

        ``act`` is an ``Act`` node, or text (which is resolved to its
        ``Act`` node through :meth:`act_node`).
        """
        self._check_atom(actor, "actor")
        act_id = self._resolve_act(act)
        return self.rules.create_predicate(
            self.Does, actor, act_id, label=label, confidence=confidence
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
        """Assert one act predicate (only ``Does`` exists here)."""
        if predicate != self.Does:
            raise TypeError("predicate is not part of the act vocabulary")
        return self.do(left, right, label=label, confidence=confidence)

    create_predicate = relate
    create_link = relate

    def has(self, predicate: AtomId, left: AtomId, right: AtomId) -> bool:
        if predicate != self.Does:
            raise TypeError("predicate is not part of the act vocabulary")
        return self.rules.has_predicate(predicate, left, right)

    has_predicate = has
    has_link = has

    # -- inspection --------------------------------------------------------------

    def acts_of(self, actor: AtomId) -> List[AtomId]:
        """Return the act nodes this actor has ``Does`` atoms on."""
        found: List[AtomId] = []
        for result in self.api.search(predicate=self.Does):
            atom = result.atom
            if isinstance(atom, Predicate) and atom.args[0] == actor \
                    and atom.args[1] not in found:
                found.append(atom.args[1])
        return found

    def occurrences(self, act: AtomId) -> List[AtomId]:
        """Return every ``Does`` atom pointing at this act node."""
        found: List[AtomId] = []
        for result in self.api.search(predicate=self.Does):
            atom = result.atom
            if isinstance(atom, Predicate) and atom.args[1] == act:
                found.append(atom.id)
        return found

    def actors_of(self, act: AtomId) -> List[AtomId]:
        """Return every actor with a ``Does`` atom on this act."""
        found: List[AtomId] = []
        for result in self.api.search(predicate=self.Does):
            atom = result.atom
            if isinstance(atom, Predicate) and atom.args[1] == act \
                    and atom.args[0] not in found:
                found.append(atom.args[0])
        return found


def install(api: AtomSpaceAPI) -> ActPredicates:
    """Install and return an act vocabulary for ``api``."""
    installed = _INSTALLATIONS.get(api)
    if installed is None:
        installed = ActPredicates(api)
        _INSTALLATIONS[api] = installed
    return installed


install_act_predicates = install
Acts = ActPredicates

__all__ = [
    "ActPredicates", "Acts", "install", "install_act_predicates",
]
