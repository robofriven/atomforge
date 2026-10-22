"""Consent predicate vocabulary: boundaries over act types.

A domain vocabulary: it presupposes the world of ``stdagent.acts``
(act types as canonical ``Act`` nodes), agents with boundaries, and
speech — consent is normally *declared*, and a declaration is a
``Says`` atom.

The predicates, all ``(holder, act)`` over act nodes:

- ``HardLimit(holder, act)`` — categorical refusal.  The act is off
  the table for this holder, full stop.
- ``ConsentsTo(holder, act)`` — affirmative consent by this holder.
- ``Permits(holder, act)`` — the act is permitted by this holder:
  allowed territory, a weaker and more passive stance than consenting
  oneself.

Consent is not preference, and the two vocabularies must not be
conflated: ``Likes`` is not permission and ``Dislikes`` is not
prohibition.  A holder can dislike an act they permit and like an act
that is a hard limit; each module records its own axis and neither
derives the other's answers.

Exclusions are first-class data.  ``relate(..., excludes=(...))``
records each excluded atom as an ``Excludes`` Ligature on the consent
atom itself: the consent covers the act *except* those atoms — a
variant act, a condition, a context.  An exclusion is never a silent
absence and never a separate negative assertion nobody links back to;
it rides on the consent it qualifies, and :meth:`exclusions_of` reads
it back.  Excluding the very act being consented to is refused: a
consent that excludes itself is a contradiction in the input, not a
state the graph should hold.

Declarations ground consent.  Pass ``declaration=`` naming a ``Says``
atom whose speaker is the holder, and the consent atom records that
saying as its evidence (epistemic ``EvidenceFor``): the trail from a
boundary back to the moment it was stated stays walkable.  A
declaration by anyone else is refused — one agent's words cannot
ground another agent's consent.

Conflicts are preserved, not resolved.  Asserting a consent-side
predicate (``ConsentsTo`` or ``Permits``) where a ``HardLimit``
already stands on the same holder and act — or the reverse — records
a ``Contradicts`` atom between the two assertions, in the preferences
module's style: both stay in the graph for a reasoner to weigh, and
:meth:`consent_state` reports the pair as ``"conflicted"`` rather
than silently picking a winner.  A boundary changed over time is a
Transition, which callers assert explicitly; this module does not
guess that a newer atom supersedes an older one.

Depends on stdagent acts (act validation), speech (declaration
checks), epistemic (EvidenceFor grounding), and logic (Contradicts).
None of those depend on this module.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional
from weakref import WeakKeyDictionary

from ...atoms import AtomId, Ligature, Predicate
from ...facade import AtomSpaceAPI
from ...infrastructure import InvalidAtomOperationError, UnknownAtomError
from ...rules.generic import RuleSet
from ...stdagent.acts import install as install_acts
from ...stdagent.epistemic import install as install_epistemic
from ...stdagent.logic import install as install_logic
from ...stdagent.speech import install as install_speech


_CONSENT_SPECS = {
    "HardLimit": ("holder", "act"),
    "ConsentsTo": ("holder", "act"),
    "Permits": ("holder", "act"),
}

# Asserting a predicate on one side where the other side already
# stands (same holder, same act) is a recorded contradiction.
_OPPOSES = {
    "HardLimit": ("ConsentsTo", "Permits"),
    "ConsentsTo": ("HardLimit",),
    "Permits": ("HardLimit",),
}

_INSTALLATIONS: "WeakKeyDictionary[AtomSpaceAPI, ConsentPredicates]" = (
    WeakKeyDictionary()
)


class ConsentPredicates:
    """Installed consent vocabulary bound to one :class:`AtomSpaceAPI`."""

    def __init__(self, api: AtomSpaceAPI) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self.api = api
        self.acts = install_acts(api)
        self.speech = install_speech(api)
        self.epistemic = install_epistemic(api)
        self.logic = install_logic(api)
        self.predicates: Dict[str, AtomId] = {}
        for name, roles in _CONSENT_SPECS.items():
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
                f"consent {role} names unknown atom {atom_id!r}"
            ) from None
        if raw.deleted:
            raise UnknownAtomError(
                f"consent {role} names deleted atom {atom_id!r}"
            )
        atom = raw.atom
        if (
            isinstance(atom, Predicate)
            and atom.predicate == self.api.current_predicate
        ):
            raise InvalidAtomOperationError(
                f"consent {role} names a Current assertion, which "
                "cannot be a relationship argument"
            )

    def _check_act(self, act: AtomId) -> None:
        self._check_atom(act, "act")
        if not self.acts.is_act(act):
            raise TypeError(
                "consent target must be an Act node; mint one with "
                "the acts module's act_node()"
            )

    # -- assertion -----------------------------------------------------------

    def relate(
        self,
        predicate: AtomId,
        holder: AtomId,
        act: AtomId,
        *,
        declaration: Optional[AtomId] = None,
        excludes: Iterable[AtomId] = (),
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert one consent predicate, with FTFO validation.

        Everything is checked before any atom is written, so a refused
        assertion leaves the graph untouched.  ``declaration`` grounds
        the assertion in the holder's own ``Says`` atom; ``excludes``
        records first-class exclusions as data on the new atom.
        """
        name = self._names.get(predicate)
        if name is None:
            raise TypeError("predicate is not part of the consent vocabulary")
        self._check_atom(holder, "holder")
        self._check_act(act)

        exclusions: List[AtomId] = []
        for excluded in excludes:
            self._check_atom(excluded, "exclusion")
            if excluded == act:
                raise TypeError(
                    "a consent assertion cannot exclude the very act "
                    "it is asserted on"
                )
            if excluded not in exclusions:
                exclusions.append(excluded)

        if declaration is not None:
            self._check_atom(declaration, "declaration")
            if not self.speech.is_saying(declaration):
                raise TypeError("declaration must be a Says atom")
            if self.speech.speaker_of(declaration) != holder:
                raise TypeError(
                    "declaration speaker is not the consent holder: "
                    "one agent's words cannot ground another's consent"
                )

        atom_id = self.rules.create_predicate(
            predicate, holder, act, label=label, confidence=confidence
        )
        for excluded in exclusions:
            self.api.create_ligature("Excludes", atom_id, excluded)
        if declaration is not None:
            self.epistemic.evidence_for(atom_id, declaration)
        self._record_conflicts(atom_id, name, holder, act)
        return atom_id

    create_predicate = relate
    create_link = relate

    def _record_conflicts(
        self, atom_id: AtomId, name: str, holder: AtomId, act: AtomId
    ) -> None:
        for other_name in _OPPOSES[name]:
            for result in self.api.find_predicates(
                self.predicates[other_name], holder, act
            ):
                other = result.atom.id
                if other != atom_id:
                    self.logic.relate(self.logic.Contradicts, atom_id, other)

    def has(self, predicate: AtomId, left: AtomId, right: AtomId) -> bool:
        if predicate not in self._names:
            raise TypeError("predicate is not part of the consent vocabulary")
        return self.rules.has_predicate(predicate, left, right)

    has_predicate = has
    has_link = has

    # -- inspection ------------------------------------------------------------

    def exclusions_of(self, consent_atom: AtomId) -> List[AtomId]:
        """Return the exclusion atoms recorded on a consent assertion."""
        found: List[AtomId] = []
        for ligature_id in self.api.in_ligatures(consent_atom):
            ligature = self.api.get(ligature_id)
            if isinstance(ligature, Ligature) \
                    and ligature.name == "Excludes" \
                    and len(ligature.args) == 2 \
                    and ligature.args[0] == consent_atom:
                found.append(ligature.args[1])
        return found

    def _assertions(self, name: str, holder: AtomId) -> List[AtomId]:
        found: List[AtomId] = []
        for result in self.api.search(predicate=self.predicates[name]):
            atom = result.atom
            if isinstance(atom, Predicate) and atom.args[0] == holder:
                found.append(atom.id)
        return found

    def hard_limits_of(self, holder: AtomId) -> List[AtomId]:
        """Return every ``HardLimit`` atom asserted by this holder."""
        return self._assertions("HardLimit", holder)

    def consents_of(self, holder: AtomId) -> List[AtomId]:
        """Return every ``ConsentsTo`` atom asserted by this holder."""
        return self._assertions("ConsentsTo", holder)

    def permits_of(self, holder: AtomId) -> List[AtomId]:
        """Return every ``Permits`` atom asserted by this holder."""
        return self._assertions("Permits", holder)

    def consent_state(self, holder: AtomId, act: AtomId) -> Optional[str]:
        """Summarize the holder's stance on an act, without resolving
        conflicts: ``"hard_limit"``, ``"consents"``, ``"permits"``,
        ``"conflicted"`` when opposing assertions both stand, or
        ``None`` when nothing is asserted."""
        hard = self.api.has_predicate(self.HardLimit, holder, act)
        consents = self.api.has_predicate(self.ConsentsTo, holder, act)
        permits = self.api.has_predicate(self.Permits, holder, act)
        if hard and (consents or permits):
            return "conflicted"
        if hard:
            return "hard_limit"
        if consents:
            return "consents"
        if permits:
            return "permits"
        return None


def install(api: AtomSpaceAPI) -> ConsentPredicates:
    """Install and return a consent vocabulary for ``api``."""
    installed = _INSTALLATIONS.get(api)
    if installed is None:
        installed = ConsentPredicates(api)
        _INSTALLATIONS[api] = installed
    return installed


install_consent_predicates = install
Consent = ConsentPredicates

__all__ = [
    "ConsentPredicates", "Consent", "install", "install_consent_predicates",
]
