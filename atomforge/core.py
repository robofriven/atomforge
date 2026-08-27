from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Type, Union

from .atoms import (
    Atom, AtomId, KindAtom, Ligature, Link, Node, PredicateAtom,
    RawAtomResult, SearchResult, TraversalResult,
)
from .infrastructure import (
    AlreadyDeletedError, DuplicateCurrentError, GraphInvariantError,
    InvalidAtomOperationError, InvalidConfidenceError,
    MalformedPersistenceError, SchemaVersionError, UnknownAtomError,
    UnknownPredicateError,
)

NameOrId = Union[str, AtomId]
SCHEMA_VERSION = 5


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


class AtomSpace:
    """Storage and graph mechanics for structurally immutable atoms."""

    def __init__(self, *, dedup_links: bool = True) -> None:
        self._next_id = 1
        self._dedup_links = bool(dedup_links)
        self._atoms: Dict[AtomId, Atom] = {}
        self._confidence: Dict[AtomId, float] = {}
        self._deleted_ids: Set[AtomId] = set()
        self._in_links: Dict[AtomId, Set[AtomId]] = {}
        self._by_pred: Dict[AtomId, Set[AtomId]] = {}
        self._link_key_index: Dict[
            Tuple[AtomId, Tuple[AtomId, ...]], Set[AtomId]
        ] = {}
        self._label_index: Dict[str, List[AtomId]] = {}
        self._kind_intern: Dict[str, AtomId] = {}
        self._pred_intern: Dict[str, AtomId] = {}
        self._validators: List[Any] = []
        self.current_predicate = self._create_predicate(
            "Current", arity=1, roles=("atom",)
        )
        self.delete_predicate = self._create_predicate(
            "Delete", arity=1, roles=("atom",)
        )

    def _alloc(self) -> AtomId:
        atom_id = self._next_id
        self._next_id += 1
        return atom_id

    @staticmethod
    def _validated_confidence(value: float, *, creation: bool) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidConfidenceError("confidence must be numeric")
        value = float(value)
        if not math.isfinite(value) or (value <= 0 if creation else value < 0) or value > 1:
            interval = "(0, 1]" if creation else "[0, 1]"
            raise InvalidConfidenceError(f"confidence must be in {interval}")
        return value

    def _store_atom(self, atom: Atom, *, confidence: float = 1.0) -> None:
        if atom.id in self._atoms or atom.id <= 0:
            raise GraphInvariantError(f"invalid or colliding atom id {atom.id}")
        self._atoms[atom.id] = atom
        self._confidence[atom.id] = self._validated_confidence(
            confidence, creation=True
        )
        self._index_atom(atom)

    def _index_atom(self, atom: Atom) -> None:
        if atom.label:
            self._label_index.setdefault(atom.label, []).append(atom.id)
        self._in_links.setdefault(atom.id, set())
        if isinstance(atom, PredicateAtom):
            self._by_pred.setdefault(atom.id, set())
        if isinstance(atom, Link):
            self._by_pred.setdefault(atom.predicate, set()).add(atom.id)
        if isinstance(atom, (Link, Ligature)):
            for target in atom.args:
                self._in_links.setdefault(target, set()).add(atom.id)
        if isinstance(atom, Link):
            self._link_key_index.setdefault(
                (atom.predicate, atom.args), set()
            ).add(atom.id)

    def _require_physical(self, atom_id: AtomId) -> Atom:
        if not isinstance(atom_id, int) or atom_id not in self._atoms:
            raise UnknownAtomError(atom_id)
        return self._atoms[atom_id]

    def _is_deleted(self, atom_id: AtomId) -> bool:
        return atom_id in self._deleted_ids

    def get(self, atom_id: AtomId) -> Optional[Atom]:
        atom = self._require_physical(atom_id)
        return None if self._is_deleted(atom_id) else atom

    atom = get

    def get_raw(self, atom_id: AtomId) -> RawAtomResult:
        atom = self._require_physical(atom_id)
        return RawAtomResult(
            atom=atom, atom_id=atom_id,
            confidence=self._confidence[atom_id],
            deleted=self._is_deleted(atom_id),
        )

    def confidence(self, atom_id: AtomId) -> float:
        self._require_physical(atom_id)
        if self._is_deleted(atom_id):
            raise AlreadyDeletedError(atom_id)
        return self._confidence[atom_id]

    def set_confidence(self, atom_id: AtomId, value: float) -> None:
        self._require_physical(atom_id)
        if self._is_deleted(atom_id):
            raise AlreadyDeletedError(atom_id)
        self._confidence[atom_id] = self._validated_confidence(value, creation=False)

    def kind(
        self, name: str, *, intern: bool = True, confidence: float = 1.0,
    ) -> AtomId:
        if intern and name in self._kind_intern:
            atom_id = self._kind_intern[name]
            if self._is_deleted(atom_id):
                raise AlreadyDeletedError(atom_id)
            return atom_id
        atom_id = self._alloc()
        self._store_atom(
            KindAtom(atom_id, name, _utc_now_iso()), confidence=confidence
        )
        if intern:
            self._kind_intern[name] = atom_id
        return atom_id

    def predicate(
        self, name: str, *, arity: int = -1,
        roles: Tuple[str, ...] = (), anti_reflexive: bool = False,
        acyclic: bool = False, intern: bool = True,
        template: Optional[str] = None, confidence: float = 1.0,
    ) -> AtomId:
        if name in ("Current", "Delete"):
            raise InvalidAtomOperationError(
                f"{name!r} is a reserved Core predicate name"
            )
        return self._create_predicate(
            name, arity=arity, roles=roles,
            anti_reflexive=anti_reflexive, acyclic=acyclic,
            intern=intern, template=template, confidence=confidence,
        )

    def _create_predicate(
        self, name: str, *, arity: int = -1,
        roles: Tuple[str, ...] = (), anti_reflexive: bool = False,
        acyclic: bool = False, intern: bool = True,
        template: Optional[str] = None, confidence: float = 1.0,
    ) -> AtomId:
        if arity < -1:
            raise ValueError("arity must be -1 or non-negative")
        if intern and name in self._pred_intern:
            atom_id = self._pred_intern[name]
            if self._is_deleted(atom_id):
                raise AlreadyDeletedError(atom_id)
            existing = self._atoms[atom_id]
            assert isinstance(existing, PredicateAtom)
            requested_structure = (
                arity, tuple(roles), template,
                bool(anti_reflexive), bool(acyclic),
            )
            existing_structure = (
                existing.arity, existing.roles, existing.template,
                existing.anti_reflexive, existing.acyclic,
            )
            if requested_structure != existing_structure:
                raise GraphInvariantError(
                    f"predicate {name!r} already exists with different structure"
                )
            return atom_id
        atom_id = self._alloc()
        atom = PredicateAtom(
            atom_id, name, _utc_now_iso(), arity, tuple(roles), template,
            bool(anti_reflexive), bool(acyclic),
        )
        self._store_atom(atom, confidence=confidence)
        if intern:
            self._pred_intern[name] = atom_id
        return atom_id

    def _resolve_kind(self, kind: NameOrId) -> AtomId:
        atom_id = self._kind_intern.get(kind) if isinstance(kind, str) else kind
        atom = self.get(atom_id) if atom_id is not None else None
        if not isinstance(atom, KindAtom):
            raise UnknownAtomError(f"unknown kind {kind!r}")
        return atom.id

    def _resolve_predicate(self, predicate: NameOrId) -> AtomId:
        atom_id = (
            self._pred_intern.get(predicate)
            if isinstance(predicate, str) else predicate
        )
        if atom_id is None:
            raise UnknownPredicateError(f"unknown predicate {predicate!r}")
        atom = self.get(atom_id)
        if not isinstance(atom, PredicateAtom):
            raise UnknownPredicateError(predicate)
        return atom.id

    def _resolve_kind_raw(self, kind: NameOrId) -> AtomId:
        atom_id = self._kind_intern.get(kind) if isinstance(kind, str) else kind
        atom = self._atoms.get(atom_id) if atom_id is not None else None
        if not isinstance(atom, KindAtom):
            raise UnknownAtomError(f"unknown kind {kind!r}")
        return atom.id

    def _resolve_predicate_raw(self, predicate: NameOrId) -> AtomId:
        atom_id = (
            self._pred_intern.get(predicate)
            if isinstance(predicate, str) else predicate
        )
        atom = self._atoms.get(atom_id) if atom_id is not None else None
        if not isinstance(atom, PredicateAtom):
            raise UnknownPredicateError(predicate)
        return atom.id

    def _validate_address(self, atom_id: AtomId) -> None:
        self._require_physical(atom_id)
        if self._is_deleted(atom_id):
            raise AlreadyDeletedError(atom_id)

    def _is_current_assertion(self, atom_id: AtomId) -> bool:
        atom = self._atoms.get(atom_id)
        return (
            isinstance(atom, Link)
            and atom.predicate == self.current_predicate
        )

    def create_node(
        self, label: Optional[str], *, kind: NameOrId = 0,
        props: Optional[Dict[str, Any]] = None, intern: bool = False,
        confidence: float = 1.0,
    ) -> AtomId:
        kind_id = self._resolve_kind(kind) if kind else 0
        requested_props = tuple(sorted((props or {}).items()))
        if intern:
            for atom_id in self.find_by_label(label):
                atom = self.get(atom_id)
                if not isinstance(atom, Node):
                    continue
                if atom.kind != kind_id or atom.props != requested_props:
                    raise GraphInvariantError(
                        f"interned node {label!r} conflicts with existing structure"
                    )
                return atom.id
        atom_id = self._alloc()
        self._store_atom(
            Node(
                atom_id, label, _utc_now_iso(), kind_id,
                requested_props,
            ),
            confidence=confidence,
        )
        return atom_id

    def _validate_link(
        self, predicate_id: AtomId, args: Tuple[AtomId, ...],
        *, allow_deleted: bool = False,
    ) -> PredicateAtom:
        predicate = self._atoms.get(predicate_id) if allow_deleted else self.get(predicate_id)
        if not isinstance(predicate, PredicateAtom):
            raise UnknownPredicateError(predicate_id)
        for atom_id in args:
            self._require_physical(atom_id)
            if not allow_deleted and self._is_deleted(atom_id):
                raise AlreadyDeletedError(atom_id)
            if self._is_current_assertion(atom_id):
                error = GraphInvariantError if allow_deleted else InvalidAtomOperationError
                raise error(
                    "Current assertions cannot be relationship arguments"
                )
        predicate.check_arity(len(args))
        for validator in self._validators:
            validator(self, predicate, args)
        if predicate.anti_reflexive and len(set(args)) != len(args):
            raise ValueError(f"{predicate.label} forbids repeated args")
        if predicate.acyclic and len(args) == 2:
            if args[0] == args[1] or self._reachable_via_predicate(
                args[1], args[0], predicate_id, raw=allow_deleted
            ):
                raise ValueError(f"{predicate.label} would create a cycle")
        if not allow_deleted and predicate_id == self.delete_predicate:
            target = args[0]
            if target in (self.current_predicate, self.delete_predicate):
                raise InvalidAtomOperationError("Core predicates cannot be deleted")
            target_atom = self._atoms[target]
            if isinstance(target_atom, Link) and target_atom.predicate == self.delete_predicate:
                raise InvalidAtomOperationError("Delete assertions cannot be deleted")
            if self._is_deleted(target):
                raise AlreadyDeletedError(target)
        return predicate

    def _create_link(
        self, predicate: NameOrId, args: Iterable[AtomId], *,
        label: Optional[str] = None, confidence: float = 1.0,
        deduplicate: Optional[bool] = None, allow_core: bool = False,
    ) -> AtomId:
        predicate_id = self._resolve_predicate(predicate)
        if not allow_core and predicate_id in (
            self.current_predicate, self.delete_predicate
        ):
            raise InvalidAtomOperationError(
                "Core predicates require their dedicated API operations"
            )
        arg_ids = tuple(int(value) for value in args)
        self._validate_link(predicate_id, arg_ids)
        dedup = self._dedup_links if deduplicate is None else deduplicate
        existing_ids = self._link_key_index.get((predicate_id, arg_ids), set())
        if any(self._is_deleted(existing_id) for existing_id in existing_ids):
            raise InvalidAtomOperationError(
                "an exact historical Link was deleted and cannot be recreated"
            )
        if dedup and existing_ids:
            return min(existing_ids)
        atom_id = self._alloc()
        self._store_atom(
            Link(atom_id, label, _utc_now_iso(), predicate_id, arg_ids),
            confidence=confidence,
        )
        return atom_id

    def create_link(
        self, predicate: NameOrId, *args: AtomId,
        label: Optional[str] = None, confidence: float = 1.0,
    ) -> AtomId:
        return self._create_link(
            predicate, args, label=label, confidence=confidence
        )

    def create_ligature(
        self, name: str, *args: AtomId, label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Ligature name must be a non-empty string")
        arg_ids = tuple(int(value) for value in args)
        if not arg_ids:
            raise ValueError("Ligature must connect at least one atom")
        for atom_id in arg_ids:
            self._validate_address(atom_id)
            if self._is_current_assertion(atom_id):
                raise InvalidAtomOperationError(
                    "Current assertions cannot be relationship arguments"
                )
        atom_id = self._alloc()
        self._store_atom(
            Ligature(atom_id, label, _utc_now_iso(), name, arg_ids),
            confidence=confidence,
        )
        return atom_id

    def find_by_label(self, label: str) -> List[AtomId]:
        return [
            atom_id for atom_id in self._label_index.get(label, [])
            if not self._is_deleted(atom_id)
        ]

    def links_of(self, predicate: NameOrId) -> Set[AtomId]:
        return {
            result.matched_id
            for result in self.search(predicate=predicate, atom_type=Link)
        }

    def find_links(
        self, predicate: NameOrId, *args: AtomId
    ) -> List[SearchResult]:
        predicate_id = self._resolve_predicate(predicate)
        wanted = tuple(int(value) for value in args)
        for atom_id in wanted:
            self._validate_address(atom_id)
        return [
            result
            for result in self.search(predicate=predicate_id, atom_type=Link)
            if isinstance(result.atom, Link) and result.atom.args == wanted
        ]

    def has_link(self, predicate: NameOrId, *args: AtomId) -> bool:
        return bool(self.find_links(predicate, *args))

    def find_links_by_label(
        self, predicate: NameOrId, *labels: str
    ) -> List[SearchResult]:
        pools = [
            None if label.strip() == "*" else set(self.find_by_label(label))
            for label in labels
        ]
        if any(pool == set() for pool in pools):
            return []
        return [
            result
            for result in self.search(predicate=predicate, atom_type=Link)
            if isinstance(result.atom, Link)
            and len(result.atom.args) == len(pools)
            and all(
                pool is None or arg in pool
                for arg, pool in zip(result.atom.args, pools)
            )
        ]

    def has_link_by_label(self, predicate: NameOrId, *labels: str) -> bool:
        return bool(self.find_links_by_label(predicate, *labels))

    def in_ligatures(self, atom_id: AtomId) -> Set[AtomId]:
        self._validate_address(atom_id)
        results = set()
        for matched_id in self._in_links.get(atom_id, set()):
            if not isinstance(self._atoms.get(matched_id), Ligature):
                continue
            ligature = self.get(matched_id)
            if isinstance(ligature, Ligature) and atom_id in ligature.args:
                results.add(matched_id)
        return results

    def in_links(
        self, atom_id: AtomId, *, predicate: Optional[NameOrId] = None
    ) -> Set[AtomId]:
        self._validate_address(atom_id)
        predicate_id = (
            self._resolve_predicate(predicate) if predicate is not None else None
        )
        results = set()
        for matched_id in self._in_links.get(atom_id, set()):
            if not isinstance(self._atoms.get(matched_id), Link):
                continue
            link = self.get(matched_id)
            if not isinstance(link, Link) or atom_id not in link.args:
                continue
            if predicate_id is None or link.predicate == predicate_id:
                results.add(matched_id)
        return results

    def out(self, link_id: AtomId) -> Tuple[AtomId, ...]:
        atom = self.get(link_id)
        if not isinstance(atom, Link):
            raise InvalidAtomOperationError(f"{link_id} is not a Link")
        return tuple(arg for arg in atom.args if not self._is_deleted(arg))

    def connected(self, ligature_id: AtomId) -> Tuple[AtomId, ...]:
        atom = self.get(ligature_id)
        if not isinstance(atom, Ligature):
            raise InvalidAtomOperationError(f"{ligature_id} is not a Ligature")
        return tuple(arg for arg in atom.args if not self._is_deleted(arg))

    def _reachable_via_predicate(
        self, start: AtomId, goal: AtomId, predicate_id: AtomId, *,
        raw: bool = False,
    ) -> bool:
        stack, seen = [start], set()
        while stack:
            current = stack.pop()
            if current == goal:
                return True
            if current in seen:
                continue
            seen.add(current)
            for link_id in self._by_pred.get(predicate_id, set()):
                link = self._atoms.get(link_id) if raw else self.get(link_id)
                if not isinstance(link, Link) or len(link.args) != 2:
                    continue
                if link.args[0] == current and (
                    raw or not self._is_deleted(link.args[1])
                ):
                    stack.append(link.args[1])
        return False

    def delete(self, atom_id: AtomId) -> AtomId:
        self._validate_address(atom_id)
        atom = self._atoms[atom_id]
        if isinstance(atom, Link) and atom.predicate == self.current_predicate:
            raise InvalidAtomOperationError(
                "Current assertions must be removed with remove_current()"
            )
        if isinstance(atom, Link) and atom.predicate == self.delete_predicate:
            raise InvalidAtomOperationError("Delete assertions cannot be deleted")
        if isinstance(atom, KindAtom) and any(
            isinstance(candidate, Node)
            and candidate.kind == atom_id
            and not self._is_deleted(candidate.id)
            for candidate in self._atoms.values()
        ):
            raise InvalidAtomOperationError(
                "a KindAtom referenced by a live Node cannot be deleted"
            )
        if isinstance(atom, PredicateAtom):
            if atom_id in (self.current_predicate, self.delete_predicate):
                raise InvalidAtomOperationError("Core predicates cannot be deleted")
            if any(
                not self._is_deleted(link_id)
                for link_id in self._by_pred.get(atom_id, set())
            ):
                raise InvalidAtomOperationError(
                    "a PredicateAtom used by a live Link cannot be deleted"
                )

        scheduled: Set[AtomId] = {atom_id}
        pending = [atom_id]
        current_assertions: Set[AtomId] = set()
        while pending:
            target = pending.pop()
            for relationship_id in self._in_links.get(target, set()):
                if self._is_deleted(relationship_id):
                    continue
                relationship = self._atoms[relationship_id]
                if not isinstance(relationship, (Link, Ligature)):
                    continue
                if (
                    isinstance(relationship, Link)
                    and relationship.predicate == self.delete_predicate
                ):
                    continue
                if self._is_current_assertion(relationship_id):
                    current_assertions.add(relationship_id)
                    continue
                if relationship_id not in scheduled:
                    scheduled.add(relationship_id)
                    pending.append(relationship_id)

        for assertion_id in current_assertions:
            self._remove_atom_physical(assertion_id)
        deletion_assertions = {}
        for target in sorted(scheduled):
            assertion_id = self._create_link(
                self.delete_predicate, (target,), deduplicate=False,
                allow_core=True,
            )
            self._deleted_ids.add(target)
            deletion_assertions[target] = assertion_id
        return deletion_assertions[atom_id]

    def _remove_atom_physical(self, atom_id: AtomId) -> None:
        atom = self._require_physical(atom_id)
        if not isinstance(atom, Link) or atom.predicate != self.current_predicate:
            raise InvalidAtomOperationError(
                "only Current assertions may be physically removed"
            )
        if any(
            not self._is_deleted(relationship_id)
            for relationship_id in self._in_links.get(atom_id, set())
        ):
            raise GraphInvariantError(
                "a Current assertion is illegally used by a live relationship"
            )
        self._by_pred[atom.predicate].discard(atom_id)
        for target in atom.args:
            self._in_links.get(target, set()).discard(atom_id)
        self._in_links.pop(atom_id, None)
        key = (atom.predicate, atom.args)
        indexed = self._link_key_index.get(key)
        if indexed is not None:
            indexed.discard(atom_id)
            if not indexed:
                self._link_key_index.pop(key)
        if atom.label:
            self._label_index[atom.label].remove(atom_id)
            if not self._label_index[atom.label]:
                self._label_index.pop(atom.label)
        self._confidence.pop(atom_id)
        self._atoms.pop(atom_id)

    def _current_matches(self, atom_id: AtomId) -> List[AtomId]:
        self._validate_address(atom_id)
        matches = []
        for link_id in self._by_pred.get(self.current_predicate, set()):
            link = self.get(link_id)
            if isinstance(link, Link) and link.args == (atom_id,):
                matches.append(link_id)
        return matches

    def make_current(self, atom_id: AtomId) -> AtomId:
        self._validate_address(atom_id)
        if self._is_current_assertion(atom_id):
            raise InvalidAtomOperationError(
                "a Current assertion cannot itself be Current"
            )
        if self._current_matches(atom_id):
            raise DuplicateCurrentError(atom_id)
        return self._create_link(
            self.current_predicate, (atom_id,), deduplicate=False,
            allow_core=True,
        )

    def remove_current(self, atom_id: AtomId) -> None:
        matches = self._current_matches(atom_id)
        if len(matches) > 1:
            raise GraphInvariantError(
                f"multiple Current assertions for {atom_id}"
            )
        if not matches:
            raise InvalidAtomOperationError(
                f"no Current assertion for {atom_id}"
            )
        self._remove_atom_physical(matches[0])

    @staticmethod
    def _matches(
        atom: Atom, *, label: Optional[str],
        atom_type: Optional[Type[Atom]], predicate_id: Optional[int],
        kind_id: Optional[int],
    ) -> bool:
        return (
            (label is None or atom.label == label)
            and (atom_type is None or isinstance(atom, atom_type))
            and (predicate_id is None or isinstance(atom, Link) and atom.predicate == predicate_id)
            and (kind_id is None or isinstance(atom, Node) and atom.kind == kind_id)
        )

    def search_raw(
        self, *, label: Optional[str] = None,
        atom_type: Optional[Type[Atom]] = None,
        predicate: Optional[NameOrId] = None,
        kind: Optional[NameOrId] = None,
    ) -> List[RawAtomResult]:
        predicate_id = self._resolve_predicate_raw(predicate) if predicate is not None else None
        kind_id = self._resolve_kind_raw(kind) if kind is not None else None
        return [
            self.get_raw(atom_id)
            for atom_id, atom in self._atoms.items()
            if self._matches(
                atom, label=label, atom_type=atom_type,
                predicate_id=predicate_id, kind_id=kind_id,
            )
        ]

    def search(
        self, *, label: Optional[str] = None,
        atom_type: Optional[Type[Atom]] = None,
        predicate: Optional[NameOrId] = None,
        kind: Optional[NameOrId] = None,
    ) -> List[SearchResult]:
        predicate_id = self._resolve_predicate(predicate) if predicate is not None else None
        kind_id = self._resolve_kind(kind) if kind is not None else None
        return [
            SearchResult(raw.atom, raw.atom_id)
            for raw in self.search_raw(
                label=label, atom_type=atom_type,
                predicate=predicate_id, kind=kind_id,
            )
            if not raw.deleted
        ]

    def traverse_raw(
        self, start: AtomId, *, max_depth: Optional[int] = None
    ) -> List[RawAtomResult]:
        self._require_physical(start)
        queue, seen, results = deque([(start, 0)]), set(), []
        while queue:
            atom_id, depth = queue.popleft()
            if atom_id in seen:
                continue
            seen.add(atom_id)
            results.append(self.get_raw(atom_id))
            if max_depth is not None and depth >= max_depth:
                continue
            atom = self._atoms[atom_id]
            if isinstance(atom, Node) and atom.kind:
                queue.append((atom.kind, depth + 1))
            if isinstance(atom, Link):
                queue.append((atom.predicate, depth + 1))
                queue.extend((arg, depth + 1) for arg in atom.args)
            if isinstance(atom, Ligature):
                queue.extend((arg, depth + 1) for arg in atom.args)
            queue.extend(
                (relationship_id, depth + 1)
                for relationship_id in self._in_links.get(atom_id, set())
            )
        return results

    def traverse(
        self, start: AtomId, *, max_depth: Optional[int] = None
    ) -> List[TraversalResult]:
        self._validate_address(start)
        queue, seen, results = deque([(start, 0)]), set(), []
        while queue:
            atom_id, depth = queue.popleft()
            if atom_id in seen or self._is_deleted(atom_id):
                continue
            seen.add(atom_id)
            atom = self._atoms[atom_id]
            results.append(TraversalResult(atom, atom_id))
            if max_depth is not None and depth >= max_depth:
                continue
            if isinstance(atom, Node) and atom.kind:
                queue.append((atom.kind, depth + 1))
            if isinstance(atom, Link):
                queue.append((atom.predicate, depth + 1))
                queue.extend((arg, depth + 1) for arg in atom.args)
            if isinstance(atom, Ligature):
                queue.extend((arg, depth + 1) for arg in atom.args)
            queue.extend(
                (relationship_id, depth + 1)
                for relationship_id in self._in_links.get(atom_id, set())
            )
        return results

    def pretty(self, atom_id: AtomId, *, max_depth: int = 2) -> str:
        def render(target: int, depth: int) -> str:
            atom = self.get(target)
            if atom is None:
                return "<deleted>"
            if isinstance(atom, Link):
                predicate = self.get(atom.predicate)
                name = getattr(predicate, "label", None) or f"Pred#{atom.predicate}"
                if depth <= 0:
                    return f"{name}(...)"
                return f"{name}({', '.join(render(arg, depth - 1) for arg in atom.args)})"
            if isinstance(atom, Ligature):
                if depth <= 0:
                    return f"{atom.name}(...)"
                return f"{atom.name}({', '.join(render(arg, depth - 1) for arg in atom.args)})"
            return atom.label or f"{type(atom).__name__}#{atom.id}"
        return render(atom_id, max_depth)

    def add_validator(self, fn: Any) -> None:
        self._validators.append(fn)

    @staticmethod
    def _encoded_atom(atom: Atom) -> Dict[str, Any]:
        data = asdict(atom)
        data["type"] = type(atom).__name__
        return data

    def save(self, path: Union[str, Path]) -> None:
        data = {
            "schema_version": SCHEMA_VERSION,
            "next_id": self._next_id,
            "dedup_links": self._dedup_links,
            "atoms": [self._encoded_atom(atom) for atom in self._atoms.values()],
            "confidence": {str(key): value for key, value in self._confidence.items()},
            "kind_intern": self._kind_intern,
            "pred_intern": self._pred_intern,
            "current_predicate": self.current_predicate,
            "delete_predicate": self.delete_predicate,
        }
        Path(path).write_text(
            json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Union[str, Path]) -> "AtomSpace":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            raise MalformedPersistenceError(str(exc)) from exc
        if "schema_version" not in data:
            raise SchemaVersionError("missing schema_version")
        if data["schema_version"] != SCHEMA_VERSION:
            raise SchemaVersionError(
                f"unsupported schema version {data['schema_version']}"
            )
        try:
            space = cls.__new__(cls)
            space._next_id = int(data["next_id"])
            space._dedup_links = bool(data["dedup_links"])
            space._atoms, space._confidence = {}, {}
            space._deleted_ids = set()
            space._in_links, space._by_pred = {}, {}
            space._link_key_index, space._label_index = {}, {}
            space._kind_intern = {
                str(key): int(value) for key, value in data["kind_intern"].items()
            }
            space._pred_intern = {
                str(key): int(value) for key, value in data["pred_intern"].items()
            }
            space._validators = []
            constructors = {
                "Atom": Atom, "Node": Node, "Link": Link,
                "Ligature": Ligature, "KindAtom": KindAtom,
                "PredicateAtom": PredicateAtom,
            }
            for stored in data["atoms"]:
                item = dict(stored)
                constructor = constructors[item.pop("type")]
                for key in ("props", "args", "roles"):
                    if key in item:
                        item[key] = tuple(
                            tuple(value) if isinstance(value, list) else value
                            for value in item[key]
                        )
                atom = constructor(**item)
                if atom.id <= 0 or atom.id in space._atoms:
                    raise GraphInvariantError(f"illegal/colliding id {atom.id}")
                space._atoms[atom.id] = atom
            space._confidence = {
                int(key): space._validated_confidence(value, creation=False)
                for key, value in data["confidence"].items()
            }
            if set(space._confidence) != set(space._atoms):
                raise GraphInvariantError("confidence does not cover stored atoms")
            for atom in space._atoms.values():
                space._index_atom(atom)
            space.current_predicate = int(data["current_predicate"])
            space.delete_predicate = int(data["delete_predicate"])
            for assertion_id in space._by_pred.get(space.delete_predicate, set()):
                assertion = space._atoms[assertion_id]
                if not isinstance(assertion, Link) or len(assertion.args) != 1:
                    raise GraphInvariantError("malformed Delete assertion")
                space._deleted_ids.add(assertion.args[0])
            space._validate_loaded()
            return space
        except (
            GraphInvariantError, SchemaVersionError, InvalidConfidenceError,
        ):
            raise
        except Exception as exc:
            raise MalformedPersistenceError(str(exc)) from exc

    def _validate_loaded(self) -> None:
        if self._next_id <= max(self._atoms, default=0):
            raise GraphInvariantError("next_id is not above allocated ids")
        for atom in self._atoms.values():
            if isinstance(atom, Node) and atom.kind and not isinstance(
                self._atoms.get(atom.kind), KindAtom
            ):
                raise GraphInvariantError(f"invalid kind on {atom.id}")
            if (
                isinstance(atom, Node)
                and atom.kind
                and not self._is_deleted(atom.id)
                and self._is_deleted(atom.kind)
            ):
                raise GraphInvariantError(
                    f"live Node {atom.id} uses deleted KindAtom {atom.kind}"
                )
            if isinstance(atom, Link):
                self._validate_link(atom.predicate, atom.args, allow_deleted=True)
            if isinstance(atom, Ligature):
                if not isinstance(atom.name, str) or not atom.name.strip():
                    raise GraphInvariantError(f"invalid Ligature name on {atom.id}")
                if not atom.args:
                    raise GraphInvariantError(f"Ligature {atom.id} has no connections")
                for target in atom.args:
                    self._require_physical(target)
                    if self._is_current_assertion(target):
                        raise GraphInvariantError(
                            "Current assertions cannot be Ligature arguments"
                        )
        for name, atom_id in self._kind_intern.items():
            if not isinstance(self._atoms.get(atom_id), KindAtom):
                raise GraphInvariantError(f"bad kind intern {name}")
        for name, atom_id in self._pred_intern.items():
            if not isinstance(self._atoms.get(atom_id), PredicateAtom):
                raise GraphInvariantError(f"bad predicate intern {name}")
        current = self._atoms.get(self.current_predicate)
        deletion = self._atoms.get(self.delete_predicate)
        core_structure = (1, ("atom",), None, False, False)
        if (
            not isinstance(current, PredicateAtom)
            or current.label != "Current"
            or (
                current.arity, current.roles, current.template,
                current.anti_reflexive, current.acyclic,
            ) != core_structure
            or self._pred_intern.get("Current") != self.current_predicate
        ):
            raise GraphInvariantError("invalid Current predicate")
        if (
            not isinstance(deletion, PredicateAtom)
            or deletion.label != "Delete"
            or (
                deletion.arity, deletion.roles, deletion.template,
                deletion.anti_reflexive, deletion.acyclic,
            ) != core_structure
            or self._pred_intern.get("Delete") != self.delete_predicate
        ):
            raise GraphInvariantError("invalid Delete predicate")
        for atom in self._atoms.values():
            if (
                isinstance(atom, PredicateAtom)
                and atom.label in ("Current", "Delete")
                and atom.id not in (self.current_predicate, self.delete_predicate)
            ):
                raise GraphInvariantError(
                    f"reserved predicate name {atom.label!r} has invalid identity"
                )
        deleted_targets = set()
        for assertion_id in self._by_pred.get(self.delete_predicate, set()):
            assertion = self._atoms[assertion_id]
            assert isinstance(assertion, Link)
            target = assertion.args[0]
            if target in (self.current_predicate, self.delete_predicate):
                raise GraphInvariantError("Core predicates cannot be deleted")
            target_atom = self._atoms[target]
            if (
                isinstance(target_atom, Link)
                and target_atom.predicate == self.delete_predicate
            ):
                raise GraphInvariantError("Delete assertions cannot be deleted")
            if target in deleted_targets:
                raise GraphInvariantError(f"duplicate Delete assertion for {target}")
            deleted_targets.add(target)
        if deleted_targets != self._deleted_ids:
            raise GraphInvariantError("derived deletion state is inconsistent")
        for target in deleted_targets:
            for incident_id in self._in_links.get(target, set()):
                incident = self._atoms[incident_id]
                if (
                    isinstance(incident, Link)
                    and incident.predicate == self.delete_predicate
                    and incident.args == (target,)
                ):
                    continue
                if isinstance(incident, (Link, Ligature)) and not self._is_deleted(incident_id):
                    raise GraphInvariantError(
                        f"live relationship {incident_id} is incident to deleted atom {target}"
                    )
            if isinstance(self._atoms[target], PredicateAtom):
                for link_id in self._by_pred.get(target, set()):
                    if not self._is_deleted(link_id):
                        raise GraphInvariantError(
                            f"live Link {link_id} uses deleted predicate {target}"
                        )
        current_targets = set()
        for assertion_id in self._by_pred.get(self.current_predicate, set()):
            if self._is_deleted(assertion_id):
                raise GraphInvariantError("Current assertions cannot be tombstoned")
            assertion = self._atoms[assertion_id]
            assert isinstance(assertion, Link)
            target = assertion.args[0]
            if self._is_deleted(target):
                raise GraphInvariantError("Current cannot target a deleted atom")
            if target in current_targets:
                raise GraphInvariantError(f"duplicate Current assertion for {target}")
            current_targets.add(target)
