"""Speech predicate vocabulary: who said what, as reified claim atoms.

Presupposes speakers — agents that utter propositions.  This is a
foundation stdagent module: other vocabularies (epistemic, obligation,
any domain with dialogue) build on the claim atoms minted here.

The one predicate is ``Says(speaker, claim)``.  It is deliberately the
weakest speech verb available: saying implies nothing about belief,
truth, or commitment.  People say things they do not believe, are
quoting, are role-playing, or are lying about; grading an utterance is
the epistemic module's job, not this one's.  Performative force, where
a domain needs it, likewise lives in that domain's own act predicates
(a promise is ``Promises``, not a stronger ``Says``).

A claim is any atom: a proposition asserted elsewhere in the graph, or
a piece of text.  Text claims are stored as ``Node`` atoms of kind
``Claim`` labeled with the text, minted through the normal store, so
the same text always resolves to the same claim atom and a bare
assertion of a proposition and a ``Says`` about that proposition meet
at one atom (Core predicate dedup handles proposition identity).

``Says`` reports; it does not decide who believed what was said.  No
``Believes`` atoms are created here for hearers — belief formation
belongs to whoever ingests or consolidates a graph.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union
from weakref import WeakKeyDictionary

from ...atoms import AtomId, Node, Predicate
from ...facade import AtomSpaceAPI
from ...infrastructure import InvalidAtomOperationError, UnknownAtomError
from ...rules.generic import RuleSet


_SPEECH_SPECS = {
    "Says": ("speaker", "claim"),
}

_INSTALLATIONS: "WeakKeyDictionary[AtomSpaceAPI, SpeechPredicates]" = (
    WeakKeyDictionary()
)


class SpeechPredicates:
    """Installed speech vocabulary bound to one :class:`AtomSpaceAPI`."""

    def __init__(self, api: AtomSpaceAPI) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self.api = api
        self.predicates: Dict[str, AtomId] = {}
        for name, roles in _SPEECH_SPECS.items():
            predicate = api.predicate(name, arity=2, roles=roles)
            self.predicates[name] = predicate
            setattr(self, name, predicate)
        self._names = {predicate: name for name, predicate in self.predicates.items()}
        self.claim_kind = api.kind("Claim")

        self.rules = RuleSet(api)

    def __getitem__(self, name: str) -> AtomId:
        return self.predicates[name]

    # -- claim atoms -------------------------------------------------------

    def claim_node(self, text: str) -> AtomId:
        """Return the claim atom for a piece of text, minting it if new.

        The same text always resolves to the same ``Claim`` node.
        """
        if not isinstance(text, str) or not text:
            raise TypeError("claim text must be a non-empty string")
        for atom_id in self.api.find_by_label(text):
            atom = self.api.get(atom_id)
            if isinstance(atom, Node) and atom.kind == self.claim_kind:
                return atom_id
        return self.api.create_node(text, kind=self.claim_kind)

    def _resolve_claim(self, content: Union[AtomId, str]) -> AtomId:
        if isinstance(content, str):
            return self.claim_node(content)
        self._check_atom(content, "claim")
        return content

    def _check_atom(self, atom_id: AtomId, role: str) -> None:
        """Preflight one argument: it must exist, be live, and be usable
        as a relationship argument (Core refuses Current assertions)."""
        try:
            raw = self.api.get_raw(atom_id)
        except UnknownAtomError:
            raise UnknownAtomError(
                f"Says {role} names unknown atom {atom_id!r}"
            ) from None
        if raw.deleted:
            raise UnknownAtomError(
                f"Says {role} names deleted atom {atom_id!r}"
            )
        atom = raw.atom
        if (
            isinstance(atom, Predicate)
            and atom.predicate == self.api.current_predicate
        ):
            raise InvalidAtomOperationError(
                f"Says {role} names a Current assertion, which cannot "
                "be a relationship argument"
            )

    # -- assertion ---------------------------------------------------------

    def say(
        self,
        speaker: AtomId,
        content: Union[AtomId, str],
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert ``Says(speaker, claim)`` and return the saying atom.

        ``content`` is a claim atom, a proposition atom, or text (which
        is resolved to its ``Claim`` node).  The returned atom is the
        handle other modules wrap: ``Knows(elena, offer)`` where
        ``offer`` is a ``Says`` atom is second-order knowledge about a
        specific utterance.
        """
        self._check_atom(speaker, "speaker")
        claim = self._resolve_claim(content)
        return self.rules.create_predicate(
            self.Says, speaker, claim, label=label, confidence=confidence
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
        """Assert one speech predicate (only ``Says`` exists here)."""
        if predicate != self.Says:
            raise TypeError("predicate is not part of the speech vocabulary")
        return self.say(left, right, label=label, confidence=confidence)

    create_predicate = relate
    create_link = relate

    def has(self, predicate: AtomId, left: AtomId, right: AtomId) -> bool:
        if predicate != self.Says:
            raise TypeError("predicate is not part of the speech vocabulary")
        return self.rules.has_predicate(predicate, left, right)

    has_predicate = has
    has_link = has

    # -- inspection ----------------------------------------------------------

    def _saying_parts(self, saying: AtomId) -> "tuple[AtomId, AtomId]":
        atom = self.api.get(saying)
        if not isinstance(atom, Predicate) or atom.predicate != self.Says:
            raise TypeError(f"atom {saying!r} is not a Says assertion")
        return atom.args

    def speaker_of(self, saying: AtomId) -> AtomId:
        """Return the speaker argument of a ``Says`` atom."""
        return self._saying_parts(saying)[0]

    def claim_of(self, saying: AtomId) -> AtomId:
        """Return the claim argument of a ``Says`` atom."""
        return self._saying_parts(saying)[1]

    def is_saying(self, atom_id: AtomId) -> bool:
        """Return whether ``atom_id`` is a live ``Says`` assertion."""
        atom = self.api.get(atom_id)
        return isinstance(atom, Predicate) and atom.predicate == self.Says

    def sayings_by(self, speaker: AtomId) -> List[AtomId]:
        """Return every ``Says`` atom asserted with this speaker."""
        found: List[AtomId] = []
        for result in self.api.search(predicate=self.Says):
            atom = result.atom
            if isinstance(atom, Predicate) and atom.args[0] == speaker:
                found.append(atom.id)
        return found

    def sayings_of(self, claim: AtomId) -> List[AtomId]:
        """Return every ``Says`` atom whose claim is ``claim``."""
        found: List[AtomId] = []
        for result in self.api.search(predicate=self.Says):
            atom = result.atom
            if isinstance(atom, Predicate) and atom.args[1] == claim:
                found.append(atom.id)
        return found


def install(api: AtomSpaceAPI) -> SpeechPredicates:
    """Install and return a speech vocabulary for ``api``."""
    installed = _INSTALLATIONS.get(api)
    if installed is None:
        installed = SpeechPredicates(api)
        _INSTALLATIONS[api] = installed
    return installed


install_speech_predicates = install
Speech = SpeechPredicates

__all__ = [
    "SpeechPredicates", "Speech", "install", "install_speech_predicates",
]
