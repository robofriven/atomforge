"""Inspectable result shapes for deterministic structural retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from atomforge.atoms import AtomId


@dataclass(frozen=True, slots=True)
class IntersectionEvidence:
    atom_id: AtomId
    candidate_depths: Tuple[Tuple[AtomId, int], ...]
    coverage: int
    combined_depth: int


@dataclass(frozen=True, slots=True)
class ContainerEvidence:
    intersection_atom_id: AtomId
    container_atom_id: AtomId
    intersection_depth: int
    candidate_depths: Tuple[Tuple[AtomId, int], ...]
    coverage: int
    combined_depth: int


@dataclass(frozen=True, slots=True)
class RankedContainer:
    atom_id: AtomId
    candidate_ids: Tuple[AtomId, ...]
    coverage: int
    structural_depth: int
    evidence: Tuple[ContainerEvidence, ...]


@dataclass(frozen=True, slots=True)
class RetrievedLigature:
    atom_id: AtomId
    name: str
    args: Tuple[AtomId, ...]


@dataclass(frozen=True, slots=True)
class BoundedSubgraph:
    container_atom_id: AtomId
    atom_ids: Tuple[AtomId, ...]
    atom_depths: Tuple[Tuple[AtomId, int], ...]
    ligatures: Tuple[RetrievedLigature, ...]


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    candidate_atom_ids: Tuple[AtomId, ...]
    intersections: Tuple[IntersectionEvidence, ...]
    relevant_intersections: Tuple[IntersectionEvidence, ...]
    container_evidence: Tuple[ContainerEvidence, ...]
    ranked_containers: Tuple[RankedContainer, ...]
    selected_container_atom_ids: Tuple[AtomId, ...]
    subgraphs: Tuple[BoundedSubgraph, ...]

    @property
    def retrieved_atom_ids(self) -> Tuple[AtomId, ...]:
        return tuple(sorted({
            atom_id
            for subgraph in self.subgraphs
            for atom_id in subgraph.atom_ids
        }))

    @property
    def retrieved_ligatures(self) -> Tuple[RetrievedLigature, ...]:
        by_id = {
            ligature.atom_id: ligature
            for subgraph in self.subgraphs
            for ligature in subgraph.ligatures
        }
        return tuple(by_id[atom_id] for atom_id in sorted(by_id))
