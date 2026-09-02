"""Supported public boundary for AtomForge consumers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Type, Union

from .atoms import (
    Atom,
    AtomId,
    Intersection,
    RawAtomResult,
    SearchResult,
    StructuralSearchResult,
    TraversalResult,
)
from .core import AtomSpace

NameOrId = Union[str, AtomId]


class AtomSpaceAPI:
    """Flat public graph API.

    Consumers should depend on this type rather than on Core storage.
    """

    __slots__ = ("__space",)

    def __init__(self, space: AtomSpace) -> None:
        if not isinstance(space, AtomSpace):
            raise TypeError("space must be an AtomSpace")
        self.__space = space

    @classmethod
    def create(cls, *, dedup_links: bool = True) -> "AtomSpaceAPI":
        return cls(AtomSpace(dedup_links=dedup_links))

    @classmethod
    def load(cls, path: Union[str, Path]) -> "AtomSpaceAPI":
        return cls(AtomSpace.load(path))

    @property
    def current_predicate(self) -> AtomId:
        return self.__space.current_predicate

    @property
    def delete_predicate(self) -> AtomId:
        return self.__space.delete_predicate

    def kind(
        self,
        name: str,
        *,
        intern: bool = True,
        confidence: float = 1.0,
    ) -> AtomId:
        return self.__space.kind(
            name, intern=intern, confidence=confidence
        )

    def predicate(
        self,
        name: str,
        *,
        arity: int = -1,
        roles: Tuple[str, ...] = (),
        anti_reflexive: bool = False,
        acyclic: bool = False,
        intern: bool = True,
        template: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        return self.__space.predicate(
            name,
            arity=arity,
            roles=roles,
            anti_reflexive=anti_reflexive,
            acyclic=acyclic,
            intern=intern,
            template=template,
            confidence=confidence,
        )

    def create_node(
        self,
        label: Optional[str],
        *,
        kind: NameOrId = 0,
        props: Optional[Dict[str, Any]] = None,
        intern: bool = False,
        confidence: float = 1.0,
    ) -> AtomId:
        return self.__space.create_node(
            label,
            kind=kind,
            props=props,
            intern=intern,
            confidence=confidence,
        )

    def create_link(
        self,
        predicate: NameOrId,
        *args: AtomId,
        label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        return self.__space.create_link(
            predicate,
            *args,
            label=label,
            confidence=confidence,
        )

    def create_ligature(
        self, name: str, *args: AtomId, label: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AtomId:
        return self.__space.create_ligature(
            name, *args, label=label, confidence=confidence
        )

    def get(self, atom_id: AtomId) -> Optional[Atom]:
        return self.__space.get(atom_id)

    def get_raw(self, atom_id: AtomId) -> RawAtomResult:
        return self.__space.get_raw(atom_id)

    def search(
        self,
        *,
        label: Optional[str] = None,
        atom_type: Optional[Type[Atom]] = None,
        predicate: Optional[NameOrId] = None,
        kind: Optional[NameOrId] = None,
    ) -> List[SearchResult]:
        return self.__space.search(
            label=label, atom_type=atom_type, predicate=predicate, kind=kind
        )

    def search_raw(
        self,
        *,
        label: Optional[str] = None,
        atom_type: Optional[Type[Atom]] = None,
        predicate: Optional[NameOrId] = None,
        kind: Optional[NameOrId] = None,
    ) -> List[RawAtomResult]:
        return self.__space.search_raw(
            label=label, atom_type=atom_type, predicate=predicate, kind=kind
        )

    def traverse(
        self, start: AtomId, *, max_depth: Optional[int] = None
    ) -> List[TraversalResult]:
        return self.__space.traverse(start, max_depth=max_depth)

    def traverse_raw(
        self, start: AtomId, *, max_depth: Optional[int] = None
    ) -> List[RawAtomResult]:
        return self.__space.traverse_raw(start, max_depth=max_depth)

    def intersection(
        self, seeds: Iterable[AtomId], *, max_depth: int
    ) -> List[Intersection]:
        return self.__space.intersection(seeds, max_depth=max_depth)

    def containers(
        self, start: AtomId, container_definition: AtomId, *, max_depth: int
    ) -> List[StructuralSearchResult]:
        return self.__space.containers(
            start, container_definition, max_depth=max_depth
        )

    def nearest_hub(
        self, start: AtomId, *, max_depth: int
    ) -> List[StructuralSearchResult]:
        return self.__space.nearest_hub(start, max_depth=max_depth)

    def find_by_label(self, label: str) -> List[AtomId]:
        return self.__space.find_by_label(label)

    def links_of(self, predicate: NameOrId) -> Set[AtomId]:
        return self.__space.links_of(predicate)

    def find_links(self, predicate: NameOrId, *args: AtomId) -> List[SearchResult]:
        return self.__space.find_links(predicate, *args)

    def has_link(self, predicate: NameOrId, *args: AtomId) -> bool:
        return self.__space.has_link(predicate, *args)

    def find_links_by_label(
        self, predicate: NameOrId, *labels: str
    ) -> List[SearchResult]:
        return self.__space.find_links_by_label(predicate, *labels)

    def has_link_by_label(self, predicate: NameOrId, *labels: str) -> bool:
        return self.__space.has_link_by_label(predicate, *labels)

    def in_ligatures(self, atom_id: AtomId) -> Set[AtomId]:
        return self.__space.in_ligatures(atom_id)

    def in_links(
        self, atom_id: AtomId, *, predicate: Optional[NameOrId] = None
    ) -> Set[AtomId]:
        return self.__space.in_links(atom_id, predicate=predicate)

    def out(self, link_id: AtomId) -> Tuple[AtomId, ...]:
        return self.__space.out(link_id)

    def connected(self, ligature_id: AtomId) -> Tuple[AtomId, ...]:
        return self.__space.connected(ligature_id)

    def confidence(self, atom_id: AtomId) -> float:
        return self.__space.confidence(atom_id)

    def set_confidence(self, atom_id: AtomId, value: float) -> None:
        self.__space.set_confidence(atom_id, value)

    def delete(self, atom_id: AtomId) -> AtomId:
        return self.__space.delete(atom_id)

    def make_current(self, atom_id: AtomId) -> AtomId:
        return self.__space.make_current(atom_id)

    def remove_current(self, atom_id: AtomId) -> None:
        self.__space.remove_current(atom_id)

    def pretty(self, atom_id: AtomId, *, max_depth: int = 2) -> str:
        return self.__space.pretty(atom_id, max_depth=max_depth)

    def save(self, path: Union[str, Path]) -> None:
        self.__space.save(path)
