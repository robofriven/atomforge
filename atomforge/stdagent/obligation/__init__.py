"""Obligation predicate vocabulary and its domain-level rule semantics.

Skeleton module, styled after ``stdagent.relational``.  The vocabulary is
the modal / attitude family: desire, want, need, compulsion, obligation,
commitment, and agreement.

Some predicates require a supporting atom before they may be asserted.
``Obligated`` without a reason is not an obligation, and ``Shall`` without
a consequence has no force.  Requirements are enforced here, above Core:
``relate`` raises when a required support is missing or does not name an
existing atom, and attaches each supplied support to the asserted atom
with a Ligature named for the requirement (``Reason``, ``Consequence``,
...).  Ligatures carry the grounds without minting new predicates for
them, so the predicate vocabulary stays exactly the twelve names below.

``Desires`` and ``Wants`` require nothing: they are self-certifying.
``Will`` requires agency -- the target must be the subject's own future
act -- which no supporting atom can establish, so it declares no
requirement here.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple
from weakref import WeakKeyDictionary

from ...atoms import AtomId, Predicate
from ...facade import AtomSpaceAPI
from ...infrastructure import InvalidAtomOperationError, UnknownAtomError
from ...rules.generic import RuleSet


_OBLIGATION_SPECS = {
    "Desires": ("subject", "desired"),
    "Wants": ("subject", "wanted"),
    "Needs": ("subject", "needed"),
    "HasTo": ("subject", "required"),
    "Obligated": ("subject", "obligation"),
    "Promises": ("promiser", "promised"),
    "AgreesTo": ("subject", "agreed"),
    "Acquiesces": ("subject", "acquiesced"),
    "Should": ("subject", "recommended"),
    "Shall": ("subject", "required"),
    "Must": ("subject", "required"),
    "Will": ("subject", "committed"),
}

# Predicate name -> required supporting atoms, by requirement name.
# The Ligature that records a support is named after the requirement:
# "reason" is recorded as a ``Reason`` Ligature, and so on.
_REQUIREMENTS: Dict[str, Tuple[str, ...]] = {
    "Desires": (),
    "Wants": (),
    "Needs": ("end",),
    "HasTo": ("circumstance",),
    "Obligated": ("reason",),
    "Promises": ("promisee",),
    "AgreesTo": ("proposal",),
    "Acquiesces": ("knowledge",),
    "Should": ("standard",),
    "Shall": ("consequence",),
    "Must": ("condition",),
    "Will": (),
}

_INSTALLATIONS: "WeakKeyDictionary[AtomSpaceAPI, ObligationPredicates]" = (
    WeakKeyDictionary()
)


class ObligationPredicates:
    """Installed obligation vocabulary bound to one :class:`AtomSpaceAPI`."""

    def __init__(self, api: AtomSpaceAPI) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self.api = api
        self.predicates: Dict[str, AtomId] = {}
        for name, roles in _OBLIGATION_SPECS.items():
            predicate = api.predicate(name, arity=2, roles=roles)
            self.predicates[name] = predicate
            setattr(self, name, predicate)
        self._names = {predicate: name for name, predicate in self.predicates.items()}

        self.rules = RuleSet(api)
        self._install_rules()

    def __getitem__(self, name: str) -> AtomId:
        return self.predicates[name]

    def _install_rules(self) -> None:
        # No generic relational rules apply to this vocabulary: none of
        # these predicates is symmetric, transitive, or the inverse of
        # another.  The RuleSet is still installed so assertion and
        # query go through the same path as the relational module.
        pass

    def requirements_for(self, name: str) -> Tuple[str, ...]:
        """Return the supporting atoms ``name`` requires before assertion."""
        return _REQUIREMENTS[name]

    def _check_requirements(
        self, name: str, supplied: Dict[str, AtomId]
    ) -> Dict[str, AtomId]:
        required = _REQUIREMENTS[name]
        missing = [key for key in required if key not in supplied]
        if missing:
            raise TypeError(
                f"{name} requires {', '.join(missing)}; assertion refused"
            )
        unexpected = [key for key in supplied if key not in required]
        if unexpected:
            raise TypeError(
                f"{name} takes no {', '.join(unexpected)} requirement"
            )
        for key, atom_id in supplied.items():
            # Preflight the Ligature this requirement will become, so
            # relate() cannot fail after the main atom is created: the
            # support must exist, be live, and be ligature-eligible
            # (Core refuses Current assertions as relationship args).
            try:
                raw = self.api.get_raw(atom_id)
            except UnknownAtomError:
                raise UnknownAtomError(
                    f"{name} requirement {key!r} names unknown atom {atom_id!r}"
                ) from None
            if raw.deleted:
                raise UnknownAtomError(
                    f"{name} requirement {key!r} names deleted atom {atom_id!r}"
                )
            support = raw.atom
            if (
                isinstance(support, Predicate)
                and support.predicate == self.api.current_predicate
            ):
                raise InvalidAtomOperationError(
                    f"{name} requirement {key!r} names a Current assertion, "
                    "which cannot be a relationship argument"
                )
        return supplied

    def relate(
        self,
        predicate: AtomId,
        left: AtomId,
        right: AtomId,
        *,
        label: Optional[str] = None,
        confidence: float = 1.0,
        **requirements: AtomId,
    ) -> AtomId:
        """Assert one obligation using this vocabulary's canonicalization.

        Required supporting atoms are passed by requirement name, e.g.
        ``relate(mod.Obligated, elena, clients, reason=deposits)``.  Each
        supplied support is recorded as a Ligature from the asserted atom
        to the supporting atom, named for the requirement.
        """
        name = self._names.get(predicate)
        if name is None:
            raise TypeError("predicate is not part of the obligation vocabulary")
        checked = self._check_requirements(name, requirements)
        atom_id = self.rules.create_predicate(
            predicate,
            left,
            right,
            label=label,
            confidence=confidence,
        )
        for key, support_id in checked.items():
            self.api.create_ligature(key.capitalize(), atom_id, support_id)
        return atom_id

    create_predicate = relate
    create_link = relate

    def has(self, predicate: AtomId, left: AtomId, right: AtomId) -> bool:
        """Query an obligation using rules without materializing inferences."""
        return self.rules.has_predicate(predicate, left, right)

    has_predicate = has
    has_link = has


def install(api: AtomSpaceAPI) -> ObligationPredicates:
    """Install and return an obligation vocabulary for ``api``."""
    installed = _INSTALLATIONS.get(api)
    if installed is None:
        installed = ObligationPredicates(api)
        _INSTALLATIONS[api] = installed
    return installed


install_obligation_predicates = install
Obligation = ObligationPredicates

__all__ = [
    "ObligationPredicates", "Obligation", "install",
    "install_obligation_predicates",
]
