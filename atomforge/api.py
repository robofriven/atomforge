from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .atoms import AtomId, Link, Node
from .common import NameOrId, ByLabelCreationError

# atom_space/api.py


class AddAPI:
    def __init__(self, A: Any) -> None:
        self.A = A

    def link(
        self, predicate: NameOrId, *args: AtomId, label: Optional[str] = None
    ) -> AtomId:
        return self.A._create_link(predicate, args, label=label)

    def node(
        self,
        label: str,
        *,
        kind: NameOrId = "Entity",
        props: Optional[Dict[str, Any]] = None,
        intern: bool = True,  # <--- NEW
    ) -> AtomId:
        if intern:
            hits = self.A.find_by_label(label)
            if hits:
                # Optional: prefer matching kind if multiple hits exist
                if kind:
                    kid = self.A._resolve_kind(kind)
                    for hid in hits:
                        a = self.A._atoms[hid]
                        if isinstance(a, Node) and a.kind == kid:
                            return hid
                return hits[0]
        return self.A._create_node(label, kind=kind, props=props)

    def entity(self, label: str, **kw: Any) -> AtomId:
        return self.node(label, kind="Entity", **kw)

    def class_(self, label: str, **kw: Any) -> AtomId:
        return self.node(label, kind="Class", **kw)

    def new_entity(self, label: str, **kw: Any) -> AtomId:
        return self.node(label, kind="Entity", intern=False, **kw)

    def new_class(self, label: str, **kw: Any) -> AtomId:
        return self.node(label, kind="Class", intern=False, **kw)


class CheckAPI:
    def __init__(self, A: Any) -> None:
        self.A = A

    def link(self, predicate: NameOrId, *args: AtomId) -> bool:
        pid = self.A._resolve_predicate(predicate)
        want = tuple(int(x) for x in args)
        for lid in self.A._by_pred.get(pid, set()):
            lk = self.A._atoms[lid]
            assert isinstance(lk, Link)
            if lk.args == want:
                return True
        return False

    def link_by_label(self, predicate: NameOrId, *labels: str) -> bool:
        return bool(self.A.retrieve.link_by_label(predicate, *labels))


class RetrieveAPI:
    def __init__(self, A: Any) -> None:
        self.A = A

    def link(
        self, predicate: NameOrId, *args: AtomId
    ) -> List[Tuple[AtomId, Tuple[AtomId, ...]]]:
        pid = self.A._resolve_predicate(predicate)
        want = tuple(int(x) for x in args)
        out: List[Tuple[AtomId, Tuple[AtomId, ...]]] = []
        for lid in self.A._by_pred.get(pid, set()):
            lk = self.A._atoms[lid]
            assert isinstance(lk, Link)
            if lk.args == want:
                out.append((lid, lk.args))
        return out

    # api.py (inside class RetrieveAPI)

    def link_by_label(
        self, predicate: NameOrId, *labels: str
    ) -> List[Tuple[AtomId, Tuple[AtomId, ...]]]:
        """
        Supports '*' as a wildcard label for any arg position.

        Examples:
          link_by_label("At", "Greg", "*")     -> where is Greg?
          link_by_label("At", "*", "Tavern")   -> who's at the Tavern?
          link_by_label("Believes", "Joe", "*")-> what does Joe believe?
        """
        pid = self.A._resolve_predicate(predicate)

        # Build pools, but allow wildcards.
        pools: List[Optional[set[int]]] = []
        for lbl in labels:
            if lbl == "*" or (isinstance(lbl, str) and lbl.strip() == "*"):
                pools.append(None)  # unconstrained slot
            else:
                pool = set(self.A._resolve_many_by_label(lbl))
                if not pool:
                    return []
                pools.append(pool)

        # Seed candidates:
        # If any slot is constrained, use in_links from that pool to reduce scanning.
        # Otherwise fall back to scanning all links for the predicate.
        candidate_lids: Optional[set[int]] = None
        for pool in pools:
            if pool is None:
                continue
            # Union in_links over all ids in this pool
            seeded: set[int] = set()
            for atom_id in pool:
                seeded |= self.A.in_links(atom_id, predicate=pid)
            candidate_lids = seeded
            break

        if candidate_lids is None:
            candidate_lids = set(self.A._by_pred.get(pid, set()))

        out: List[Tuple[AtomId, Tuple[AtomId, ...]]] = []
        for lid in candidate_lids:
            lk = self.A._atoms[lid]
            assert isinstance(lk, Link)
            if lk.predicate != pid:
                continue
            if len(lk.args) != len(pools):
                continue

            ok = True
            for got, pool in zip(lk.args, pools):
                if pool is None:  # wildcard slot
                    continue
                if got not in pool:
                    ok = False
                    break

            if ok:
                out.append((lid, lk.args))

        return out
