"""Preference predicate vocabulary and its domain-level rule semantics.

Preferences are ordinary, first-class atoms -- not a separate scoring
system.  The stance predicates (``Loves`` .. ``Hates``) relate a subject
to a target.  ``Prefers`` relates two preference *statements*: its
arguments are stance assertion atoms, e.g.
``Prefers(Likes(Elena, Steak), Loves(Elena, Shrimp))``.

The default hierarchy, strongest to weakest, is

    Loves > Likes > Indifferent > Dislikes > Hates

Hierarchy consequences are derived at query time and never materialized:
``Loves`` satisfies a ``Likes`` query, ``Hates`` satisfies a ``Dislikes``
query, and a subject's ranking of two targets can be inferred from their
respective stances.  An explicit ``Prefers`` assertion overrides the
inferred ranking.  When an explicit preference and the inferred ranking
disagree, both are preserved: the disagreement is a contradiction the
system can reason about (via the logic module's ``Contradicts``), not an
error to be erased.

Contradictions are recorded automatically at assertion time.  Asserting
a stance that fights an existing stance on the same subject and target
-- opposite sides of the scale, or ``Indifferent`` against any stance --
creates the new atom and a ``Contradicts`` atom linking the two, in the
same ``relate`` call.  The one exception is supersession: if the new
assertion is shown superseding the old one with a Transition atom
(``relate(..., supersedes=old_atom)``, or ``supersede(old, new)`` after
the fact), the change is a replacement over time, not a contradiction,
and no ``Contradicts`` atom is made for that pair.

Observed behavior is deliberately not handled here.  A single choice is
one observation, not a preference; how behavioral evidence accumulates
and when it should trigger reassessment of a stated preference is an
open decision with no threshold settled, so this module records stated
and explicit preferences and derives inferred ones -- nothing more.

Depends on the logic module (for ``Contradicts``); the logic module
does not depend on this one.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from weakref import WeakKeyDictionary

from ...atoms import AtomId, Predicate
from ...facade import AtomSpaceAPI
from ...infrastructure import UnknownAtomError
from ...rules.generic import RuleSet, Transitive
from ..logic import install as install_logic


_PREFERENCE_SPECS = {
    "Loves": ("subject", "target"),
    "Likes": ("subject", "target"),
    "Indifferent": ("subject", "target"),
    "Dislikes": ("subject", "target"),
    "Hates": ("subject", "target"),
    "Prefers": ("preferred_statement", "dispreferred_statement"),
}

# Position on the preference scale.  Indifferent is a real stance at
# zero, not the absence of a stance: an unrecorded target has no rank.
_SCALE = {
    "Loves": 2,
    "Likes": 1,
    "Indifferent": 0,
    "Dislikes": -1,
    "Hates": -2,
}

_STANCES = ("Loves", "Likes", "Indifferent", "Dislikes", "Hates")

# A stronger stance on the same side of the scale satisfies a query
# for the weaker one.  There is no cross-side implication: Likes does
# not imply Indifferent, and Dislikes does not either.
_IMPLIES = {"Loves": "Likes", "Hates": "Dislikes"}

_INSTALLATIONS: "WeakKeyDictionary[AtomSpaceAPI, PreferencePredicates]" = (
    WeakKeyDictionary()
)


class PreferencePredicates:
    """Installed preference vocabulary bound to one :class:`AtomSpaceAPI`."""

    def __init__(self, api: AtomSpaceAPI) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self.api = api
        self.logic = install_logic(api)
        self.predicates: Dict[str, AtomId] = {}
        for name, roles in _PREFERENCE_SPECS.items():
            predicate = api.predicate(name, arity=2, roles=roles)
            self.predicates[name] = predicate
            setattr(self, name, predicate)

        self.rules = RuleSet(api)
        self._install_rules()

    def __getitem__(self, name: str) -> AtomId:
        return self.predicates[name]

    def _install_rules(self) -> None:
        # Explicit preference chains compose: Prefers(A, B) and
        # Prefers(B, C) satisfy a query for Prefers(A, C), at query
        # time, without materializing the composed assertion.
        self.rules.register(self.Prefers, Transitive())

    def relate(
        self,
        predicate: AtomId,
        left: AtomId,
        right: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
        supersedes: Optional[AtomId] = None,
    ) -> AtomId:
        """Assert one preference using this vocabulary's canonicalization.

        If the new assertion contradicts an existing one, a
        ``Contradicts`` atom linking the two is created in the same
        call.  Pass ``supersedes`` naming the existing assertion this
        one replaces to record a Transition instead: a superseded
        assertion is not contradicted.
        """
        name = self._name_of(predicate)
        if supersedes is not None:
            self._check_supersede(name, supersedes, left, right)
        if name == "Prefers":
            self._check_prefers_args(left, right)
        atom_id = self.rules.create_predicate(
            predicate,
            left,
            right,
            label=label,
            confidence=confidence,
        )
        if name in _STANCES:
            self._after_stance(atom_id, name, left, right, supersedes)
        elif name == "Prefers":
            self._after_prefers(atom_id, left, right, supersedes)
        return atom_id

    create_predicate = relate
    create_link = relate

    # -- automatic contradiction / supersession ----------------------------

    def _check_supersede(
        self,
        name: Optional[str],
        supersedes: AtomId,
        left: AtomId,
        right: AtomId,
    ) -> None:
        """Validate a supersession before any atom is written.

        The superseded atom must exist and be live, and must be the
        assertion this one replaces: a stance assertion on the same
        subject and target, or a ``Prefers`` assertion when the new
        atom is one.  Anything else is refused up front, so the
        post-creation Transition cannot fail on foreseeable input.
        """
        if name not in _STANCES + ("Prefers",):
            raise TypeError("only preference assertions can supersede")
        try:
            raw = self.api.get_raw(supersedes)
        except UnknownAtomError:
            raise UnknownAtomError(
                f"supersedes names unknown atom {supersedes!r}"
            ) from None
        if raw.deleted:
            raise UnknownAtomError(
                f"supersedes names deleted atom {supersedes!r}"
            )
        old = raw.atom
        if not isinstance(old, Predicate):
            raise TypeError("supersedes must name a preference assertion")
        if name == "Prefers":
            if old.predicate != self.Prefers:
                raise TypeError("a Prefers assertion can only supersede a Prefers assertion")
        elif old.predicate not in {
            self.predicates[stance] for stance in _STANCES
        } or old.args != (left, right):
            raise TypeError(
                "supersedes must name a stance assertion on the same "
                "subject and target"
            )

    def _check_prefers_args(self, left: AtomId, right: AtomId) -> None:
        """Prefers orders two stance assertions by the same subject.

        Anything else — a person, a thing, stances by two different
        subjects — is a category error, refused before any atom is
        written rather than stored as a meaningless assertion whose
        post-assertion hook silently no-ops.
        """
        stance_ids = {self.predicates[stance] for stance in _STANCES}
        subjects = []
        for arg in (left, right):
            atom = self.api.get_raw(arg).atom
            if not isinstance(atom, Predicate) or atom.predicate not in stance_ids:
                raise TypeError(
                    "Prefers relates two preference stance assertions, "
                    f"not atom {arg!r}"
                )
            subjects.append(atom.args[0])
        if subjects[0] != subjects[1]:
            raise TypeError(
                "Prefers requires stance assertions by the same subject"
            )

    def _name_of(self, predicate: AtomId) -> Optional[str]:
        for name, predicate_id in self.predicates.items():
            if predicate_id == predicate:
                return name
        return None

    @staticmethod
    def _stances_contradict(first: str, second: str) -> bool:
        a, b = _SCALE[first], _SCALE[second]
        if a == 0 or b == 0:
            return a != b
        return (a > 0) != (b > 0)

    def _contradict(self, first: AtomId, second: AtomId) -> AtomId:
        return self.logic.relate(self.logic.Contradicts, first, second)

    def _after_stance(
        self,
        atom_id: AtomId,
        name: str,
        subject: AtomId,
        target: AtomId,
        supersedes: Optional[AtomId],
    ) -> None:
        if supersedes is not None:
            self.supersede(supersedes, atom_id)
        for other_name in _STANCES:
            if other_name == name:
                continue
            for result in self.api.find_predicates(
                self.predicates[other_name], subject, target
            ):
                existing = result.atom.id
                if existing == atom_id or existing == supersedes:
                    continue
                if self._stances_contradict(name, other_name):
                    self._contradict(atom_id, existing)

    def _after_prefers(
        self,
        atom_id: AtomId,
        left: AtomId,
        right: AtomId,
        supersedes: Optional[AtomId],
    ) -> None:
        if supersedes is not None:
            self.supersede(supersedes, atom_id)
        left_atom = self.api.get(left)
        right_atom = self.api.get(right)
        left_args = getattr(left_atom, "args", None)
        right_args = getattr(right_atom, "args", None)
        if (
            left_args is None
            or right_args is None
            or len(left_args) != 2
            or len(right_args) != 2
        ):
            return
        subject, first_target = left_args
        other_subject, second_target = right_args
        if subject != other_subject:
            return
        # An opposing explicit Prefers on the same pair contradicts this one.
        opposing = self.explicit_preference(
            subject, second_target, first_target
        )
        if opposing is not None and opposing != atom_id:
            self._contradict(atom_id, opposing)
        # An explicit Prefers that fights the inferred ranking records
        # its contradiction with the stance atom driving that ranking.
        self.record_contradictions(subject, first_target, second_target)

    def supersede(self, old: AtomId, new: AtomId) -> AtomId:
        """Show ``new`` superseding ``old`` with a Transition atom.

        Creates ``Transition(old, new)`` and logically deletes any
        ``Contradicts`` atom between the pair: once the change is shown
        as a replacement over time, the two assertions no longer stand
        as simultaneous, contradictory claims.  Returns the Transition.
        """
        for first, second in ((old, new), (new, old)):
            for result in self.api.find_predicates(
                self.logic.Contradicts, first, second
            ):
                self.api.delete(result.atom.id)
        return self.api.transition(old, new)

    def has(self, predicate: AtomId, left: AtomId, right: AtomId) -> bool:
        """Query a preference, including hierarchy implication.

        ``Loves(A, B)`` satisfies a ``Likes(A, B)`` query and
        ``Hates(A, B)`` satisfies a ``Dislikes(A, B)`` query.  The
        implied relationship is evaluated here, not materialized.
        """
        if self.rules.has_predicate(predicate, left, right):
            return True
        for stronger, weaker in _IMPLIES.items():
            if predicate == self.predicates[weaker]:
                if self.api.has_predicate(self.predicates[stronger], left, right):
                    return True
        return False

    has_predicate = has
    has_link = has

    # -- stance inspection -------------------------------------------------

    def statements(self, subject: AtomId, target: AtomId) -> List[AtomId]:
        """Return the asserted stance atoms relating subject to target."""
        found: List[AtomId] = []
        for name in _STANCES:
            for result in self.api.find_predicates(
                self.predicates[name], subject, target
            ):
                found.append(result.atom.id)
        return found

    def rank(self, subject: AtomId, target: AtomId) -> Optional[int]:
        """Return the subject's effective scale position toward target.

        Derived from the asserted stances only; nothing is written.
        Returns ``None`` when no stance is asserted, and also when the
        strongest asserted stances cancel (e.g. both ``Loves`` and
        ``Hates``) -- that conflict is knowledge to reason about, not
        a tie this method may silently break.
        """
        values = set()
        for name in _STANCES:
            if self.api.has_predicate(self.predicates[name], subject, target):
                values.add(_SCALE[name])
        if not values:
            return None
        strongest = max(abs(value) for value in values)
        top = {value for value in values if abs(value) == strongest}
        if len(top) > 1:
            return None
        return top.pop()

    def _driving_statement(
        self, subject: AtomId, target: AtomId
    ) -> Optional[AtomId]:
        """Return the stance atom that determines target's rank, if any."""
        value = self.rank(subject, target)
        if value is None:
            return None
        for name in _STANCES:
            if _SCALE[name] == value:
                found = self.api.find_predicates(
                    self.predicates[name], subject, target
                )
                if found:
                    return found[0].atom.id
        return None

    # -- explicit versus inferred ------------------------------------------

    def explicit_preference(
        self, subject: AtomId, preferred: AtomId, dispreferred: AtomId
    ) -> Optional[AtomId]:
        """Return an asserted ``Prefers`` atom ranking two targets, if any.

        ``Prefers`` relates statements, so this looks for an assertion
        between any stance atom of the preferred target and any stance
        atom of the dispreferred target.
        """
        for left in self.statements(subject, preferred):
            for right in self.statements(subject, dispreferred):
                found = self.api.find_predicates(self.Prefers, left, right)
                if found:
                    return found[0].atom.id
        return None

    def preferred(
        self, subject: AtomId, first: AtomId, second: AtomId
    ) -> Optional[AtomId]:
        """Return which of two targets the subject prefers, if determinable.

        An explicit ``Prefers`` assertion wins over the hierarchy.  With
        no explicit assertion, the inferred ranking decides.  Returns
        ``None`` when the ranking is equal, ambiguous, or unknown for
        either target.
        """
        if self.explicit_preference(subject, first, second) is not None:
            return first
        if self.explicit_preference(subject, second, first) is not None:
            return second
        first_rank = self.rank(subject, first)
        second_rank = self.rank(subject, second)
        if first_rank is None or second_rank is None:
            return None
        if first_rank > second_rank:
            return first
        if second_rank > first_rank:
            return second
        return None

    def contradictions(
        self, subject: AtomId, first: AtomId, second: AtomId
    ) -> List[Tuple[AtomId, AtomId]]:
        """Find explicit preferences that contradict the inferred ranking.

        Returns (explicit ``Prefers`` atom, driving stance atom) pairs:
        the stance atom whose asserted strength makes the hierarchy
        rank the targets opposite to the explicit assertion.  Both
        sides of the disagreement remain in the graph.
        """
        found: List[Tuple[AtomId, AtomId]] = []
        for winner, loser in ((first, second), (second, first)):
            explicit = self.explicit_preference(subject, winner, loser)
            if explicit is None:
                continue
            winner_rank = self.rank(subject, winner)
            loser_rank = self.rank(subject, loser)
            if (
                winner_rank is not None
                and loser_rank is not None
                and loser_rank > winner_rank
            ):
                driving = self._driving_statement(subject, loser)
                if driving is not None:
                    found.append((explicit, driving))
        return found

    def record_contradictions(
        self, subject: AtomId, first: AtomId, second: AtomId
    ) -> List[AtomId]:
        """Record each found contradiction as a ``Contradicts`` atom."""
        recorded: List[AtomId] = []
        for explicit, driving in self.contradictions(subject, first, second):
            recorded.append(
                self.logic.relate(self.logic.Contradicts, explicit, driving)
            )
        return recorded


def install(api: AtomSpaceAPI) -> PreferencePredicates:
    """Install and return a preference vocabulary for ``api``."""
    installed = _INSTALLATIONS.get(api)
    if installed is None:
        installed = PreferencePredicates(api)
        _INSTALLATIONS[api] = installed
    return installed


install_preference_predicates = install
Preferences = PreferencePredicates

__all__ = [
    "PreferencePredicates", "Preferences", "install",
    "install_preference_predicates",
]
