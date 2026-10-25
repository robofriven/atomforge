"""Sex: the sex response predicates and the SexAct kind.

A domain vocabulary.  It presupposes agents with bodies — responses
happen to agents and land on body parts, objects, or persons — and
nothing else.  The class is closed and body-bounded, so its members
are individual predicates, each earning its place through the reuse
and selectivity gates; a response that has not graduated (trembling,
gasping) stays in the remembering layer's verses.

The predicates:

- ``EjaculatesOn(agent, target)`` — an external finish: the
  response lands on the target (a body part or an object).
- ``EjaculatesIn(agent, target)`` — an internal finish: the response
  lands inside the target (a body part or the person).  Internal
  finishes are a trackable, consent-relevant class of their own.
- ``SquirtsOn(agent, target)`` / ``SquirtsIn(agent, target)`` — the
  same On/In distinction, by symmetry with the Ejaculates pair.
- ``Orgasms(agent)`` — unary on purpose: an orgasm has no target,
  it doesn't land anywhere.  Simultaneity is two ``Orgasms`` atoms
  plus a relational ``Simultaneous`` link, never a term.

Responses are not claims (nobody *holds* a response) and not act
terms (a simultaneous orgasm is never a term).  Targets are
deliberately not kind-gated: bodies are named by ordinary nodes, and
the BodyPart kind is still an open question — response targets stay
ungated until it is ruled.

``SexAct`` is a real schema kind whose home is this module:
``IsA(SexAct, Act)`` at the kind level, so ``Does`` covers every sex
act by kind inheritance, and taxonomy below the kind level is IsA
among term nodes.  The kind *atom* itself is just a name, interned
through Core like any kind — ``api.kind("SexAct")`` — so the act
vocabulary factory in ``stdagent.acts`` keeps minting SexAct-kind
terms from the whole packaged vocabulary by kind name, without
importing this module.  This module asserts the kind-level IsA edge
lazily (see :meth:`SexPredicates.ensure_sex_act_kind`), matching the
factory's own laziness: merely installing a vocabulary must not
write taxonomy into a graph.  The factory's SexAct minting and this
module's kind home are two views of one kind, joined by the name.

Depends on Core and the relational vocabulary (kind closure for the
SexAct taxonomy).  ``stdagent`` never depends on this module.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from weakref import WeakKeyDictionary

from ...atoms import AtomId, Predicate
from ...facade import AtomSpaceAPI
from ...infrastructure import InvalidAtomOperationError, UnknownAtomError
from ...rules.generic import RuleSet
from ...stdagent.relational import install as install_relational


_SEX_SPECS = {
    "EjaculatesOn": (2, ("agent", "target")),
    "EjaculatesIn": (2, ("agent", "target")),
    "SquirtsOn": (2, ("agent", "target")),
    "SquirtsIn": (2, ("agent", "target")),
    "Orgasms": (1, ("agent",)),
}

_INSTALLATIONS: "WeakKeyDictionary[AtomSpaceAPI, SexPredicates]" = (
    WeakKeyDictionary()
)


class SexPredicates:
    """Installed sex vocabulary bound to one :class:`AtomSpaceAPI`."""

    def __init__(self, api: AtomSpaceAPI) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self.api = api
        self.predicates: Dict[str, AtomId] = {}
        for name, (arity, roles) in _SEX_SPECS.items():
            predicate = api.predicate(name, arity=arity, roles=roles)
            self.predicates[name] = predicate
            setattr(self, name, predicate)
        self._names = {predicate: name for name, predicate in self.predicates.items()}
        self.act_kind = api.kind("Act")
        self.sex_act_kind = api.kind("SexAct")
        self.relational = install_relational(api)

        self.rules = RuleSet(api)

    def __getitem__(self, name: str) -> AtomId:
        return self.predicates[name]

    # -- kind home -----------------------------------------------------------

    def ensure_sex_act_kind(self) -> None:
        """Assert ``IsA(SexAct, Act)`` at the kind level, once.

        Lazy on purpose, matching the act factory: merely installing
        this module must not write taxonomy into a graph.  The act
        factory asserts the same edge when it first mints a SexAct
        term; either path joins the kind to the Act hierarchy."""
        if not self.relational.has(
            self.relational.IsA, self.sex_act_kind, self.act_kind
        ):
            self.relational.relate(
                self.relational.IsA, self.sex_act_kind, self.act_kind
            )

    # -- preflight -----------------------------------------------------------

    def _check_atom(self, atom_id: AtomId, role: str) -> None:
        """Preflight one argument: it must exist, be live, and be usable
        as a relationship argument (Core refuses Current assertions)."""
        try:
            raw = self.api.get_raw(atom_id)
        except UnknownAtomError:
            raise UnknownAtomError(
                f"sex {role} names unknown atom {atom_id!r}"
            ) from None
        if raw.deleted:
            raise UnknownAtomError(
                f"sex {role} names deleted atom {atom_id!r}"
            )
        atom = raw.atom
        if (
            isinstance(atom, Predicate)
            and atom.predicate == self.api.current_predicate
        ):
            raise InvalidAtomOperationError(
                f"sex {role} names a Current assertion, which cannot "
                "be a relationship argument"
            )

    # -- assertion -----------------------------------------------------------

    def _respond(
        self,
        predicate: AtomId,
        agent: AtomId,
        target: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        self._check_atom(agent, "agent")
        self._check_atom(target, "target")
        return self.rules.create_predicate(
            predicate, agent, target, label=label, confidence=confidence
        )

    def ejaculates_on(
        self, agent: AtomId, target: AtomId, **kwargs
    ) -> AtomId:
        """Assert ``EjaculatesOn(agent, target)`` — target a body
        part or an object."""
        return self._respond(self.EjaculatesOn, agent, target, **kwargs)

    def ejaculates_in(
        self, agent: AtomId, target: AtomId, **kwargs
    ) -> AtomId:
        """Assert ``EjaculatesIn(agent, target)`` — the internal
        finish, a trackable class of its own (the creampie grants
        make it consent-relevant)."""
        return self._respond(self.EjaculatesIn, agent, target, **kwargs)

    def squirts_on(
        self, agent: AtomId, target: AtomId, **kwargs
    ) -> AtomId:
        """Assert ``SquirtsOn(agent, target)``."""
        return self._respond(self.SquirtsOn, agent, target, **kwargs)

    def squirts_in(
        self, agent: AtomId, target: AtomId, **kwargs
    ) -> AtomId:
        """Assert ``SquirtsIn(agent, target)``."""
        return self._respond(self.SquirtsIn, agent, target, **kwargs)

    def orgasms(
        self,
        agent: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert ``Orgasms(agent)``.  Unary on purpose: an orgasm
        has no target — it doesn't land anywhere.  Simultaneity is
        two of these atoms plus a relational ``Simultaneous`` link."""
        self._check_atom(agent, "agent")
        return self.rules.create_predicate(
            self.Orgasms, agent, label=label, confidence=confidence
        )

    def has_orgasm(self, agent: AtomId) -> bool:
        """Whether an ``Orgasms(agent)`` atom stands."""
        return self.api.has_predicate(self.Orgasms, agent)

    def relate(
        self,
        predicate: AtomId,
        left: AtomId,
        right: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert one binary sex predicate."""
        name = self._names.get(predicate)
        if name is None:
            raise TypeError("predicate is not part of the sex vocabulary")
        if name == "Orgasms":
            raise TypeError(
                "Orgasms is unary; assert it with orgasms()"
            )
        self._check_atom(left, "left")
        self._check_atom(right, "right")
        return self.rules.create_predicate(
            predicate, left, right, label=label, confidence=confidence
        )

    create_predicate = relate
    create_link = relate

    def has(self, predicate: AtomId, left: AtomId, right: AtomId) -> bool:
        name = self._names.get(predicate)
        if name is None:
            raise TypeError("predicate is not part of the sex vocabulary")
        if name == "Orgasms":
            raise TypeError(
                "Orgasms is unary; query it with has_orgasm()"
            )
        return self.rules.has_predicate(predicate, left, right)

    has_predicate = has
    has_link = has


def install(api: AtomSpaceAPI) -> SexPredicates:
    """Install and return a sex vocabulary for ``api``."""
    installed = _INSTALLATIONS.get(api)
    if installed is not None:
        return installed
    installed = SexPredicates(api)
    _INSTALLATIONS[api] = installed
    return installed


install_sex_predicates = install
Sex = SexPredicates

__all__ = [
    "SexPredicates", "Sex", "install", "install_sex_predicates",
]
