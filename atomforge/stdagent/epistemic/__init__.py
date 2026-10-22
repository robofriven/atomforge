"""Epistemic predicate vocabulary: what a holder believes, suspects, knows.

Presupposes believers — agents with a point of view.  Everything in
this module is judged *inside the holder's graph*: there is no external
truth stamp, and none is needed.

The ladder (three tiers, one holder, one claim atom):

- ``Believes(holder, claim)`` — acceptance.  Requires no evidence and
  does not care about truth.  This is the tier that holds full
  acceptance on zero evidence.
- ``Suspects(holder, claim)`` — entertained, with some ground.  Requires
  at least one ground: an evidence atom, an inference source, a
  premise, or a witnessed scene.
- ``Knows(holder, claim)`` — acceptance plus believed evidence.
  "True" here is *internal* truth: the holder believes the claim and
  believes its evidence.  ``relate`` enforces this mechanically — every
  evidence atom supplied for a ``Knows`` must itself be a claim the
  holder currently Believes or Knows, or the assertion is refused.
  An agent can therefore genuinely Know a false thing, by every test
  its own graph can run.

Claims are atoms — any proposition, including another agent's stance
atoms and ``Says`` atoms from the speech module.  ``Believes(elena,
Likes(robert, ...))`` is how reported material stays wrapped as her
belief instead of leaking into her graph as ground truth.

``EvidenceFor(claim, ground)`` is the directional grounding relation:
grounds are scenes, claim atoms, or saying atoms.  It replaces what
used to be a prose convention.  Causation is a different relation
(``Because``, elsewhere): EvidenceFor is what justifies, not why
something came to be believed.

Acquisition modes (``via=``) record how a claim entered, as Ligatures
on the epistemic atom, and each mode carries a requirement enforced
before anything is written:

- ``via="learned"`` — taught.  Requires ``teacher=``.  If the claim is
  a ``Says`` atom, its speaker must be the teacher.
- ``via="discovered"`` — found firsthand.  Requires ``scene=`` or
  ``declaration=``; either is also recorded as a ground via
  ``EvidenceFor``.  A declaration is a witnessed performative — a
  consent, a promise, an agreement — where the saying *constitutes*
  the claim rather than reporting it, so it warrants the way a scene
  does: the holder was present at the fact's creation.  The claim
  must be a predicate atom whose first argument is the declaration's
  speaker; a declaration binds only its maker.  A *report* of a
  performative — someone else's saying about it — is not a
  declaration and stays ``learned``.
- ``via="inferred"`` — induced from sources.  Requires ``sources=``
  and may only enter at ``Suspects``: induction never buys certainty.
- ``via="deduced"`` — deduced from premises.  Requires ``premises=``;
  the conclusion's tier may not exceed the weakest premise's tier.

Tier movement is revision, not editing: ``revise(old, tier, ...)``
asserts the new tier with a Transition from the old atom, history
preserved.  Demotion is the normal case — a holder who stops believing
their evidence falls from Knows back to Believes.

Deliberate omissions: certainty (how sure a holder is, beyond tier) is
not represented here — the word for it is unsettled and it is not Core
confidence metadata either.  This module also does not record
``Contradicts`` atoms between tiers; tier conflicts on one claim are
queryable via ``tier_of`` and left for the reasoner to weigh.

Model error flags: ``ModelError(claim)`` is a unary provenance flag
over a claim atom.  It asserts that the claim's *content* is an
artifact of the generating model — a miscounted day, a swapped clock —
retained in the graph for the record rather than deleted.  The saying
of it may be perfectly true (a ``Says`` atom stands untouched); what
the flag denies is the content's standing as fact.  Flagged claims are
excluded from fact-grade use by consumers, and claims grounded in
flagged claims inherit the taint — see ``downstream_of_flagged``.  The
flag is orthogonal to tier: a holder may hold a flagged claim at any
tier, which is exactly the historical situation the flag exists to
describe honestly.

Depends on the speech module (for ``Says`` speaker checks); speech
does not depend on this one.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple
from weakref import WeakKeyDictionary

from ...atoms import AtomId, Predicate
from ...facade import AtomSpaceAPI
from ...infrastructure import InvalidAtomOperationError, UnknownAtomError
from ...rules.generic import RuleSet
from ..speech import install as install_speech


_EPISTEMIC_SPECS = {
    "Believes": ("holder", "claim"),
    "Suspects": ("holder", "claim"),
    "Knows": ("holder", "claim"),
    "EvidenceFor": ("claim", "ground"),
}

_TIERS = ("Suspects", "Believes", "Knows")
_RANK = {"Suspects": 0, "Believes": 1, "Knows": 2}

# Query-time implication only, never materialized (same pattern as the
# preferences hierarchy): to Know a claim is, among other things, to
# believe it.
_IMPLIES = {"Knows": "Believes"}

_MODES = ("learned", "discovered", "inferred", "deduced")

_INSTALLATIONS: "WeakKeyDictionary[AtomSpaceAPI, EpistemicPredicates]" = (
    WeakKeyDictionary()
)


class EpistemicPredicates:
    """Installed epistemic vocabulary bound to one :class:`AtomSpaceAPI`."""

    def __init__(self, api: AtomSpaceAPI) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self.api = api
        self.speech = install_speech(api)
        self.predicates: Dict[str, AtomId] = {}
        for name, roles in _EPISTEMIC_SPECS.items():
            predicate = api.predicate(name, arity=2, roles=roles)
            self.predicates[name] = predicate
            setattr(self, name, predicate)
        self._names = {predicate: name for name, predicate in self.predicates.items()}

        # Unary provenance flag; arity differs from the tier specs, so
        # it is installed outside the loop above.
        self.ModelError = api.predicate("ModelError", arity=1, roles=("claim",))
        self.predicates["ModelError"] = self.ModelError
        self._names[self.ModelError] = "ModelError"

        self.rules = RuleSet(api)

    def __getitem__(self, name: str) -> AtomId:
        return self.predicates[name]

    # -- preflight -----------------------------------------------------------

    def _check_atom(self, atom_id: AtomId, role: str) -> None:
        try:
            raw = self.api.get_raw(atom_id)
        except UnknownAtomError:
            raise UnknownAtomError(
                f"epistemic {role} names unknown atom {atom_id!r}"
            ) from None
        if raw.deleted:
            raise UnknownAtomError(
                f"epistemic {role} names deleted atom {atom_id!r}"
            )
        atom = raw.atom
        if (
            isinstance(atom, Predicate)
            and atom.predicate == self.api.current_predicate
        ):
            raise InvalidAtomOperationError(
                f"epistemic {role} names a Current assertion, which "
                "cannot be a relationship argument"
            )

    def _asserted_tier(self, holder: AtomId, claim: AtomId) -> Optional[str]:
        """Strongest tier actually asserted for (holder, claim), if any.

        Raw assertions only — query-time implication does not count
        here, because validation must see what is really in the graph.
        """
        for name in ("Knows", "Believes", "Suspects"):
            if self.api.has_predicate(self.predicates[name], holder, claim):
                return name
        return None

    # -- assertion -----------------------------------------------------------

    def relate(
        self,
        predicate: AtomId,
        holder: AtomId,
        claim: AtomId,
        *,
        via: Optional[str] = None,
        teacher: Optional[AtomId] = None,
        scene: Optional[AtomId] = None,
        declaration: Optional[AtomId] = None,
        evidence: Iterable[AtomId] = (),
        premises: Iterable[AtomId] = (),
        sources: Iterable[AtomId] = (),
        supersedes: Optional[AtomId] = None,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert one epistemic stance, with FTFO validation.

        Everything is checked before any atom is written, so a refused
        assertion leaves the graph untouched.
        """
        name = self._names.get(predicate)
        if name is None:
            raise TypeError("predicate is not part of the epistemic vocabulary")
        if name == "EvidenceFor":
            if via is not None or teacher is not None or scene is not None \
                    or declaration is not None \
                    or premises or sources or supersedes is not None:
                raise TypeError("EvidenceFor takes no via/teacher/scene/"
                                "declaration/premises/sources/supersedes "
                                "arguments")
            return self.evidence_for(holder, claim, label=label,
                                     confidence=confidence)

        evidence = tuple(evidence)
        premises = tuple(premises)
        sources = tuple(sources)

        self._check_atom(holder, "holder")
        self._check_atom(claim, "claim")
        for atom_id in evidence:
            self._check_atom(atom_id, "evidence")
        for atom_id in premises:
            self._check_atom(atom_id, "premise")
        for atom_id in sources:
            self._check_atom(atom_id, "source")
        if teacher is not None:
            self._check_atom(teacher, "teacher")
        if scene is not None:
            self._check_atom(scene, "scene")
        if declaration is not None:
            self._check_atom(declaration, "declaration")

        grounds = list(evidence)
        # Grounds the holder must separately believe for a Knows
        # assertion.  A discovery scene or a witnessed declaration is
        # exempt: witnessing is self-warranting, the holder was there.
        believed_grounds = list(evidence)
        ligatures: List[Tuple[str, AtomId]] = []

        if via is not None:
            if via not in _MODES:
                raise TypeError(f"unknown acquisition mode {via!r}")
            if via == "learned":
                if teacher is None:
                    raise TypeError("via='learned' requires teacher=")
                if premises or sources or scene is not None \
                        or declaration is not None:
                    raise TypeError("via='learned' takes no premises, "
                                    "sources, scene, or declaration")
                if self.speech.is_saying(claim):
                    speaker = self.speech.speaker_of(claim)
                    if speaker != teacher:
                        raise TypeError(
                            "via='learned': the claim is a Says atom "
                            "whose speaker is not the named teacher"
                        )
                ligatures.append(("Teacher", teacher))
            elif via == "discovered":
                if (scene is None) == (declaration is None):
                    raise TypeError("via='discovered' requires exactly "
                                    "one of scene= or declaration=")
                if teacher is not None or premises or sources:
                    raise TypeError("via='discovered' takes no teacher, "
                                    "premises, or sources")
                if scene is not None:
                    grounds.append(scene)
                else:
                    if not self.speech.is_saying(declaration):
                        raise TypeError(
                            "via='discovered': declaration must be a "
                            "Says atom"
                        )
                    claim_atom = self.api.get(claim)
                    if not isinstance(claim_atom, Predicate):
                        raise TypeError(
                            "via='discovered': a declaration warrants "
                            "a performative predicate claim, not a "
                            "bare node"
                        )
                    if not claim_atom.args or claim_atom.args[0] != \
                            self.speech.speaker_of(declaration):
                        raise TypeError(
                            "via='discovered': the declaration's "
                            "speaker is not the party the claim binds"
                        )
                    grounds.append(declaration)
            elif via == "inferred":
                if name != "Suspects":
                    raise TypeError(
                        "via='inferred' enters at Suspects only: "
                        "induction never buys certainty"
                    )
                if not sources:
                    raise TypeError("via='inferred' requires sources=")
                if teacher is not None or premises or scene is not None \
                        or declaration is not None:
                    raise TypeError("via='inferred' takes no teacher, "
                                    "premises, scene, or declaration")
                ligatures.extend(("Source", s) for s in sources)
            elif via == "deduced":
                if not premises:
                    raise TypeError("via='deduced' requires premises=")
                if teacher is not None or sources or scene is not None \
                        or declaration is not None:
                    raise TypeError("via='deduced' takes no teacher, "
                                    "sources, scene, or declaration")
                weakest: Optional[int] = None
                for premise in premises:
                    tier = self._asserted_tier(holder, premise)
                    if tier is None:
                        raise TypeError(
                            "via='deduced': premise is not held by the "
                            "holder at any tier"
                        )
                    rank = _RANK[tier]
                    weakest = rank if weakest is None else min(weakest, rank)
                if weakest is not None and _RANK[name] > weakest:
                    raise TypeError(
                        "via='deduced': conclusion tier exceeds the "
                        "weakest premise's tier"
                    )
                ligatures.extend(("Premise", p) for p in premises)
        else:
            if teacher is not None or scene is not None \
                    or declaration is not None or premises or sources:
                raise TypeError(
                    "teacher/scene/declaration/premises/sources require "
                    "a via= mode"
                )

        if name == "Knows":
            if not grounds:
                raise TypeError(
                    "Knows requires evidence the holder believes; "
                    "assertion refused"
                )
            for ground in believed_grounds:
                tier = self._asserted_tier(holder, ground)
                if tier not in ("Believes", "Knows"):
                    raise TypeError(
                        "Knows requires evidence the holder believes: "
                        "ground is not Believed or Known by the holder"
                    )
        elif name == "Suspects":
            if not grounds and not sources and not premises:
                raise TypeError(
                    "Suspects requires some ground: evidence, a scene, "
                    "inference sources, or premises"
                )

        if supersedes is not None:
            self._check_supersede(supersedes, holder, claim)

        atom_id = self.rules.create_predicate(
            predicate, holder, claim, label=label, confidence=confidence
        )
        for ground in grounds:
            self.evidence_for(claim, ground)
        for ligature_name, target in ligatures:
            self.api.create_ligature(ligature_name, atom_id, target)
        if supersedes is not None:
            self.api.transition(supersedes, atom_id)
        return atom_id

    create_predicate = relate
    create_link = relate

    def _check_supersede(self, old: AtomId, holder: AtomId, claim: AtomId) -> None:
        self._check_atom(old, "supersedes")
        atom = self.api.get(old)
        if not isinstance(atom, Predicate) \
                or atom.predicate not in {self.predicates[t] for t in _TIERS}:
            raise TypeError("supersedes must name an epistemic tier assertion")
        if atom.args != (holder, claim):
            raise TypeError(
                "supersedes must name a tier assertion on the same "
                "holder and claim"
            )

    def revise(
        self,
        old: AtomId,
        new_tier: str,
        **kwargs,
    ) -> AtomId:
        """Assert ``new_tier`` for the same holder and claim as ``old``,
        with a Transition from the old atom.  Returns the new atom."""
        if new_tier not in _TIERS:
            raise TypeError(f"unknown tier {new_tier!r}")
        atom = self.api.get(old)
        if not isinstance(atom, Predicate) \
                or atom.predicate not in {self.predicates[t] for t in _TIERS}:
            raise TypeError("revise expects an epistemic tier assertion")
        holder, claim = atom.args
        return self.relate(
            self.predicates[new_tier], holder, claim,
            supersedes=old, **kwargs,
        )

    # -- evidence ------------------------------------------------------------

    def evidence_for(
        self,
        claim: AtomId,
        ground: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert ``EvidenceFor(claim, ground)``."""
        self._check_atom(claim, "claim")
        self._check_atom(ground, "ground")
        return self.rules.create_predicate(
            self.EvidenceFor, claim, ground,
            label=label, confidence=confidence,
        )

    def evidence_of(self, claim: AtomId) -> List[AtomId]:
        """Return the ground atoms recorded for ``claim``."""
        found: List[AtomId] = []
        for result in self.api.search(predicate=self.EvidenceFor):
            atom = result.atom
            if isinstance(atom, Predicate) and atom.args[0] == claim:
                found.append(atom.args[1])
        return found

    # -- queries ---------------------------------------------------------------

    def has(self, predicate: AtomId, holder: AtomId, claim: AtomId) -> bool:
        """Query a stance, including the Knows => Believes implication."""
        if self.rules.has_predicate(predicate, holder, claim):
            return True
        name = self._names.get(predicate)
        if name is not None and name in _IMPLIES.values():
            for stronger, weaker in _IMPLIES.items():
                if name == weaker and self.api.has_predicate(
                    self.predicates[stronger], holder, claim
                ):
                    return True
        return False

    has_predicate = has
    has_link = has

    def tier_of(self, holder: AtomId, claim: AtomId) -> Optional[str]:
        """Strongest asserted tier for (holder, claim), or ``None``."""
        return self._asserted_tier(holder, claim)

    def holds(self, holder: AtomId, claim: AtomId) -> bool:
        """Whether the holder holds the claim at any tier."""
        return self._asserted_tier(holder, claim) is not None

    # -- model error flags ---------------------------------------------------

    def flag_model_error(
        self,
        claim: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert ``ModelError(claim)``: the claim's content is a model
        artifact, kept for the record, denied standing as fact."""
        self._check_atom(claim, "claim")
        return self.rules.create_predicate(
            self.ModelError, claim, label=label, confidence=confidence,
        )

    def is_model_error(self, claim: AtomId) -> bool:
        """Whether ``claim`` carries a ``ModelError`` flag."""
        return self.api.has_predicate(self.ModelError, claim)

    def model_errors(self) -> List[AtomId]:
        """All claim atoms currently flagged ``ModelError``."""
        flagged: List[AtomId] = []
        for result in self.api.search(predicate=self.ModelError):
            atom = result.atom
            if isinstance(atom, Predicate):
                flagged.append(atom.args[0])
        return flagged

    def downstream_of_flagged(self) -> List[AtomId]:
        """Unflagged claims with at least one flagged ground.

        The downstream consequence of a model error: anything resting
        on it inherits the taint until re-grounded.  Direct grounds
        only — one ``EvidenceFor`` hop — so the report stays a precise
        list of what to re-examine, not a transitive smear.
        """
        flagged = set(self.model_errors())
        tainted: List[AtomId] = []
        seen = set()
        for result in self.api.search(predicate=self.EvidenceFor):
            atom = result.atom
            if isinstance(atom, Predicate):
                claim, ground = atom.args[0], atom.args[1]
                if ground in flagged and claim not in flagged and claim not in seen:
                    seen.add(claim)
                    tainted.append(claim)
        return tainted


def install(api: AtomSpaceAPI) -> EpistemicPredicates:
    """Install and return an epistemic vocabulary for ``api``."""
    installed = _INSTALLATIONS.get(api)
    if installed is None:
        installed = EpistemicPredicates(api)
        _INSTALLATIONS[api] = installed
    return installed


install_epistemic_predicates = install
Epistemic = EpistemicPredicates

__all__ = [
    "EpistemicPredicates", "Epistemic", "install",
    "install_epistemic_predicates",
]
