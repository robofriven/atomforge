"""Consent: one grant predicate, holder-symmetric, provenance first-class.

A domain vocabulary.  It presupposes agents, act types as canonical
``Act`` nodes (``stdagent.acts``), and speech — consent is normally
*declared*, and a declaration is a ``Says`` atom.  It deliberately does
NOT presuppose any taxonomy of acts: no kind check gates consent.  A
mis-classified act must never orphan a consent fact, so the module
checks the *form* of a consent assertion and leaves the meaning of the
act to the categorizer that minted it.

The predicates, all ``(holder, act)``:

- ``ConsentGranted(holder, act)`` — the single grant predicate.  It
  records the holder's own participation in the act, and nothing else.
  Because the first argument is always the person whose consent it is,
  actor-side self-authorization — "I have given consent to myself to
  do this to you" — is grammatically inexpressible: consent for an act
  done to a person exists only as that person's own atom, hanging from
  that person's own statement.  The predicate is holder-symmetric —
  the same shape serves every holder, and a shared act reads as
  consented only while every participant's own grant stands.
- ``HardLimit(holder, act)`` — categorical refusal.  The act is off
  the table for this holder, full stop.  A hard limit stands until
  its holder lifts it by statement; it is never presumed lapsed.
- ``ConsentRevoked(holder, act)`` — a revocation, written only by
  :meth:`ConsentPredicates.revoke`.  Revocation (the Red signal)
  withdraws a standing grant *until stated otherwise*: the revoked
  state persists until a new grant statement supersedes it.  The
  other signals of an in-scene signal system (e.g. Yellow, "please
  slow down / pause") are NOT consent operations and do not belong to
  this module: a Yellow changes pacing, not the grant, and is recorded
  as a scene event in the remembering layer.

Facts and records.  Core deduplicates predicate applications: one
``ConsentGranted(holder, act)`` atom is the canonical fact, the index
every query speaks.  But consent is *stated*, often more than once —
granted, revoked, granted again — and each statement has its own
provenance and its own window.  So every statement is also a record:
a ``ConsentRecord`` node carrying that statement's hangers, linked
from the canonical atom by a ``Statement`` ligature.  Records chain
by Transition (grant record → revocation record → re-grant record),
so consent state at any point in the timeline reads correctly and the
whole history stays walkable.  Nothing is ever deleted or edited.

Renaming restatements are a distinct record type, not a re-grant:
when a category is coined mid-stream, the naming scene mints a
restatement record Transition-chained to the original record,
carrying the new term — "the thing we granted back then, we now call
secret play."  The restatement is a genuine grant statement on the
new term (see :meth:`ConsentPredicates.restate_grant`): it inherits
the original's recipient, window, and exclusions, so
:meth:`consent_state` on the new term reads ``"granted"`` from the
naming scene onward and ``"none"`` before it — the name did not exist
yet, and that honest blank is not a failure.  No past atom is
rewritten, the original grant's state is unchanged, and a restatement
never revokes: its predecessor is a grant record, never a revocation
record, and no ``ConsentRevoked`` atom is written.

Every grant statement carries its provenance as required data
("hangers"), enforced at write time — a grant missing any of them is
refused before anything is written:

- ``to`` — who the consent is given to.  Consent is addressed, never
  floating.  At write time the recipient must be determinate: passed
  explicitly, or resolved from the installation's ``owner`` (grants in
  a graph are presumed addressed to the graph's owner unless a
  different recipient is named).
- ``statement`` — the reference to where the grant was stated.  For a
  declared grant this is the holder's own ``Says`` atom (anyone else's
  words are refused: one agent's words cannot ground another's
  consent).  For an enacted grant (``mode="enacted"``) it is the
  scene / performance atom where the holder's own active
  participation grounds the record.  Either way the statement is
  recorded as evidence (epistemic ``EvidenceFor``).
- ``stated_on`` — the statement date, in WXDY format (``W<week>D<day>``).
- ``expires`` — the explicit end of the active window.  Every grant
  must answer "until when" at creation: a WXDY date, or the reserved
  sentinel :data:`NEVER_EXPIRES` (``W999D999``) for standing consent.
  A grant with no decided window cannot be written at all.  An
  optional ``active_from`` (default: ``stated_on``) opens the window
  later than the statement date.

Modes.  A declared grant projects forward across its window.  An
enacted grant is a retrospective record only: it testifies that one
occasion was consensual and never licenses a future one — its window
is the occasion, and outside that window it reads as expired history.
Yeses expire; nos persist.  Where no grant and no refusal stand,
:meth:`consent_state` answers ``"none"`` — an honest blank, never an
implied yes.  Consent is never inferred into existence by this module.

Scope.  A grant's act argument may be a single act node, or a kind
atom — consent addressed to a kind covers its member acts (resolved
through the relational ``IsA`` closure at query time): blanket
consent.  Exclusions are first-class data riding on the grant record
(``Excludes`` ligatures, read back by :meth:`exclusions_of`) and
outrank the grant they qualify, blanket grants included.  Excluding
the very act being granted is refused.

Consent is not preference, and the two vocabularies must not be
conflated: ``Likes`` is not permission and ``Dislikes`` is not
prohibition.  Neither module derives the other's answers.  Consent
about *other* people — a grant between two third parties that this
graph's holder merely knows about — never stands bare in this
vocabulary: it is knowledge, wrapped in ``Believes`` / ``Knows`` with
the receiving party hanging off the inner claim.  Bare consent atoms
are operative; wrapped ones are testimony.

Conflicts are preserved, not resolved.  Asserting a grant where a
``HardLimit`` already stands on the same holder and act — or the
reverse — records a ``Contradicts`` atom between the two assertions:
both stay in the graph, and :meth:`consent_state` reports
``"conflicted"`` rather than silently picking a winner.

Consent data is redundant on purpose.  Grant, declaration, scope and
exclusions are all stored explicitly even when one is derivable from
another; this vocabulary is exempt from the usual austerity rule,
because a missed consent fact is the one silent failure the system
must not have.

Depends on stdagent acts (act vocabulary), speech (declaration
checks), epistemic (EvidenceFor grounding), logic (Contradicts), and
relational (kind closure for blanket scope).  None of those depend on
this module.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Tuple
from weakref import WeakKeyDictionary

from ...atoms import AtomId, KindAtom, Ligature, Predicate
from ...facade import AtomSpaceAPI
from ...infrastructure import InvalidAtomOperationError, UnknownAtomError
from ...rules.generic import RuleSet
from ...stdagent.acts import install as install_acts
from ...stdagent.epistemic import install as install_epistemic
from ...stdagent.logic import install as install_logic
from ...stdagent.relational import install as install_relational
from ...stdagent.speech import install as install_speech


#: Reserved expiry sentinel: standing consent with no expiry.  A
#: WXDY-shaped value later than any real timeline date, so window
#: arithmetic never needs a special case — and never a writable date,
#: so no real statement can be mistaken for it.
NEVER_EXPIRES = "W999D999"

_DATE_RE = re.compile(r"^W(\d+)D(\d+)$")

_CONSENT_SPECS = {
    "ConsentGranted": ("holder", "act"),
    "HardLimit": ("holder", "act"),
    "ConsentRevoked": ("holder", "act"),
}

# Asserting one side where the other already stands (same holder,
# same act) is a recorded contradiction.
_OPPOSES = {
    "HardLimit": ("ConsentGranted",),
    "ConsentGranted": ("HardLimit",),
}

_MODES = ("declared", "enacted")

_INSTALLATIONS: "WeakKeyDictionary[AtomSpaceAPI, ConsentPredicates]" = (
    WeakKeyDictionary()
)


def wxdy_key(date: str) -> Tuple[int, int]:
    """Return the ordering key for a WXDY date string.

    Raises :class:`TypeError` on anything that is not a well-formed
    ``W<week>D<day>`` date — dates in this module fail loud, never
    guess.
    """
    if not isinstance(date, str):
        raise TypeError(f"WXDY date must be a string, got {date!r}")
    match = _DATE_RE.match(date)
    if match is None:
        raise TypeError(
            f"malformed WXDY date {date!r}; expected W<week>D<day>"
        )
    return (int(match.group(1)), int(match.group(2)))


class ConsentPredicates:
    """Installed consent vocabulary bound to one :class:`AtomSpaceAPI`.

    ``owner`` names the graph's owner: the standing default recipient
    for grants written into this graph.  It may be set here, via
    :func:`install`, or assigned to the instance later; a grant whose
    recipient is neither passed nor resolvable from ``owner`` is
    refused.
    """

    def __init__(
        self, api: AtomSpaceAPI, owner: Optional[AtomId] = None
    ) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self.api = api
        self.owner = owner
        self.acts = install_acts(api)
        self.speech = install_speech(api)
        self.epistemic = install_epistemic(api)
        self.logic = install_logic(api)
        self.relational = install_relational(api)
        self.date_kind = api.kind("Date")
        self.mode_kind = api.kind("ConsentMode")
        self.record_kind = api.kind("ConsentRecord")
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
        """A consent target is an Act node, or a kind atom (blanket
        scope).  There is deliberately no check of *which* kind an act
        node carries: taxonomy never gates consent."""
        self._check_atom(act, "act")
        atom = self.api.get(act)
        if isinstance(atom, KindAtom):
            return
        if not self.acts.is_act(act):
            raise TypeError(
                "consent target must be an Act node or a kind atom; "
                "mint act nodes with the acts module's act_node()"
            )

    def _check_statement(self, statement: AtomId, holder: AtomId,
                         mode: str) -> None:
        self._check_atom(statement, "statement")
        if self.speech.is_saying(statement):
            if self.speech.speaker_of(statement) != holder:
                raise TypeError(
                    "statement speaker is not the consent holder: "
                    "one agent's words cannot ground another's consent"
                )
        elif mode == "declared":
            raise TypeError(
                "a declared grant's statement must be a Says atom "
                "by the holder"
            )
        # An enacted grant's statement is the scene / performance atom
        # where the holder's participation grounds the record; any
        # live atom may name it.

    # -- small atoms: dates, modes ----------------------------------------------

    def date_node(self, date: str) -> AtomId:
        """Return the shared ``Date`` atom for a WXDY string, minting
        it if new.  Dates are atoms so they act as join points:
        everything stated on a date hangs off the same atom."""
        wxdy_key(date)  # validates; raises on malformed input
        for atom_id in self.api.find_by_label(date):
            if self.relational.kind_is_a(atom_id, self.date_kind):
                return atom_id
        return self.api.create_node(date, kind=self.date_kind)

    def _mode_node(self, mode: str) -> AtomId:
        for atom_id in self.api.find_by_label(mode):
            if self.relational.kind_is_a(atom_id, self.mode_kind):
                return atom_id
        return self.api.create_node(mode, kind=self.mode_kind)

    # -- hanger I/O ---------------------------------------------------------------

    def _hang(self, atom_id: AtomId, name: str, target: AtomId) -> None:
        self.api.create_ligature(name, atom_id, target)

    def _ligature_targets(self, atom_id: AtomId, name: str) -> List[AtomId]:
        found: List[AtomId] = []
        for ligature_id in self.api.in_ligatures(atom_id):
            ligature = self.api.get(ligature_id)
            if isinstance(ligature, Ligature) \
                    and ligature.name == name \
                    and len(ligature.args) == 2 \
                    and ligature.args[0] == atom_id:
                found.append(ligature.args[1])
        return found

    def _one_hanger(self, atom_id: AtomId, name: str) -> Optional[AtomId]:
        targets = self._ligature_targets(atom_id, name)
        return targets[0] if targets else None

    def _date_hanger(self, atom_id: AtomId, name: str) -> Optional[str]:
        target = self._one_hanger(atom_id, name)
        if target is None:
            return None
        return self.api.get(target).label

    def _is_record(self, atom_id: AtomId) -> bool:
        atom = self.api.get(atom_id)
        return not isinstance(atom, (Predicate, KindAtom)) \
            and self.relational.kind_is_a(atom_id, self.record_kind)

    def records_of(self, consent_atom: AtomId) -> List[AtomId]:
        """Return the statement records hanging off a canonical
        ``ConsentGranted`` / ``ConsentRevoked`` atom, oldest first."""
        records = self._ligature_targets(consent_atom, "Statement")
        return sorted(records)

    def hangers_of(self, atom_id: AtomId) -> Dict[str, object]:
        """Read back a consent statement's hangers as plain data:
        recipient and statement as atom ids, dates as WXDY strings,
        mode and note as text, exclusions as a list of atom ids.

        Accepts a record atom directly, a canonical grant/revocation
        atom (its latest statement's hangers), or a ``HardLimit``
        atom (whose hangers ride on the atom itself)."""
        if not self._is_record(atom_id):
            records = self.records_of(atom_id)
            if records:
                atom_id = records[-1]
        note = self._one_hanger(atom_id, "Note")
        mode = self._one_hanger(atom_id, "Mode")
        return {
            "to": self._one_hanger(atom_id, "GrantedTo"),
            "statement": self._one_hanger(atom_id, "StatedIn"),
            "stated_on": self._date_hanger(atom_id, "StatedOn"),
            "active_from": self._date_hanger(atom_id, "ActiveFrom"),
            "expires": self._date_hanger(atom_id, "ExpiresOn"),
            "mode": self.api.get(mode).label if mode is not None else None,
            "note": self.api.get(note).label if note is not None else None,
            "excludes": self.exclusions_of(atom_id),
        }

    def exclusions_of(self, consent_atom: AtomId) -> List[AtomId]:
        """Return the exclusion atoms recorded on a consent assertion
        (for a canonical grant atom: on its latest statement record)."""
        if not self._is_record(consent_atom):
            records = self.records_of(consent_atom)
            if records:
                consent_atom = records[-1]
        return self._ligature_targets(consent_atom, "Excludes")

    # -- assertion -----------------------------------------------------------

    def grant(
        self,
        holder: AtomId,
        act: AtomId,
        *,
        to: Optional[AtomId] = None,
        statement: AtomId,
        stated_on: str,
        expires: str,
        active_from: Optional[str] = None,
        mode: str = "declared",
        excludes: Iterable[AtomId] = (),
        note: Optional[str] = None,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert a ``ConsentGranted`` statement with its full
        required hangers, and return the canonical grant atom.

        Everything is validated before any atom is written, so a
        refused grant leaves the graph untouched.  ``to`` may be
        omitted only when the installation's ``owner`` resolves it.
        ``expires`` must be a WXDY date or :data:`NEVER_EXPIRES` —
        there is no default window.  A grant stated after a revocation
        of the same holder and act supersedes it: the revocation
        record is Transition-chained to the new grant record.
        """
        return self.relate(
            self.ConsentGranted, holder, act,
            to=to, statement=statement, stated_on=stated_on,
            expires=expires, active_from=active_from, mode=mode,
            excludes=excludes, note=note, label=label,
            confidence=confidence,
        )

    def hard_limit(
        self,
        holder: AtomId,
        act: AtomId,
        *,
        declaration: Optional[AtomId] = None,
        excludes: Iterable[AtomId] = (),
        note: Optional[str] = None,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Assert a ``HardLimit``, optionally grounded in the holder's
        own declaration."""
        return self.relate(
            self.HardLimit, holder, act,
            declaration=declaration, excludes=excludes, note=note,
            label=label, confidence=confidence,
        )

    def relate(
        self,
        predicate: AtomId,
        holder: AtomId,
        act: AtomId,
        **kwargs,
    ) -> AtomId:
        """Assert one consent predicate, with FTFO validation.

        ``ConsentGranted`` requires the full hanger set (see
        :meth:`grant`); ``HardLimit`` takes an optional ``declaration``.
        ``ConsentRevoked`` cannot be asserted directly — it is written
        only by :meth:`revoke`, so a revocation always names the grant
        it withdraws.
        """
        name = self._names.get(predicate)
        if name is None:
            raise TypeError("predicate is not part of the consent vocabulary")
        if name == "ConsentRevoked":
            raise TypeError(
                "ConsentRevoked is written only by revoke(): a "
                "revocation must name the grant it withdraws"
            )
        if name == "ConsentGranted":
            return self._relate_grant(holder, act, **kwargs)
        return self._relate_hard_limit(holder, act, **kwargs)

    create_predicate = relate
    create_link = relate

    def _validate_exclusions(
        self, act: AtomId, excludes: Iterable[AtomId]
    ) -> List[AtomId]:
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
        return exclusions

    @staticmethod
    def _validate_note(note: Optional[str]) -> None:
        if note is not None and (not isinstance(note, str) or not note):
            raise TypeError("note must be a non-empty string")

    def _new_record(self, label: Optional[str]) -> AtomId:
        return self.api.create_node(
            label if label is not None else "consent statement",
            kind=self.record_kind,
        )

    def _relate_grant(
        self,
        holder: AtomId,
        act: AtomId,
        *,
        to: Optional[AtomId] = None,
        statement: AtomId,
        stated_on: str,
        expires: str,
        active_from: Optional[str] = None,
        mode: str = "declared",
        excludes: Iterable[AtomId] = (),
        note: Optional[str] = None,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        if mode not in _MODES:
            raise TypeError(
                f"consent mode must be one of {_MODES}, got {mode!r}"
            )
        recipient = to if to is not None else self.owner
        if recipient is None:
            raise TypeError(
                "grant has no recipient: pass to= or install the "
                "consent vocabulary with an owner — consent is "
                "addressed, never floating"
            )
        # Validate every hanger before writing anything.
        self._check_atom(holder, "holder")
        self._check_act(act)
        self._check_atom(recipient, "recipient")
        self._check_statement(statement, holder, mode)
        stated_key = wxdy_key(stated_on)
        expires_key = wxdy_key(expires)
        active_from = stated_on if active_from is None else active_from
        active_key = wxdy_key(active_from)
        if active_key < stated_key:
            raise TypeError(
                "active_from precedes stated_on: a grant cannot open "
                "before it was stated"
            )
        if expires_key < active_key:
            raise TypeError(
                "expires precedes the window opening: an empty "
                "consent window is a data error, not a grant"
            )
        exclusions = self._validate_exclusions(act, excludes)
        self._validate_note(note)

        atom_id = self.rules.create_predicate(
            self.ConsentGranted, holder, act,
            label=None, confidence=confidence,
        )
        record = self._new_record(label)
        self._hang(atom_id, "Statement", record)
        self._hang(record, "GrantedTo", recipient)
        self._hang(record, "StatedIn", statement)
        self._hang(record, "StatedOn", self.date_node(stated_on))
        self._hang(record, "ActiveFrom", self.date_node(active_from))
        self._hang(record, "ExpiresOn", self.date_node(expires))
        self._hang(record, "Mode", self._mode_node(mode))
        for excluded in exclusions:
            self._hang(record, "Excludes", excluded)
        if note is not None:
            self._hang(record, "Note", self.speech.claim_node(note))
        self.epistemic.evidence_for(atom_id, statement)
        self.epistemic.evidence_for(record, statement)
        self._record_conflicts(atom_id, "ConsentGranted", holder, act)
        self._chain_regrant(record, holder, act, stated_key)
        return atom_id

    def _relate_hard_limit(
        self,
        holder: AtomId,
        act: AtomId,
        *,
        declaration: Optional[AtomId] = None,
        excludes: Iterable[AtomId] = (),
        note: Optional[str] = None,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        self._check_atom(holder, "holder")
        self._check_act(act)
        exclusions = self._validate_exclusions(act, excludes)
        if declaration is not None:
            self._check_statement(declaration, holder, "declared")
        self._validate_note(note)

        atom_id = self.rules.create_predicate(
            self.HardLimit, holder, act,
            label=label, confidence=confidence,
        )
        for excluded in exclusions:
            self._hang(atom_id, "Excludes", excluded)
        if note is not None:
            self._hang(atom_id, "Note", self.speech.claim_node(note))
        if declaration is not None:
            self._hang(atom_id, "StatedIn", declaration)
            self.epistemic.evidence_for(atom_id, declaration)
        self._record_conflicts(atom_id, "HardLimit", holder, act)
        return atom_id

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

    def _chain_regrant(
        self, record: AtomId, holder: AtomId, act: AtomId,
        stated_key: Tuple[int, int],
    ) -> None:
        """A grant stated after a revocation covering the same holder
        and act supersedes it ("until stated otherwise"): chain the
        revocation record to the new grant record so the timeline
        stays walkable."""
        for revocation in self._assertions("ConsentRevoked", holder):
            if not self._covers(self.api.get(revocation).args[1], act):
                continue
            for old_record in self.records_of(revocation):
                hangers = self.hangers_of(old_record)
                revoked_on = hangers["stated_on"]
                if revoked_on is None \
                        or wxdy_key(revoked_on) > stated_key:
                    continue
                already = any(
                    self.api.transition_args(t)[1] == record
                    for t in self.api.in_transitions(record)
                )
                if not already:
                    self.api.transition(old_record, record)

    # -- revocation ------------------------------------------------------------

    def revoke(
        self,
        holder: AtomId,
        act: AtomId,
        *,
        statement: AtomId,
        stated_on: str,
        note: Optional[str] = None,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Revoke the standing grant covering ``(holder, act)``, and
        return the canonical ``ConsentRevoked`` atom.

        ``statement`` is the holder's own revocation utterance (a
        ``Says`` atom — Red is spoken by the holder, and anyone else's
        words are refused).  The revocation record is
        Transition-chained from the grant record it withdraws and
        stands until a later grant supersedes it.  Raises when no
        grant stands to be revoked: a refusal of something never
        granted is a ``HardLimit`` or a scene event, not a revocation,
        and the caller must say which.
        """
        self._check_atom(holder, "holder")
        self._check_act(act)
        self._check_statement(statement, holder, "declared")
        stated_key = wxdy_key(stated_on)
        self._validate_note(note)

        governing = self._governing_record(holder, act, stated_key)
        if governing is None:
            raise InvalidAtomOperationError(
                "nothing standing to revoke: no grant covers this "
                "holder and act at that date"
            )

        atom_id = self.rules.create_predicate(
            self.ConsentRevoked, holder, act,
            label=None, confidence=confidence,
        )
        record = self._new_record(label)
        self._hang(atom_id, "Statement", record)
        self._hang(record, "StatedIn", statement)
        self._hang(record, "StatedOn", self.date_node(stated_on))
        if note is not None:
            self._hang(record, "Note", self.speech.claim_node(note))
        self.epistemic.evidence_for(atom_id, statement)
        self.epistemic.evidence_for(record, statement)
        self.api.transition(governing, record)
        return atom_id

    # -- renaming restatement ------------------------------------------------

    def restate_grant(
        self,
        holder: AtomId,
        old_act: AtomId,
        new_act: AtomId,
        *,
        statement: AtomId,
        stated_on: str,
        note: Optional[str] = None,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        """Restate a standing grant under a term coined mid-stream,
        and return the canonical ``ConsentGranted`` atom on the new
        term.

        The naming scene mints a restatement record Transition-chained
        to the original (governing) record, carrying the new term:
        "the thing we granted back then, we now call this."  The
        restatement inherits the original's recipient, window
        (``active_from`` / ``expires``), and exclusions, and is
        marked with mode ``"restated"`` plus a ``Restates`` ligature
        to the original record.  No past atom is rewritten and the
        original grant's state is unchanged.

        This is DISTINCT from a revoke-restate: its predecessor is a
        grant record, never a revocation record, and no
        ``ConsentRevoked`` atom is written.  It also never resurrects
        a revoked or expired grant: the original must be standing at
        the naming date, or the restatement is refused.

        Because the restatement is a genuine grant statement on the
        new term, :meth:`consent_state` needs no special case: on the
        new term it reads ``"none"`` before the naming scene (the
        name did not exist yet) and the grant's state from the naming
        scene onward.  The recipient is inherited, never re-decided,
        so there is no ``to`` argument.
        """
        if old_act == new_act:
            raise TypeError(
                "a restatement must rename: new term is the same "
                "act as the original"
            )
        self._check_atom(holder, "holder")
        self._check_act(old_act)
        self._check_act(new_act)
        self._check_statement(statement, holder, "declared")
        stated_key = wxdy_key(stated_on)
        self._validate_note(note)

        governing = self._governing_record(holder, old_act, stated_key)
        if governing is None:
            raise InvalidAtomOperationError(
                "nothing standing to restate: no grant covers this "
                "holder and act at that date"
            )
        original = self.hangers_of(governing)
        recipient = original["to"]
        if recipient is None:
            raise InvalidAtomOperationError(
                "governing record names no recipient: cannot restate "
                "an unaddressed grant"
            )
        active_from = original["active_from"] or original["stated_on"]
        expires = original["expires"]
        if active_from is None or expires is None:
            raise InvalidAtomOperationError(
                "governing record names no window: cannot restate "
                "a grant without one"
            )

        atom_id = self.rules.create_predicate(
            self.ConsentGranted, holder, new_act,
            label=None, confidence=confidence,
        )
        record = self._new_record(label)
        self._hang(atom_id, "Statement", record)
        self._hang(record, "GrantedTo", recipient)
        self._hang(record, "StatedIn", statement)
        self._hang(record, "StatedOn", self.date_node(stated_on))
        self._hang(record, "ActiveFrom", self.date_node(active_from))
        self._hang(record, "ExpiresOn", self.date_node(expires))
        self._hang(record, "Mode", self._mode_node("restated"))
        self._hang(record, "Restates", governing)
        for excluded in original["excludes"]:
            self._hang(record, "Excludes", excluded)
        if note is not None:
            self._hang(record, "Note", self.speech.claim_node(note))
        self.epistemic.evidence_for(atom_id, statement)
        self.epistemic.evidence_for(record, statement)
        self.api.transition(governing, record)
        self._record_conflicts(atom_id, "ConsentGranted", holder, new_act)
        return atom_id

    # -- queries ---------------------------------------------------------------

    def has(self, predicate: AtomId, left: AtomId, right: AtomId) -> bool:
        if predicate not in self._names:
            raise TypeError("predicate is not part of the consent vocabulary")
        return self.rules.has_predicate(predicate, left, right)

    has_predicate = has
    has_link = has

    def _assertions(
        self, name: str, holder: AtomId, act: Optional[AtomId] = None
    ) -> List[AtomId]:
        found: List[AtomId] = []
        for result in self.api.search(predicate=self.predicates[name]):
            atom = result.atom
            if isinstance(atom, Predicate) and atom.args[0] == holder:
                if act is None or atom.args[1] == act:
                    found.append(atom.id)
        return found

    def grants_of(self, holder: AtomId) -> List[AtomId]:
        """Return every canonical ``ConsentGranted`` atom of this holder."""
        return self._assertions("ConsentGranted", holder)

    def hard_limits_of(self, holder: AtomId) -> List[AtomId]:
        """Return every ``HardLimit`` atom asserted by this holder."""
        return self._assertions("HardLimit", holder)

    def revocations_of(self, holder: AtomId) -> List[AtomId]:
        """Return every canonical ``ConsentRevoked`` atom of this holder."""
        return self._assertions("ConsentRevoked", holder)

    def _covers(self, target: AtomId, act: AtomId) -> bool:
        """Does an assertion on ``target`` cover ``act``?  Directly,
        or through blanket scope: the target is a kind the act
        belongs to."""
        if target == act:
            return True
        target_atom = self.api.get(target)
        if isinstance(target_atom, KindAtom):
            return self.relational.kind_is_a(act, target)
        return False

    def _events(
        self, holder: AtomId, act: AtomId
    ) -> List[Tuple[Tuple[int, int], int, str, AtomId, Dict[str, object]]]:
        """The dated statement timeline covering (holder, act):
        (stated_on key, record id, kind, record, hangers) sorted
        chronologically.  A grant record whose exclusions name the
        act does not cover it and is left out."""
        events = []
        for name, kind in (
            ("ConsentGranted", "grant"), ("ConsentRevoked", "revocation"),
        ):
            for atom_id in self._assertions(name, holder):
                if not self._covers(self.api.get(atom_id).args[1], act):
                    continue
                for record in self.records_of(atom_id):
                    hangers = self.hangers_of(record)
                    if hangers["stated_on"] is None:
                        continue
                    if act in hangers["excludes"]:
                        continue
                    events.append((
                        wxdy_key(hangers["stated_on"]), record,
                        kind, record, hangers,
                    ))
        events.sort(key=lambda event: (event[0], event[1]))
        return events

    def _governing_record(
        self, holder: AtomId, act: AtomId, at_key: Tuple[int, int]
    ) -> Optional[AtomId]:
        """The grant record governing (holder, act) at a date, when a
        grant is actually standing there: the latest statement at or
        before the date is a grant, and the date is inside its
        window."""
        standing: Optional[AtomId] = None
        for key, _rid, kind, record, hangers in self._events(holder, act):
            if key > at_key:
                break
            if kind == "revocation":
                standing = None
                continue
            opens = hangers["active_from"] or hangers["stated_on"]
            closes = hangers["expires"]
            if closes is not None \
                    and wxdy_key(opens) <= at_key <= wxdy_key(closes):
                standing = record
            else:
                standing = None
        return standing

    def consent_state(
        self, holder: AtomId, act: AtomId, as_of: str
    ) -> str:
        """The holder's consent state on an act, as of a WXDY date.

        One of:

        - ``"hard_limit"`` — a categorical refusal stands (and no
          live grant contradicts it).
        - ``"conflicted"`` — a grant is live at the date while a hard
          limit also stands; preserved, never silently resolved.
        - ``"granted"`` — a declared grant is inside its window and
          unrevoked.
        - ``"enacted"`` — an enacted grant's occasion window contains
          the date (a retrospective record, never a forward license).
        - ``"revoked"`` — the latest statement at or before the date
          is a revocation: the revoked state persists until stated
          otherwise.
        - ``"expired"`` — the latest statement is a grant whose
          window has closed.
        - ``"none"`` — nothing stands either way: an honest blank,
          which must never be read as an implied yes.
        """
        self._check_atom(holder, "holder")
        self._check_act(act)
        at_key = wxdy_key(as_of)

        hard = any(
            self._covers(self.api.get(limit).args[1], act)
            and act not in self.exclusions_of(limit)
            for limit in self.hard_limits_of(holder)
        )

        governing: Optional[Tuple[str, Dict[str, object]]] = None
        for key, _rid, kind, _record, hangers in self._events(holder, act):
            if key > at_key:
                break
            governing = (kind, hangers)

        live_grant = False
        state: Optional[str] = None
        if governing is not None:
            kind, hangers = governing
            if kind == "revocation":
                state = "revoked"
            else:
                opens = hangers["active_from"] or hangers["stated_on"]
                closes = hangers["expires"]
                if closes is not None and wxdy_key(opens) <= at_key:
                    if at_key <= wxdy_key(closes):
                        live_grant = True
                        state = (
                            "enacted" if hangers["mode"] == "enacted"
                            else "granted"
                        )
                    else:
                        state = "expired"
                else:
                    state = "none"  # stated, but its window not yet open

        if hard:
            return "conflicted" if live_grant else "hard_limit"
        return state if state is not None else "none"


def install(
    api: AtomSpaceAPI, owner: Optional[AtomId] = None
) -> ConsentPredicates:
    """Install and return a consent vocabulary for ``api``.

    ``owner`` sets the graph owner's atom: the standing default
    recipient for grants.  Installing again with an owner fills an
    owner the first installation left unset.
    """
    installed = _INSTALLATIONS.get(api)
    if installed is None:
        installed = ConsentPredicates(api, owner=owner)
        _INSTALLATIONS[api] = installed
    elif owner is not None and installed.owner is None:
        installed.owner = owner
    return installed


install_consent_predicates = install
Consent = ConsentPredicates

__all__ = [
    "ConsentPredicates", "Consent", "install", "install_consent_predicates",
    "NEVER_EXPIRES", "wxdy_key",
]
