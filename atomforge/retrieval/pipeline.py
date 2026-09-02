"""Candidate-to-intersection-to-container structural retrieval pipeline."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, List, Sequence, Tuple

from atomforge import AtomSpaceAPI, Ligature
from atomforge.atoms import AtomId

from .models import (
    BoundedSubgraph,
    ContainerEvidence,
    IntersectionEvidence,
    RankedContainer,
    RetrievedLigature,
    RetrievalResult,
)


class StructuralRetriever:
    """Run deterministic retrieval using only supported AtomForge operations."""

    def __init__(self, api: AtomSpaceAPI) -> None:
        if not isinstance(api, AtomSpaceAPI):
            raise TypeError("api must be an AtomSpaceAPI")
        self._api = api

    def validate_candidates(
        self, candidate_atom_ids: Iterable[AtomId]
    ) -> Tuple[AtomId, ...]:
        candidates = tuple(sorted(set(candidate_atom_ids)))
        if not candidates:
            raise ValueError("at least one candidate Atom ID is required")
        for atom_id in candidates:
            if self._api.get(atom_id) is None:
                raise ValueError(f"candidate Atom ID {atom_id} is deleted")
        return candidates

    def find_intersections(
        self, candidates: Sequence[AtomId], *, max_depth: int
    ) -> Tuple[IntersectionEvidence, ...]:
        found: List[IntersectionEvidence] = []
        candidate_set = set(candidates)
        for intersection in self._api.intersection(
            candidates, max_depth=max_depth
        ):
            if intersection.atom_id in candidate_set:
                continue
            depths = tuple(sorted(
                (candidate, depth)
                for candidate, depth in intersection.depths.items()
                if depth >= 0
            ))
            found.append(IntersectionEvidence(
                atom_id=intersection.atom_id,
                candidate_depths=depths,
                coverage=len(depths),
                combined_depth=sum(depth for _, depth in depths),
            ))
        return tuple(sorted(
            found,
            key=lambda item: (-item.coverage, item.combined_depth, item.atom_id),
        ))

    @staticmethod
    def select_intersections(
        intersections: Sequence[IntersectionEvidence],
    ) -> Tuple[IntersectionEvidence, ...]:
        if not intersections:
            return ()
        best_coverage = max(item.coverage for item in intersections)
        best_depth = min(
            item.combined_depth
            for item in intersections
            if item.coverage == best_coverage
        )
        return tuple(sorted((item for item in intersections if (
            item.coverage, item.combined_depth
        ) == (best_coverage, best_depth)), key=lambda item: item.atom_id))

    def find_containers(
        self,
        intersections: Sequence[IntersectionEvidence],
        container_definition_id: AtomId,
        *,
        max_depth: int,
    ) -> Tuple[ContainerEvidence, ...]:
        evidence = []
        for intersection in intersections:
            for container in self._api.containers(
                intersection.atom_id,
                container_definition_id,
                max_depth=max_depth,
            ):
                evidence.append(ContainerEvidence(
                    intersection_atom_id=intersection.atom_id,
                    container_atom_id=container.atom_id,
                    intersection_depth=container.depth,
                    candidate_depths=intersection.candidate_depths,
                    coverage=intersection.coverage,
                    combined_depth=(
                        intersection.combined_depth + container.depth
                    ),
                ))
        return tuple(sorted(evidence, key=lambda item: (
            item.container_atom_id,
            item.combined_depth,
            item.intersection_atom_id,
        )))

    @staticmethod
    def rank_containers(
        evidence: Sequence[ContainerEvidence],
    ) -> Tuple[RankedContainer, ...]:
        grouped = defaultdict(list)
        for item in evidence:
            grouped[item.container_atom_id].append(item)
        ranked = []
        for atom_id, items in grouped.items():
            items.sort(key=lambda item: (
                item.combined_depth, item.intersection_atom_id
            ))
            candidate_ids = tuple(sorted({
                candidate
                for item in items
                for candidate, _ in item.candidate_depths
            }))
            ranked.append(RankedContainer(
                atom_id=atom_id,
                candidate_ids=candidate_ids,
                coverage=len(candidate_ids),
                structural_depth=min(item.combined_depth for item in items),
                evidence=tuple(items),
            ))
        return tuple(sorted(ranked, key=lambda item: (
            -item.coverage, item.structural_depth, item.atom_id
        )))

    @staticmethod
    def select_containers(
        containers: Sequence[RankedContainer],
    ) -> Tuple[RankedContainer, ...]:
        if not containers:
            return ()
        best_coverage = max(item.coverage for item in containers)
        best_depth = min(
            item.structural_depth
            for item in containers
            if item.coverage == best_coverage
        )
        return tuple(sorted((item for item in containers if (
            item.coverage, item.structural_depth
        ) == (best_coverage, best_depth)), key=lambda item: item.atom_id))

    def retrieve_bounded(
        self, container_atom_id: AtomId, *, max_depth: int
    ) -> BoundedSubgraph:
        traversal = self._api.traverse(
            container_atom_id, max_depth=max_depth
        )
        atom_ids = tuple(sorted(item.matched_id for item in traversal))
        depth_by_id = {item.matched_id: item.depth for item in traversal}
        ligatures = tuple(sorted((
            RetrievedLigature(item.matched_id, item.atom.name, item.atom.args)
            for item in traversal
            if isinstance(item.atom, Ligature)
        ), key=lambda item: item.atom_id))
        return BoundedSubgraph(
            container_atom_id=container_atom_id,
            atom_ids=atom_ids,
            atom_depths=tuple(sorted(depth_by_id.items())),
            ligatures=ligatures,
        )

    def retrieve(
        self,
        candidate_atom_ids: Iterable[AtomId],
        *,
        container_definition_id: AtomId,
        intersection_depth: int,
        container_depth: int,
        retrieval_depth: int,
    ) -> RetrievalResult:
        for name, value in (
            ("intersection_depth", intersection_depth),
            ("container_depth", container_depth),
            ("retrieval_depth", retrieval_depth),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        candidates = self.validate_candidates(candidate_atom_ids)
        # Validate the definition even when no intersection is found.
        self._api.containers(
            candidates[0], container_definition_id, max_depth=0
        )
        intersections = self.find_intersections(
            candidates, max_depth=intersection_depth
        )
        relevant = self.select_intersections(intersections)
        evidence = self.find_containers(
            relevant, container_definition_id, max_depth=container_depth
        )
        ranked = self.rank_containers(evidence)
        selected = self.select_containers(ranked)
        subgraphs = tuple(
            self.retrieve_bounded(item.atom_id, max_depth=retrieval_depth)
            for item in selected
        )
        return RetrievalResult(
            candidate_atom_ids=candidates,
            intersections=intersections,
            relevant_intersections=relevant,
            container_evidence=evidence,
            ranked_containers=ranked,
            selected_container_atom_ids=tuple(
                item.atom_id for item in selected
            ),
            subgraphs=subgraphs,
        )


def retrieve(
    api: AtomSpaceAPI,
    candidate_atom_ids: Iterable[AtomId],
    *,
    container_definition_id: AtomId,
    intersection_depth: int,
    container_depth: int,
    retrieval_depth: int,
) -> RetrievalResult:
    """Convenience entry point for one structural retrieval."""
    return StructuralRetriever(api).retrieve(
        candidate_atom_ids,
        container_definition_id=container_definition_id,
        intersection_depth=intersection_depth,
        container_depth=container_depth,
        retrieval_depth=retrieval_depth,
    )
