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

    def link_by_label(
        self, predicate: NameOrId, *labels: str
    ) -> List[Tuple[AtomId, Tuple[AtomId, ...]]]:
        pid = self.A._resolve_predicate(predicate)
        pools = [self.A._resolve_many_by_label(lbl) for lbl in labels]
        if any(len(p) == 0 for p in pools):
            return []

        out: List[Tuple[AtomId, Tuple[AtomId, ...]]] = []
        for lid in self.A._by_pred.get(pid, set()):
            lk = self.A._atoms[lid]
            assert isinstance(lk, Link)
            if len(lk.args) != len(pools):
                continue
            ok = True
            for got, pool in zip(lk.args, pools):
                if got not in pool:
                    ok = False
                    break
            if ok:
                out.append((lid, lk.args))
        return out
