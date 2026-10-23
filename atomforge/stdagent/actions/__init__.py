"""Action verbs: what agents do with objects and to each other.

The stdagent verb family partitions by what fills the second slot:
``acts.Does`` takes an act term, and this module's verbs take the
rest of the world — objects, and (for ``Gives``) another agent.

- ``Use(agent, object)`` — the object as instrument: tools,
  machines-as-tools, vehicles.  You *use* ballet shoes and racecars;
  you do not ``Does`` them (``Does(agent, object)`` does not exist —
  Elena didn't *do* claw machine).
- ``Wears(agent, object)`` — the object is on the agent's body by its
  own designed body-interface: rings, plugs, cage, collar, clothing.
  What is merely fastened on by something else's stickiness is not
  worn — that state is relational's ``AffixedTo``; what is inside
  the body is relational's ``InsertedIn``.  (Relational's older
  spatial ``Wear`` is a different predicate in a different module;
  ``Wears`` here is the ruled agent verb, agent-first.)
- ``Play(agent, object)`` — engagement for its own sake: games,
  instruments played for pleasure, the claw machine.  The line
  against ``Use`` is purpose, not mechanics: the same machine is
  ``Play`` when the point is the playing.
- ``Gives(giver, recipient)`` — the directed frame between two
  agents, and the module's centerpiece.  A giving is not complete
  without *what* was given, so every ``Gives`` application carries
  exactly one **payload**: a ``Payload`` ligature from the
  application atom to an Act term (Robert gives Elena a massage —
  the act hangs off the frame) or to an Object (Robert gives Elena
  the ring).  The frame is the principle; the payload is the
  hanger.  A ``Gives`` write with no payload is refused before
  anything is written — there is no bare ``relate`` path for
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

Depends on Core, acts (act-term checks for payloads), and possession
(custody receipts).  Act payloads are exempt from custody: you
cannot hold a massage.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from weakref import WeakKeyDictionary

from ...atoms import AtomId, Ligature, Node, Predicate
from ...facade import AtomSpaceAPI
from ...infrastructure import InvalidAtomOperationError, UnknownAtomError
from ...rules.generic import RuleSet
from ..acts import install as install_acts
from ..possession import install as install_possession


_ACTION_SPECS = {
    "Use": ("agent", "object"),
    "Wears": ("agent", "object"),
    "Play": ("agent", "object"),
    "Gives": ("giver", "recipient"),
}

#: The ligature name carrying a Gives application's payload.
PAYLOAD_LIGATURE = "Payload"

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
        self.predicates: Dict[str, AtomId] = {}
        for name, roles in _ACTION_SPECS.items():
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
        return self.rules.create_predicate(
            predicate, agent, obj, label=label, confidence=confidence
        )

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

    # -- Gives: the directed frame ----------------------------------------------

    def give(
        self,
        giver: AtomId,
        recipient: AtomId,
        payload: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert ``Gives(giver, recipient)`` with its payload.

        ``payload`` is required and singular: an Act term node (the
        act given — a massage, a rimjob) or an Object node (the thing
        given — the ring).  It rides on the application atom as a
        ``Payload`` ligature.  Self-giving is refused, as is any
        payload that is not a Node (a category or an assertion is
        not something that can be given).
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
        application = self.rules.create_predicate(
            self.Gives, giver, recipient,
            label=label, confidence=confidence,
        )
        self.api.create_ligature(PAYLOAD_LIGATURE, application, payload)
        return application

    def _gives_application(self, atom_id: AtomId, role: str) -> Predicate:
        self._check_atom(atom_id, role)
        atom = self.api.get(atom_id)
        if not isinstance(atom, Predicate) or atom.predicate != self.Gives:
            raise TypeError(f"actions {role} is not a Gives application")
        return atom

    def payload_of(self, give_atom: AtomId) -> AtomId:
        """Return the one payload hanging off a ``Gives``
        application.  Anything but exactly one is a broken write and
        fails loud."""
        self._gives_application(give_atom, "give_atom")
        found: List[AtomId] = []
        for ligature_id in self.api.in_ligatures(give_atom):
            ligature = self.api.get(ligature_id)
            if isinstance(ligature, Ligature) \
                    and ligature.name == PAYLOAD_LIGATURE \
                    and len(ligature.args) == 2 \
                    and ligature.args[0] == give_atom:
                found.append(ligature.args[1])
        if len(found) != 1:
            raise InvalidAtomOperationError(
                f"Gives application {give_atom!r} carries "
                f"{len(found)} payloads; exactly one is required"
            )
        return found[0]

    def custody_receipt(self, give_atom: AtomId) -> AtomId:
        """Chain an object payload's custody change as a Transition
        receipt: ``Gives`` application → the recipient's ``Holds``
        atom over the payload.  Returns the Transition atom.  An act
        payload has no custody to receipt and is refused."""
        application = self._gives_application(give_atom, "give_atom")
        payload = self.payload_of(give_atom)
        if self.acts.is_act(payload):
            raise TypeError(
                "an act payload has no custody; custody receipts are "
                "for object payloads"
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
        requires a payload and exists only through :meth:`give`."""
        name = self._names.get(predicate)
        if name is None:
            raise TypeError("predicate is not part of the actions vocabulary")
        if name == "Gives":
            raise TypeError(
                "Gives requires a payload; assert it with give()"
            )
        return self._simple(
            predicate, left, right, label=label, confidence=confidence
        )

    create_predicate = relate
    create_link = relate

    def has(self, predicate: AtomId, left: AtomId, right: AtomId) -> bool:
        if predicate not in self._names:
            raise TypeError("predicate is not part of the actions vocabulary")
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
    "ActionVerbs", "Actions", "PAYLOAD_LIGATURE", "install",
    "install_action_verbs",
]
