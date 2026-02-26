from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union
from datetime import datetime, timezone
from .api import AddAPI, CheckAPI, RetrieveAPI
from .predicates import install_api_predicates
import itertools
import time

from .atoms import AtomId, Atom, Node, Link, KindAtom, PredicateAtom

NameOrId = Union[str, AtomId]


# -----------------------
# DateTime UTC Helper
# ------------------------


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


class ByLabelCreationError(ValueError):
    pass


class AtomSpace:
    def __init__(self, *, dedup_links: bool = True, with_defaults: bool = True) -> None:
        self._ids = itertools.count(1)

        self._atoms: Dict[AtomId, Atom] = {}
        self._in_links: Dict[AtomId, Set[AtomId]] = {}  # atom -> link ids mentioning it
        self._by_pred: Dict[AtomId, Set[AtomId]] = {}  # predicate -> link ids using it

        self._dedup_links = dedup_links
        self._link_key_index: Dict[Tuple[AtomId, Tuple[AtomId, ...]], AtomId] = {}

        self._label_index: Dict[str, List[AtomId]] = {}

        self._validators = []

        # Intern maps for canonical "kinds" and "predicates"
        self._kind_intern: Dict[str, AtomId] = {}
        self._pred_intern: Dict[str, AtomId] = {}

        # Namespaces (user-facing API surface)
        self.add = AddAPI(self)
        self.check = CheckAPI(self)
        self.retrieve = RetrieveAPI(self)

        install_api_predicates(self)

        # Optional defaults
        if with_defaults:
            from .defaults import install_defaults

            install_defaults(self)

    # -----------------------
    # Atom primitives
    # -----------------------

    def _alloc(self) -> AtomId:
        return next(self._ids)

    def _store_atom(self, a: Atom) -> None:
        self._atoms[a.id] = a
        if a.label:
            self._label_index.setdefault(a.label, []).append(a.id)
        self._in_links.setdefault(a.id, set())

    def atom(self, atom_id: AtomId) -> Atom:
        return self._atoms[atom_id]

    def find_by_label(self, label: str) -> List[AtomId]:
        return list(self._label_index.get(label, []))

    # -----------------------
    # Interning (kinds / predicates)
    # -----------------------

    def kind(self, name: str, *, intern: bool = True) -> AtomId:
        if intern:
            existing = self._kind_intern.get(name)
            if existing is not None:
                return existing
        kid = self._alloc()
        self._store_atom(KindAtom(id=kid, label=name, created_at_utc=_utc_now_iso()))
        if intern:
            self._kind_intern[name] = kid
        return kid

    def predicate(
        self,
        name: str,
        *,
        arity: int = -1,
        roles: Tuple[str, ...] = (),
        anti_reflexive: bool = False,
        acyclic: bool = False,
        intern: bool = True,
        template: str | None = None,
    ) -> AtomId:
        if intern:
            existing = self._pred_intern.get(name)
            if existing is not None:
                return existing

        pid = self._alloc()
        self._store_atom(
            PredicateAtom(
                id=pid,
                label=name,
                created_at_utc=_utc_now_iso(),
                arity=arity,
                roles=roles,
                template=template,
                anti_reflexive=anti_reflexive,
                acyclic=acyclic,
            )
        )
        self._by_pred.setdefault(pid, set())
        if intern:
            self._pred_intern[name] = pid
        return pid

    def _resolve_kind(self, kind: NameOrId) -> AtomId:
        if isinstance(kind, int):
            return kind
        return self._kind_intern.get(kind) or self.kind(kind, intern=True)

    def _resolve_predicate(self, predicate: NameOrId) -> AtomId:
        if isinstance(predicate, int):
            return predicate
        existing = self._pred_intern.get(predicate)
        if existing is None:
            raise KeyError(
                f"Unknown predicate '{predicate}'. Define it via A.predicate()."
            )
        return existing

    def _resolve_one_by_label(self, label: str) -> AtomId:
        hits = self.find_by_label(label)
        if not hits:
            raise KeyError(f"No atom found with label '{label}'.")
        return hits[0]

    def _resolve_many_by_label(self, label: str) -> List[AtomId]:
        return self.find_by_label(label)

    # -----------------------
    # Create node/link
    # -----------------------

    def _create_node(
        self, label: str, *, kind: NameOrId = 0, props: Optional[Dict[str, Any]] = None
    ) -> AtomId:
        nid = self._alloc()
        n = Node(
            id=nid,
            label=label,
            created_at_utc=_utc_now_iso(),
            kind=self._resolve_kind(kind) if kind else 0,
            props=tuple(sorted((props or {}).items())),
        )
        self._store_atom(n)
        return nid

    def _create_link(
        self,
        predicate: NameOrId,
        args: Iterable[AtomId],
        *,
        label: Optional[str] = None,
    ) -> AtomId:
        pid = self._resolve_predicate(predicate)
        p = self._atoms[pid]
        if not isinstance(p, PredicateAtom):
            raise TypeError(f"Predicate {pid} is not a PredicateAtom (corrupt store?)")

        a = tuple(int(x) for x in args)
        p.check_arity(len(a))

        for v in getattr(self, "_validators", []):
            v(self, p, a)

        if p.anti_reflexive and len(a) >= 2 and len(set(a)) != len(a):
            raise ValueError(f"{p.label} forbids repeated args")

        if p.acyclic and len(a) == 2:
            src, dst = a
            if src == dst:
                raise ValueError(f"{p.label} forbids self-loop")
            if self._reachable_via_predicate(dst, src, pid):
                raise ValueError(f"{p.label} would create a cycle")

        if self._dedup_links:
            key = (pid, a)
            existing = self._link_key_index.get(key)
            if existing is not None:
                return existing

        lid = self._alloc()
        l = Link(
            id=lid, label=label, created_at_utc=_utc_now_iso(), predicate=pid, args=a
        )
        self._store_atom(l)

        self._by_pred.setdefault(pid, set()).add(lid)
        for x in a:
            self._in_links.setdefault(x, set()).add(lid)

        if self._dedup_links:
            self._link_key_index[(pid, a)] = lid

        return lid

    # -----------------------
    # Queries/index helpers
    # -----------------------

    def links_of(self, predicate: NameOrId) -> Set[AtomId]:
        pid = self._resolve_predicate(predicate)
        return set(self._by_pred.get(pid, set()))

    def in_links(
        self, atom_id: AtomId, *, predicate: Optional[NameOrId] = None
    ) -> Set[AtomId]:
        hits = set(self._in_links.get(atom_id, set()))
        if predicate is None:
            return hits
        pid = self._resolve_predicate(predicate)
        return {
            lid
            for lid in hits
            if isinstance(self._atoms.get(lid), Link)
            and self._atoms[lid].predicate == pid
        }

    def out(self, link_id: AtomId) -> Tuple[AtomId, ...]:
        a = self._atoms.get(link_id)
        if not isinstance(a, Link):
            raise TypeError(f"{link_id} is not a Link")
        return a.args

    def _reachable_via_predicate(
        self, start: AtomId, goal: AtomId, predicate_id: AtomId
    ) -> bool:
        if start == goal:
            return True
        seen: Set[AtomId] = set()
        stack: List[AtomId] = [start]
        pred_links = self._by_pred.get(predicate_id, set())

        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            for lid in pred_links:
                lk = self._atoms[lid]
                assert isinstance(lk, Link)
                if len(lk.args) != 2:
                    continue
                src, dst = lk.args
                if src != u:
                    continue
                if dst == goal:
                    return True
                if dst not in seen:
                    stack.append(dst)
        return False

    # -----------------------
    # Pretty
    # -----------------------

    def pretty(self, atom_id: AtomId, *, max_depth: int = 2) -> str:
        def _p(aid: AtomId, d: int) -> str:
            a = self._atoms[aid]
            if isinstance(a, Node):
                return a.label
            if isinstance(a, KindAtom):
                return f"Kind({a.label})"
            if isinstance(a, PredicateAtom):
                return f"Pred({a.label})"
            if isinstance(a, Link):
                pred = self._atoms[a.predicate]
                pred_name = (
                    pred.label
                    if isinstance(pred, PredicateAtom)
                    else f"Pred#{a.predicate}"
                )
                if d <= 0:
                    return f"{pred_name}(...)#{aid}"
                inner = ", ".join(_p(x, d - 1) for x in a.args)
                return f"{pred_name}({inner})"
            return f"Atom#{aid}"

        return _p(atom_id, max_depth)

    # -----------------------
    # Convenience: time
    # -----------------------

    def time_node(self, unix_time: Optional[float] = None) -> AtomId:
        if unix_time is None:
            unix_time = time.time()
        return self.add.node(f"t={unix_time:.3f}", kind="TimeInstant")

    # --------------------------------
    # Convenience: validator wrapper
    # --------------------------------

    def add_validator(self, fn) -> None:
        self._validators.append(fn)
