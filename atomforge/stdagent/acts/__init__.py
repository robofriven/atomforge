"""Act predicate vocabulary: acts as canonical atoms, not predicates.

Presupposes actors — agents that do things.  Act types are unbounded
vocabulary in the world, but they are NOT unbounded in the schema:
minting one predicate per act (``Hugs``, ``ProposesTo``, ``DrivesTo``,
...) is the over-predicating smell the feels module was built to avoid,
and letting every caller coin act *terms* freely is the same smell one
level down — the v2 brain grew 100 act labels for 191 occurrences,
most of them one-off phrases with occasions, recipients, and scene
flavor soldered into the label.  The v3 cure:

- An act type is a ``Node`` atom of kind ``Act`` (or of the subkind
  ``SexAct``), minted only through :meth:`ActPredicates.act_node`.
- **Minting is gated by an approved vocabulary.**  The vocabulary is
  data — by default the packaged ``vocabulary.json`` beside this
  module, derived from the human-approved term list — never strings
  scattered through code.  A label already standing in the graph as an
  Act node always resolves (deduplication is not minting; consent's
  exempt act atoms rely on this).  A label in the vocabulary mints a
  term node of the right kind with its IsA parents asserted.  A label
  in neither place is **refused and queued**: the attempt is recorded
  in the installation's proposal queue (see
  :meth:`ActPredicates.proposals`) and :class:`UnapprovedTermError`
  is raised.  Nothing is silently minted, and nothing is normalized
  or merged after the fact — a queued term enters the vocabulary only
  by a human decision (:meth:`ActPredicates.approve_term`, or a new
  vocabulary edition).
- The one mechanism predicate is ``Does(actor, act)``.

``SexAct`` is a real schema kind: ``IsA(SexAct, Act)`` at the kind
level, asserted lazily the first time a SexAct term is minted, so
``Does`` covers every sex act by kind inheritance.  Taxonomy below
the kind level is IsA among term nodes (``fellatio`` IsA ``oral``),
asserted from the vocabulary's parent lists when a term is minted.

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

Depends on Core and the relational vocabulary: kind checks are
IsA-aware — a node whose kind sits below Act in the IsA hierarchy
validates as an act.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple, Union
from weakref import WeakKeyDictionary

from ...atoms import AtomId, Predicate
from ...facade import AtomSpaceAPI
from ...infrastructure import InvalidAtomOperationError, UnknownAtomError
from ...rules.generic import RuleSet
from ..relational import install as install_relational


_ACT_SPECS = {
    "Does": ("actor", "act"),
}

#: The packaged approved term vocabulary (vocabulary draft v3).
VOCABULARY_PATH = Path(__file__).with_name("vocabulary.json")

_KIND_NAMES = ("Act", "SexAct")

_INSTALLATIONS: "WeakKeyDictionary[AtomSpaceAPI, ActPredicates]" = (
    WeakKeyDictionary()
)


class UnapprovedTermError(TypeError):
    """An act label was refused: not in the graph, not in the
    approved vocabulary.  The label has been recorded in the
    installation's proposal queue for human review."""


class _Term:
    """One approved vocabulary term: its label, its kind, and the
    labels (or kind names) it sits under in the IsA taxonomy."""

    __slots__ = ("label", "kind", "parents")

    def __init__(self, label: str, kind: str, parents: Tuple[str, ...]):
        self.label = label
        self.kind = kind
        self.parents = parents


def _normalize_vocabulary(source) -> Dict[str, _Term]:
    """Normalize a vocabulary source into ``{label: _Term}``.

    Accepted sources: ``None`` (the packaged vocabulary), a path to a
    vocabulary JSON file, a mapping with a ``"terms"`` list, a list
    of term mappings, or an iterable of bare labels (each an ``Act``
    term with no term parents).
    """
    if source is None:
        source = VOCABULARY_PATH
    if isinstance(source, (str, Path)):
        with open(source, "r", encoding="utf-8") as handle:
            source = json.load(handle)
    if isinstance(source, Mapping):
        entries = source.get("terms", [])
    else:
        entries = list(source)
    terms: Dict[str, _Term] = {}
    for entry in entries:
        if isinstance(entry, str):
            terms[entry] = _Term(entry, "Act", ("Act",))
            continue
        label = entry["label"]
        kind = entry.get("kind", "Act")
        if kind not in _KIND_NAMES:
            raise TypeError(
                f"vocabulary term {label!r} names unknown kind {kind!r}"
            )
        parents = tuple(entry.get("parents", (kind,)))
        terms[label] = _Term(label, kind, parents)
    return terms


class ActPredicates:
    """Installed act vocabulary bound to one :class:`AtomSpaceAPI`."""

    def __init__(
        self, api: AtomSpaceAPI, vocabulary=None, _vocabulary_key=None
    ) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self.api = api
        self._vocabulary_key = _vocabulary_key
        self._terms: Dict[str, _Term] = _normalize_vocabulary(vocabulary)
        self._proposals: List[str] = []
        self.predicates: Dict[str, AtomId] = {}
        for name, roles in _ACT_SPECS.items():
            predicate = api.predicate(name, arity=2, roles=roles)
            self.predicates[name] = predicate
            setattr(self, name, predicate)
        self._names = {predicate: name for name, predicate in self.predicates.items()}
        self.act_kind = api.kind("Act")
        self.sex_act_kind = api.kind("SexAct")
        self.relational = install_relational(api)

        self.rules = RuleSet(api)

    def __getitem__(self, name: str) -> AtomId:
        return self.predicates[name]

    # -- vocabulary ------------------------------------------------------------

    def vocabulary_terms(self) -> List[str]:
        """Return the labels this installation may mint."""
        return sorted(self._terms)

    def proposals(self) -> List[str]:
        """Return the labels refused so far, in first-refusal order:
        the human review queue of candidate terms."""
        return list(self._proposals)

    def approve_term(
        self,
        label: str,
        *,
        kind: str = "Act",
        parents: Iterable[str] = (),
    ) -> None:
        """Admit ``label`` to this installation's vocabulary — the
        human gate acting on the proposal queue.  Runtime admission
        only; a durable term belongs in the vocabulary data."""
        if not isinstance(label, str) or not label:
            raise TypeError("term label must be a non-empty string")
        if kind not in _KIND_NAMES:
            raise TypeError(f"unknown act kind {kind!r}")
        parent_tuple = tuple(parents) or (kind,)
        self._terms[label] = _Term(label, kind, parent_tuple)
        if label in self._proposals:
            self._proposals.remove(label)

    def _ensure_sex_act_kind(self) -> None:
        """Assert ``IsA(SexAct, Act)`` at the kind level, once.

        Lazy on purpose: merely installing this module must not write
        taxonomy into a graph (a hand-built SexAct subkind only joins
        the Act hierarchy when the factory's taxonomy is exercised —
        or when a caller asserts the edge themselves)."""
        if not self.relational.has(
            self.relational.IsA, self.sex_act_kind, self.act_kind
        ):
            self.relational.relate(
                self.relational.IsA, self.sex_act_kind, self.act_kind
            )

    def _mint_term(self, term: _Term) -> AtomId:
        """Mint a vocabulary term node with its IsA parents asserted.

        Parent terms are minted recursively (hubs before leaves);
        a parent naming a kind resolves to that kind atom itself."""
        if term.kind == "SexAct":
            self._ensure_sex_act_kind()
        existing = self._find_act_node(term.label)
        if existing is not None:
            return existing
        kind_atom = (
            self.sex_act_kind if term.kind == "SexAct" else self.act_kind
        )
        node = self.api.create_node(term.label, kind=kind_atom)
        for parent in term.parents:
            if parent in _KIND_NAMES:
                parent_atom = (
                    self.sex_act_kind if parent == "SexAct"
                    else self.act_kind
                )
            else:
                parent_term = self._terms.get(parent)
                if parent_term is None:
                    raise TypeError(
                        f"vocabulary term {term.label!r} names unknown "
                        f"parent term {parent!r}"
                    )
                parent_atom = self._mint_term(parent_term)
            if parent_atom != node:
                self.relational.relate(
                    self.relational.IsA, node, parent_atom
                )
        return node

    def _find_act_node(self, text: str) -> Optional[AtomId]:
        for atom_id in self.api.find_by_label(text):
            if self.relational.kind_is_a(atom_id, self.act_kind):
                return atom_id
        return None

    # -- act atoms -------------------------------------------------------------

    def act_node(self, text: str) -> AtomId:
        """Return the act atom for a piece of text.

        Resolution order: an Act node already standing in the graph
        with this label wins (deduplication — never a mint); a label
        in the approved vocabulary mints its term node; anything else
        is refused — the label joins the proposal queue and
        :class:`UnapprovedTermError` is raised.
        """
        if not isinstance(text, str) or not text:
            raise TypeError("act text must be a non-empty string")
        existing = self._find_act_node(text)
        if existing is not None:
            return existing
        term = self._terms.get(text)
        if term is not None:
            return self._mint_term(term)
        if text not in self._proposals:
            self._proposals.append(text)
        raise UnapprovedTermError(
            f"act label {text!r} is not in the approved vocabulary; "
            "it has been queued as a term proposal instead of minted"
        )

    def is_act(self, atom_id: AtomId) -> bool:
        """Return whether ``atom_id`` is a live ``Act`` node — or a
        node under a subkind of Act in the IsA hierarchy."""
        return self.relational.kind_is_a(atom_id, self.act_kind)

    def _resolve_act(self, act: Union[AtomId, str]) -> AtomId:
        if isinstance(act, str):
            return self.act_node(act)
        self._check_atom(act, "act")
        if not self.relational.kind_is_a(act, self.act_kind):
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


def _vocabulary_key(vocabulary) -> object:
    """A comparable identity for an install-time vocabulary argument,
    so a second install() naming a *different* vocabulary fails loud
    instead of silently returning the first installation."""
    if vocabulary is None:
        return ("packaged",)
    if isinstance(vocabulary, (str, Path)):
        return ("path", str(vocabulary))
    if isinstance(vocabulary, Mapping):
        return ("mapping", id(vocabulary))
    return ("terms", tuple(sorted(str(v) for v in vocabulary)))


def install(api: AtomSpaceAPI, vocabulary=None) -> ActPredicates:
    """Install and return an act vocabulary for ``api``.

    ``vocabulary`` selects the approved term list for the gated
    factory: ``None`` for the packaged vocabulary, or any source
    :func:`_normalize_vocabulary` accepts (a vocabulary file path, a
    mapping, term entries, or bare labels).  One installation serves
    one vocabulary; installing again with a different one raises.
    """
    installed = _INSTALLATIONS.get(api)
    if installed is not None:
        if vocabulary is not None and \
                _vocabulary_key(vocabulary) != installed._vocabulary_key:
            raise TypeError(
                "acts already installed on this api with a different "
                "vocabulary"
            )
        return installed
    installed = ActPredicates(
        api, vocabulary, _vocabulary_key=_vocabulary_key(vocabulary)
    )
    _INSTALLATIONS[api] = installed
    return installed


install_act_predicates = install
Acts = ActPredicates

__all__ = [
    "ActPredicates", "Acts", "UnapprovedTermError", "VOCABULARY_PATH",
    "install", "install_act_predicates",
]
