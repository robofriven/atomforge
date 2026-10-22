"""Feels predicate vocabulary: feelings as canonical atoms, not predicates.

Presupposes feelers — agents that hold emotional states.  A feeling is
unbounded vocabulary: there is no closed list of emotions a graph will
ever need, so minting one predicate per feeling (``FeelsAfraid``,
``FeelsInsecure``, ``FeelsTiredAndHungry``, ...) is over-predicating —
a new predicate for every shade, each with its own nearly-empty index.
This module takes the other shape:

- A feeling is a ``Node`` atom of kind ``Feeling``, minted on demand
  through :meth:`FeelsPredicates.feeling_node`, exactly the
  ``claim_node`` pattern from the speech module: text in,
  deduplicated node out.  The same text always resolves to the same
  feeling atom, so one canonical node per emotion accumulates every
  occurrence — a feeling's history is the walk of ``Feels`` atoms
  pointing at it.
- The one stance predicate is ``Feels(holder, feeling)``.
- Aboutness hangs off the feeling atom, not off the holder:
  ``Because(feeling, claim)`` points a feeling at what it is about —
  the claim it is afraid of, the event it is glad about.  This is
  what dissolves the old Feels/Fears split: a fear is a feeling node
  whose ``Because`` points at the feared claim.

``Because(subject, ground)`` is introduced here because feelings are
its first customer, but it is a generic stdagent predicate, not a
feels-private one: it states why something holds or came to be — the
reason relation.  Obligation-style grounds (why an ``Obligated``
assertion binds) are the same shape and belong on ``Because`` too.
It is deliberately distinct from ``EvidenceFor`` in the epistemic
module: ``EvidenceFor`` records what justifies a stance; ``Because``
records why a thing is so.  Justification and causation part company
exactly where a holder's evidence is real but is not the reason.

Minting discipline lives outside this library.  Callers are expected
to match first against existing feeling nodes (``feeling_node``
dedups exact text; near matches are the caller's problem to find) and
to name a genuinely new feeling by compounding its descriptive words
into a single self-describing token.  The library never normalizes,
merges, or guesses: two different texts are two different feeling
atoms, even when a human can see they are twins.  Silently merging
would merge genuinely different feelings along with the duplicates,
and the refusal to guess is what exposes a caller's naming mistakes
instead of hiding them.

Depends on Core and the relational vocabulary (kind checks are
IsA-aware, as in the acts module); the speech and epistemic modules
do not depend on this one.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union
from weakref import WeakKeyDictionary

from ...atoms import AtomId, Predicate
from ...facade import AtomSpaceAPI
from ...infrastructure import InvalidAtomOperationError, UnknownAtomError
from ...rules.generic import RuleSet
from ..relational import install as install_relational


_FEELS_SPECS = {
    "Feels": ("holder", "feeling"),
    "Because": ("subject", "ground"),
}

_INSTALLATIONS: "WeakKeyDictionary[AtomSpaceAPI, FeelsPredicates]" = (
    WeakKeyDictionary()
)


class FeelsPredicates:
    """Installed feels vocabulary bound to one :class:`AtomSpaceAPI`."""

    def __init__(self, api: AtomSpaceAPI) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self.api = api
        self.predicates: Dict[str, AtomId] = {}
        for name, roles in _FEELS_SPECS.items():
            predicate = api.predicate(name, arity=2, roles=roles)
            self.predicates[name] = predicate
            setattr(self, name, predicate)
        self._names = {predicate: name for name, predicate in self.predicates.items()}
        self.feeling_kind = api.kind("Feeling")
        self.relational = install_relational(api)

        self.rules = RuleSet(api)

    def __getitem__(self, name: str) -> AtomId:
        return self.predicates[name]

    # -- feeling atoms -------------------------------------------------------

    def feeling_node(self, text: str) -> AtomId:
        """Return the feeling atom for a piece of text, minting it if new.

        The same text always resolves to the same ``Feeling`` node.
        The text is used exactly as given — conventionally a single
        compounded token naming the feeling — and is never normalized.
        """
        if not isinstance(text, str) or not text:
            raise TypeError("feeling text must be a non-empty string")
        for atom_id in self.api.find_by_label(text):
            if self.relational.kind_is_a(atom_id, self.feeling_kind):
                return atom_id
        return self.api.create_node(text, kind=self.feeling_kind)

    def is_feeling(self, atom_id: AtomId) -> bool:
        """Return whether ``atom_id`` is a live ``Feeling`` node — or
        a node under a subkind of Feeling in the IsA hierarchy."""
        return self.relational.kind_is_a(atom_id, self.feeling_kind)

    def _resolve_feeling(self, feeling: Union[AtomId, str]) -> AtomId:
        if isinstance(feeling, str):
            return self.feeling_node(feeling)
        self._check_atom(feeling, "feeling")
        if not self.relational.kind_is_a(feeling, self.feeling_kind):
            raise TypeError(
                "Feels target must be a Feeling node; mint one with "
                "feeling_node()"
            )
        return feeling

    def _check_atom(self, atom_id: AtomId, role: str) -> None:
        """Preflight one argument: it must exist, be live, and be usable
        as a relationship argument (Core refuses Current assertions)."""
        try:
            raw = self.api.get_raw(atom_id)
        except UnknownAtomError:
            raise UnknownAtomError(
                f"feels {role} names unknown atom {atom_id!r}"
            ) from None
        if raw.deleted:
            raise UnknownAtomError(
                f"feels {role} names deleted atom {atom_id!r}"
            )
        atom = raw.atom
        if (
            isinstance(atom, Predicate)
            and atom.predicate == self.api.current_predicate
        ):
            raise InvalidAtomOperationError(
                f"feels {role} names a Current assertion, which cannot "
                "be a relationship argument"
            )

    # -- assertion -----------------------------------------------------------

    def feel(
        self,
        holder: AtomId,
        feeling: Union[AtomId, str],
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert ``Feels(holder, feeling)`` and return the atom.

        ``feeling`` is a ``Feeling`` node, or text (which is resolved
        to its ``Feeling`` node through :meth:`feeling_node`).
        """
        self._check_atom(holder, "holder")
        feeling_id = self._resolve_feeling(feeling)
        return self.rules.create_predicate(
            self.Feels, holder, feeling_id,
            label=label, confidence=confidence,
        )

    def because(
        self,
        subject: AtomId,
        ground: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert ``Because(subject, ground)``: subject holds because
        of ground.  The standard pointer from a feeling node to the
        claim or event the feeling is about, and from anything else to
        its reason."""
        self._check_atom(subject, "subject")
        self._check_atom(ground, "ground")
        return self.rules.create_predicate(
            self.Because, subject, ground,
            label=label, confidence=confidence,
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
        """Assert one feels predicate (``Feels`` or ``Because``)."""
        name = self._names.get(predicate)
        if name is None:
            raise TypeError("predicate is not part of the feels vocabulary")
        if name == "Feels":
            return self.feel(left, right, label=label, confidence=confidence)
        return self.because(left, right, label=label, confidence=confidence)

    create_predicate = relate
    create_link = relate

    def has(self, predicate: AtomId, left: AtomId, right: AtomId) -> bool:
        if predicate not in self._names:
            raise TypeError("predicate is not part of the feels vocabulary")
        return self.rules.has_predicate(predicate, left, right)

    has_predicate = has
    has_link = has

    # -- inspection ------------------------------------------------------------

    def feelings_of(self, holder: AtomId) -> List[AtomId]:
        """Return every ``Feels`` atom asserted with this holder."""
        found: List[AtomId] = []
        for result in self.api.search(predicate=self.Feels):
            atom = result.atom
            if isinstance(atom, Predicate) and atom.args[0] == holder:
                found.append(atom.id)
        return found

    def feeling_atoms_of(self, holder: AtomId) -> List[AtomId]:
        """Return the feeling nodes this holder currently feels."""
        nodes: List[AtomId] = []
        for atom_id in self.feelings_of(holder):
            atom = self.api.get(atom_id)
            if isinstance(atom, Predicate) and atom.args[1] not in nodes:
                nodes.append(atom.args[1])
        return nodes

    def holders_of(self, feeling: AtomId) -> List[AtomId]:
        """Return every holder with a ``Feels`` atom on this feeling."""
        found: List[AtomId] = []
        for result in self.api.search(predicate=self.Feels):
            atom = result.atom
            if isinstance(atom, Predicate) and atom.args[1] == feeling \
                    and atom.args[0] not in found:
                found.append(atom.args[0])
        return found

    def occurrences(self, feeling: AtomId) -> List[AtomId]:
        """Return every ``Feels`` atom pointing at this feeling node.

        This is the feeling's history: because the node is canonical,
        each occurrence is one recorded episode of someone feeling it,
        and the episodes carry their own evidence elsewhere in the graph.
        """
        found: List[AtomId] = []
        for result in self.api.search(predicate=self.Feels):
            atom = result.atom
            if isinstance(atom, Predicate) and atom.args[1] == feeling:
                found.append(atom.id)
        return found

    def reasons_for(self, subject: AtomId) -> List[AtomId]:
        """Return the ground atoms recorded for ``subject`` via Because."""
        found: List[AtomId] = []
        for result in self.api.search(predicate=self.Because):
            atom = result.atom
            if isinstance(atom, Predicate) and atom.args[0] == subject:
                found.append(atom.args[1])
        return found

    def explained_by(self, ground: AtomId) -> List[AtomId]:
        """Return every subject that points at ``ground`` via Because."""
        found: List[AtomId] = []
        for result in self.api.search(predicate=self.Because):
            atom = result.atom
            if isinstance(atom, Predicate) and atom.args[1] == ground:
                found.append(atom.args[0])
        return found


def install(api: AtomSpaceAPI) -> FeelsPredicates:
    """Install and return a feels vocabulary for ``api``."""
    installed = _INSTALLATIONS.get(api)
    if installed is None:
        installed = FeelsPredicates(api)
        _INSTALLATIONS[api] = installed
    return installed


install_feels_predicates = install
Feels = FeelsPredicates

__all__ = [
    "FeelsPredicates", "Feels", "install", "install_feels_predicates",
]
