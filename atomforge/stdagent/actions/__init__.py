"""Action verbs: what agents do with objects and to each other.

The stdagent verb family partitions by what fills the second slot:
``acts.Does`` takes an act term, and this module's verbs take the
rest of the world — objects, and (for ``Gives``) another agent.

- ``Use(agent, object)`` — the object as instrument: tools,
  machines-as-tools, vehicles.  You *use* ballet shoes and racecars;
  you do not ``Does`` them (``Does(agent, object)`` does not exist —
  Elena didn't *do* claw machine).
- ``Wears(agent, object)`` — the object is on the agent's body by its
  own designed body-interface: rings, cage, collar, clothing.
  What is merely fastened on by something else's stickiness is not
  worn — that state is relational's ``AffixedTo``; what is inside
  the body is relational's ``InsertedIn``.  (Relational's older
  spatial ``Wear`` is a different predicate in a different module;
  ``Wears`` here is the ruled agent verb, agent-first.)
- ``Play(agent, object)`` — engagement for its own sake: games,
  instruments played for pleasure, the claw machine.  The line
  against ``Use`` is purpose, not mechanics: the same machine is
  ``Play`` when the point is the playing.
- ``Gives(giver, recipient, payload)`` — the directed frame
  between two agents, and the module's centerpiece.  A giving is
  not complete without *what* was given, so the payload is the
  third argument: an Act term (Robert gives Elena a massage) or
  an Object (Robert gives Elena the ring).  The frame is the
  principle — the recipient stays in the atom, not hung off it —
  and arity is what carries the payload: ``Gives`` is ternary,
  because a giving has three roles and binary-only forced the
  payload into a ligature hanger, where two payloads on one pair
  corrupted one frame.  There is no bare ``relate`` path for
  ``Gives``, only :meth:`ActionVerbs.give` — and giving to oneself
  is refused outright.  For an object payload,
  :meth:`ActionVerbs.custody_receipt` chains the custody change as
  a Transition receipt: the ``Gives`` atom transitions to the
  recipient's ``Holds`` atom (possession's custody axis), so the
  transfer's bookkeeping has the same receipts discipline as every
  other state change in the system.

A scene's activity is a composition across this family and ``acts``:
its ``Does`` + ``Use`` + ``Wears`` + ``Play`` + ``Gives`` atoms.  No
single label carries a whole scene.

The kind these verbs range over is ``Object``, and this module is
its registrar: :meth:`ActionVerbs.object_node` mints object atoms —
label in, deduplicated ``Object`` node out, exactly the
``feeling_node`` pattern from the feels module.  Minting is NOT
vocabulary-gated: any thing may exist as an instance, because schema
closure governs kinds and predicates, not instances.  Validation,
by contrast, is kind-gated throughout, and IsA-aware (a node under
a subkind of ``Object`` validates everywhere an object does):
``Use`` / ``Wears`` / ``Play`` refuse a second argument that is not
an Object node, and a ``Gives`` payload must be an Act term or an
Object node.  Before this kind was registered, the payload check
could only insist on *a* Node — a person was as acceptable a
payload as a ring.

Depends on Core, acts (act-term checks for payloads), relational
(kind checks), and possession (custody receipts).  Act payloads are
exempt from custody: you cannot hold a massage.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from weakref import WeakKeyDictionary

from ...atoms import AtomId, Node, Predicate
from ...facade import AtomSpaceAPI
from ...infrastructure import InvalidAtomOperationError, UnknownAtomError
from ...rules.generic import RuleSet
from ..acts import install as install_acts
from ..possession import install as install_possession
from ..relational import install as install_relational


# name -> (arity, roles). Arity is per-predicate and declared:
# binary-only is retired — Gives is ternary because a giving has
# three roles (giver, recipient, payload).
_ACTION_SPECS = {
    "Use": (2, ("agent", "object")),
    "Wears": (2, ("agent", "object")),
    "Play": (2, ("agent", "object")),
    "Gives": (3, ("giver", "recipient", "payload")),
}

_INSTALLATIONS: "WeakKeyDictionary[AtomSpaceAPI, ActionVerbs]" = (
    WeakKeyDictionary()
)


class ActionVerbs:
    """Installed action-verb vocabulary bound to one AtomSpaceAPI."""

    def __init__(self, api: AtomSpaceAPI) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self.api = api
        self.acts = install_acts(api)
        self.relational = install_relational(api)
        self.object_kind = api.kind("Object")
        self.predicates: Dict[str, AtomId] = {}
        for name, (arity, roles) in _ACTION_SPECS.items():
            predicate = api.predicate(name, arity=arity, roles=roles)
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
                f"actions {role} names unknown atom {atom_id!r}"
            ) from None
        if raw.deleted:
            raise UnknownAtomError(
                f"actions {role} names deleted atom {atom_id!r}"
            )
        atom = raw.atom
        if (
            isinstance(atom, Predicate)
            and atom.predicate == self.api.current_predicate
        ):
            raise InvalidAtomOperationError(
                f"actions {role} names a Current assertion, which "
                "cannot be a relationship argument"
            )

    def _check_object(self, obj: AtomId, role: str = "object") -> None:
        """Kind-gate one object argument: it must be an ``Object``
        node — or a node under a subkind of Object (the check is
        IsA-aware, as everywhere in stdagent)."""
        if not self.relational.kind_is_a(obj, self.object_kind):
            raise TypeError(
                f"actions {role} must be an Object node; mint one "
                "with object_node()"
            )

    def _simple(
        self,
        predicate: AtomId,
        agent: AtomId,
        obj: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        self._check_atom(agent, "agent")
        self._check_atom(obj, "object")
        self._check_object(obj)
        return self.rules.create_predicate(
            predicate, agent, obj, label=label, confidence=confidence
        )

    # -- object atoms ----------------------------------------------------------

    def object_node(self, label: str) -> AtomId:
        """Return the object atom for a label, minting it if new.

        The same label always resolves to the same ``Object`` node.
        The label is used exactly as given and is never normalized.
        Unlike ``act_node``, minting is not vocabulary-gated: objects
        are instances, and any thing may exist — schema closure
        governs kinds and predicates, not instances.
        """
        if not isinstance(label, str) or not label:
            raise TypeError("object label must be a non-empty string")
        for atom_id in self.api.find_by_label(label):
            if self.relational.kind_is_a(atom_id, self.object_kind):
                return atom_id
        return self.api.create_node(label, kind=self.object_kind)

    def is_object(self, atom_id: AtomId) -> bool:
        """Return whether ``atom_id`` is a live ``Object`` node — or
        a node under a subkind of Object in the IsA hierarchy."""
        return self.relational.kind_is_a(atom_id, self.object_kind)

    # -- object verbs ----------------------------------------------------------

    def use(
        self, agent: AtomId, obj: AtomId, **kwargs
    ) -> AtomId:
        """Assert ``Use(agent, object)``: the object as instrument."""
        return self._simple(self.Use, agent, obj, **kwargs)

    def wears(
        self, agent: AtomId, obj: AtomId, **kwargs
    ) -> AtomId:
        """Assert ``Wears(agent, object)``: on the body by the
        object's own designed interface."""
        return self._simple(self.Wears, agent, obj, **kwargs)

    def play(
        self, agent: AtomId, obj: AtomId, **kwargs
    ) -> AtomId:
        """Assert ``Play(agent, object)``: engagement for its own
        sake — a game, an instrument, the claw machine."""
        return self._simple(self.Play, agent, obj, **kwargs)

    # -- Gives: the directed frame, ternary -------------------------------

    def give(
        self,
        giver: AtomId,
        recipient: AtomId,
        payload: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert ``Gives(giver, recipient, payload)``.

        ``payload`` is required: an Act term node (the act given —
        a massage, a rimjob) or an Object node (the thing given —
        the ring).  It is the third argument, not a hanger:
        Core dedups on (predicate, args), so distinct payloads on
        one pair separate naturally and same-payload repeats still
        unify into one atom with grounding occurrences.  Self-giving
        is refused, as is any payload that is not a Node (a category
        or an assertion is not something that can be given), and any
        Node that is neither an Act term nor an Object — a person is
        not a payload.
        """
        if giver == recipient:
            raise TypeError("Gives cannot relate an agent to itself")
        self._check_atom(giver, "giver")
        self._check_atom(recipient, "recipient")
        self._check_atom(payload, "payload")
        if not isinstance(self.api.get(payload), Node):
            raise TypeError(
                "Gives payload must be a Node: an Act term or an Object"
            )
        if not self.acts.is_act(payload) \
                and not self.is_object(payload):
            raise TypeError(
                "Gives payload must be an Act term or an Object node; "
                "mint objects with object_node()"
            )
        return self.rules.create_predicate(
            self.Gives, giver, recipient, payload,
            label=label, confidence=confidence,
        )

    def _gives_application(self, atom_id: AtomId, role: str) -> Predicate:
        self._check_atom(atom_id, role)
        atom = self.api.get(atom_id)
        if not isinstance(atom, Predicate) or atom.predicate != self.Gives:
            raise TypeError(f"actions {role} is not a Gives application")
        if len(atom.args) != 3:
            raise TypeError(
                f"actions {role} is not a ternary Gives application"
            )
        return atom

    def custody_receipt(self, give_atom: AtomId) -> AtomId:
        """Chain an object payload's custody change as a Transition
        receipt: ``Gives`` application → the recipient's ``Holds``
        atom over the payload.  Returns the Transition atom.  An act
        payload has no custody to receipt and is refused."""
        application = self._gives_application(give_atom, "give_atom")
        payload = application.args[2]
        if self.acts.is_act(payload):
            raise TypeError(
                "an act payload has no custody; custody receipts are "
                "for object payloads"
            )
        if not self.is_object(payload):
            raise TypeError(
                "custody receipts are for Object payloads"
            )
        recipient = application.args[1]
        possession = install_possession(self.api)
        holds = possession.hold(recipient, payload)
        return self.api.transition(give_atom, holds)

    # -- generic paths ------------------------------------------------------------

    def relate(
        self,
        predicate: AtomId,
        left: AtomId,
        right: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert one action verb.  ``Gives`` is refused here: it
        is ternary and exists only through :meth:`give`."""
        name = self._names.get(predicate)
        if name is None:
            raise TypeError("predicate is not part of the actions vocabulary")
        if name == "Gives":
            raise TypeError(
                "Gives is ternary; assert it with give()"
            )
        return self._simple(
            predicate, left, right, label=label, confidence=confidence
        )

    create_predicate = relate
    create_link = relate

    def has(self, predicate: AtomId, left: AtomId, right: AtomId) -> bool:
        if predicate not in self._names:
            raise TypeError("predicate is not part of the actions vocabulary")
        if self._names[predicate] == "Gives":
            # A two-argument check cannot express a ternary giving;
            # a silent False would lie. Check the ternary application
            # directly (givings_from / givings_to plus args).
            raise TypeError(
                "Gives is ternary; assert it with give() and inspect "
                "givings_from / givings_to"
            )
        return self.rules.has_predicate(predicate, left, right)

    has_predicate = has
    has_link = has

    # -- inspection ------------------------------------------------------------

    def _sweep(self, predicate: AtomId, index: int, match: AtomId) -> List[AtomId]:
        found: List[AtomId] = []
        for result in self.api.search(predicate=predicate):
            atom = result.atom
            if isinstance(atom, Predicate) and atom.args[index] == match:
                found.append(atom.id)
        return found

    def givings_from(self, giver: AtomId) -> List[AtomId]:
        """Return every ``Gives`` application atom with this giver."""
        return self._sweep(self.Gives, 0, giver)

    def givings_to(self, recipient: AtomId) -> List[AtomId]:
        """Return every ``Gives`` application atom with this recipient."""
        return self._sweep(self.Gives, 1, recipient)


def install(api: AtomSpaceAPI) -> ActionVerbs:
    """Install and return an action-verb vocabulary for ``api``."""
    installed = _INSTALLATIONS.get(api)
    if installed is None:
        installed = ActionVerbs(api)
        _INSTALLATIONS[api] = installed
    return installed


install_action_verbs = install
Actions = ActionVerbs

__all__ = [
    "ActionVerbs", "Actions", "install",
    "install_action_verbs",
]
