# AtomForge structural retrieval

This package implements deterministic retrieval after candidate selection. It
does not accept text, create embeddings, or perform semantic ranking.

```python
from atomforge.retrieval import retrieve

result = retrieve(
    api,
    candidate_atom_ids,
    container_definition_id=container_kind,
    intersection_depth=4,
    container_depth=3,
    retrieval_depth=3,
)
```

The pipeline is deliberately inspectable:

1. validate candidate Atom IDs;
2. run Core intersection search and retain per-candidate depths;
3. rank intersections by candidate coverage, then combined depth;
4. retain every intersection tied at the best structural rank;
5. run Core container search from those intersections;
6. rank containers by candidate coverage, then structural depth;
7. retain every container tied at the best structural rank;
8. run Kind-safe Core traversal from each selected container, bounded by
   `retrieval_depth`.

`RetrievalResult` preserves all intersections, the relevant intersection tier,
container evidence, ranked and selected containers, and each bounded subgraph.
This makes ambiguity and every structural decision visible to callers.

`retrieval_depth` is the explicit context boundary. Choose it to match the
topology used to model a container; retrieval never resumes from the original
candidates after container selection.
