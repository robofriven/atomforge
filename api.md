# AtomForge Public API

Consumers use `atomforge.AtomSpaceAPI`. The facade is flat and explicit; Core's
storage dictionaries and indexes are not public API.

## Model

Every stored object has a permanent positive integer `AtomId`. IDs are never
redirected or reused. The stored primitives are `Node`, `Predicate`, `Ligature`,
`KindAtom`, `PredicateAtom`, and `Transition`.

Atoms are structurally immutable. Create a new atom to represent a changed
thing or relationship. Confidence is separate mutable metadata and may be
updated without changing graph structure.

Core creates two unary predicates and owns the binary `Transition(A, B)` atom
form:

- `Current(X)` marks an atom as currently active or relevant. It is managed only
  through `make_current` and `remove_current`.
- `Delete(X)` permanently makes `X` logically absent while retaining its
  physical atom and tombstones all live Predicates, Transitions, and Ligatures
  incident to `X`.
- `Transition(A, B)` directly records a change from state atom `A` to state
  atom `B`.

`Current`, `Delete`, and `Transition` are reserved Core relationship names.

Normal APIs hide atoms targeted by `Delete`; logical traversal stops at every
deleted atom or relationship. Raw APIs traverse and expose purely physical
history and report deletion status. Core has no phantom or ephemeral primitive.

## Construction and persistence

### `AtomSpaceAPI.create`

```python
AtomSpaceAPI.create(*, dedup_predicates: bool = True) -> AtomSpaceAPI
```

Creates a graph containing the Core-owned Current and Delete PredicateAtoms.
With predicate deduplication enabled, creating the same live
`(predicate, args)` Predicate returns its existing ID.

```python
from atomforge import AtomSpaceAPI

api = AtomSpaceAPI.create()
```

### `AtomSpaceAPI.load`

```python
AtomSpaceAPI.load(path: str | pathlib.Path) -> AtomSpaceAPI
```

Loads the exact current JSON schema, rebuilds physical indexes and the derived
deletion-ID set, and validates
atoms, confidence, vocabulary interning, structural contracts, Current
assertions, and Delete assertions. Missing or unsupported versions raise
`SchemaVersionError`; malformed data raises `MalformedPersistenceError` or a
specific invariant error.

```python
api = AtomSpaceAPI.load("graph.json")
```

### `save`

```python
api.save(path: str | pathlib.Path) -> None
```

Persists atoms, confidence, canonical vocabulary maps, allocation state, Core
predicate IDs, and predicate-deduplication configuration. Derived indexes and the
deletion-ID set are rebuilt on load and are not persisted.

```python
api.save("graph.json")
```

## Core vocabulary

### `current_predicate`

```python
api.current_predicate -> AtomId
```

Returns the ID of Core's unary `Current` PredicateAtom.

### `delete_predicate`

```python
api.delete_predicate -> AtomId
```

Returns the ID of Core's unary `Delete` PredicateAtom.

### `kind`

```python
api.kind(
    name: str,
    *,
    intern: bool = True,
    confidence: float = 1.0,
) -> AtomId
```

Creates a KindAtom. With `intern=True`, the canonical live KindAtom for `name`
is returned if it already exists. `Transition` is reserved for Core's
relationship form and cannot be used as a Kind name.

```python
person = api.kind("Person")
```

### `predicate`

```python
api.predicate(
    name: str,
    *,
    arity: int = -1,
    roles: tuple[str, ...] = (),
    anti_reflexive: bool = False,
    acyclic: bool = False,
    intern: bool = True,
    template: str | None = None,
    confidence: float = 1.0,
) -> AtomId
```

Creates a PredicateAtom defining a globally indexed Predicate form. `arity=-1` is
variadic. Roles are descriptive. Anti-reflexive predicates reject repeated
arguments; acyclic binary predicates reject cycles. Renderer may use `template`.
For an interned name, every immutable structure field must match the existing
PredicateAtom or creation raises `GraphInvariantError`.
The names `Current`, `Delete`, and `Transition` are unavailable to domain
predicates.

```python
contains = api.predicate(
    "Contains", arity=2, roles=("container", "member")
)
```

## Atom creation

### `create_node`

```python
api.create_node(
    label: str | None,
    *,
    kind: str | AtomId,
    props: dict[str, Any] | None = None,
    intern: bool = False,
    confidence: float = 1.0,
) -> AtomId
```

Creates a Node. `kind` is required and must identify a live KindAtom. Node properties
are immutable application data. `intern=True` returns an existing live Node
with the same label only when both kind and properties exactly match; a conflict
raises `GraphInvariantError`. Labels are otherwise not identity.

```python
john = api.create_node("John", kind=person, props={"source": "import"})
```

### `create_predicate`

```python
api.create_predicate(
    predicate: str | AtomId,
    *args: AtomId,
    label: str | None = None,
    confidence: float = 1.0,
) -> AtomId
```

Creates a Predicate application and applies its structural contract. The
predicate and every argument must be live. Arguments may reference any stored
atom primitive. All Core-owned predicates are rejected here;
use their dedicated operations. An exact Predicate identity that has ever been
deleted cannot be recreated. A live Current assertion cannot be an argument.

```python
group_kind = api.kind("Group")
group = api.create_node("group", kind=group_kind)
membership = api.create_predicate(contains, group, john)
```

`create_link` is retained as a temporary compatibility alias.

### `create_ligature`

```python
api.create_ligature(
    name: str,
    *args: AtomId,
    label: str | None = None,
    confidence: float = 1.0,
) -> AtomId
```

Creates a named semantic relationship reached through topology. A Ligature has
no PredicateAtom, does not enter `_by_pred`, and has no relation-name index. Its
nonempty name belongs to the relationship atom itself, and it must connect at
least one live atom. A live Current assertion cannot be a connection.

```python
body_side = api.kind("BodySide")
left = api.create_node("left", kind=body_side)
arm = api.create_ligature("Arm", john, left)
```

## Access

### `get`

```python
api.get(atom_id: AtomId) -> Atom | None
```

Returns the physical atom unless a Delete assertion targets it, in which case
it returns `None`. Unknown IDs raise `UnknownAtomError`.

### `get_raw`

```python
api.get_raw(atom_id: AtomId) -> RawAtomResult
```

Returns physical history regardless of logical deletion:

- `atom`: the stored Atom.
- `atom_id`: its permanent ID.
- `confidence`: its current confidence metadata.
- `deleted`: whether a Delete assertion targets it.

```python
raw = api.get_raw(membership)
print(raw.atom, raw.confidence, raw.deleted)
```

### `find_by_label`

```python
api.find_by_label(label: str) -> list[AtomId]
```

Returns live physical IDs with the exact indexed label.

## Search

### `search`

```python
api.search(
    *,
    label: str | None = None,
    atom_type: type[Atom] | None = None,
    predicate: str | AtomId | None = None,
    kind: str | AtomId | None = None,
) -> list[SearchResult]
```

Filters physical atoms and omits deleted matches. Each result contains the live
`atom` and its permanent `matched_id`.

```python
from atomforge import Ligature, Node, Predicate, Transition

people = api.search(atom_type=Node, kind=person)
predicates = api.search(atom_type=Predicate, predicate=contains)
ligatures = api.search(atom_type=Ligature)
transitions = api.search(atom_type=Transition)
```

### `search_raw`

```python
api.search_raw(
    *,
    label: str | None = None,
    atom_type: type[Atom] | None = None,
    predicate: str | AtomId | None = None,
    kind: str | AtomId | None = None,
) -> list[RawAtomResult]
```

Applies the same physical filters without hiding deleted atoms.

### `predicates_of`

```python
api.predicates_of(predicate: str | AtomId) -> set[AtomId]
```

Returns live Predicate IDs indexed under the PredicateAtom.

### `find_predicates`

```python
api.find_predicates(predicate: str | AtomId, *args: AtomId) -> list[SearchResult]
```

Returns live Predicates exactly matching the definition and argument tuple.

### `has_predicate`

```python
api.has_predicate(predicate: str | AtomId, *args: AtomId) -> bool
```

Returns whether `find_predicates()` has a match.

### `find_predicates_by_label`

```python
api.find_predicates_by_label(
    predicate: str | AtomId,
    *labels: str,
) -> list[SearchResult]
```

Matches Predicate arguments by exact live labels. `"*"` is a wildcard position.

### `has_predicate_by_label`

```python
api.has_predicate_by_label(predicate: str | AtomId, *labels: str) -> bool
```

Returns whether `find_predicates_by_label()` has a match.

## Local topology

### `in_predicates`

```python
api.in_predicates(
    atom_id: AtomId,
    *,
    predicate: str | AtomId | None = None,
) -> set[AtomId]
```

Reads only the atom's local incoming-reference bucket and returns live incident
Predicates. The optional definition is resolved once and filters those candidates.

### `in_ligatures`

```python
api.in_ligatures(atom_id: AtomId) -> set[AtomId]
```

Reads only the atom's local incoming-reference bucket and returns live incident
Ligatures. It does not scan atoms, Ligatures, or relation names.

### `in_transitions`

```python
api.in_transitions(atom_id: AtomId) -> set[AtomId]
```

Returns the live Transition atoms for which `atom_id` is either endpoint.

### `predicate_args`

```python
api.predicate_args(predicate_id: AtomId) -> tuple[AtomId, ...]
```

Returns a live Predicate's argument IDs, omitting arguments targeted by Delete.

### `connected`

```python
api.connected(ligature_id: AtomId) -> tuple[AtomId, ...]
```

Returns a live Ligature's connected IDs, omitting atoms targeted by Delete.

### `transition_args`

```python
api.transition_args(transition_id: AtomId) -> tuple[AtomId, AtomId]
```

Returns the direct `(before, after)` argument pair of a live Transition.

## Traversal

### `traverse`

```python
api.traverse(
    start: AtomId,
    *,
    max_depth: int | None = None,
) -> list[TraversalResult]
```

Traverses logical topology breadth-first. It follows Predicate definitions and
arguments, Transition endpoints, Ligature connections, and incoming
relationships, but does not follow `Node.kind` definition edges. This Kind boundary prevents a search from
escaping through a shared definition into unrelated graph structure. Traversal
hard-stops at deleted atoms and relationships and never crosses through them.
Each result contains `atom`, permanent `matched_id`, and `depth`, where the
starting atom has depth zero.

### `traverse_raw`

```python
api.traverse_raw(
    start: AtomId,
    *,
    max_depth: int | None = None,
) -> list[RawAtomResult]
```

Traverses purely physical topology and includes deleted atoms with their raw
deletion status and traversal `depth`. It uses the same Kind boundary as
logical traversal. This operation does not call logical resolution or filtering
helpers.

### `containers`

```python
api.containers(
    start: AtomId,
    container_definition: AtomId,
    *,
    max_depth: int,
) -> list[StructuralSearchResult]
```

Traverses outward from `start` and returns each reachable live `Node` whose
Kind is `container_definition`. Each result contains `atom_id` and its
breadth-first `depth`. This is a structural, Kind-safe operation and performs no
semantic ranking.

### `nearest_hub`

```python
api.nearest_hub(
    start: AtomId,
    *,
    max_depth: int,
) -> list[StructuralSearchResult]
```

Returns the nearest reachable live Nodes whose canonical Kind is `Hub`. All
hubs at the minimum discovered depth are returned; farther hubs are excluded.
Each result contains `atom_id` and `depth`. An empty list is returned when no
hub is reachable within `max_depth` or no live canonical `Hub` Kind exists.
This operation is Kind-safe and does not rank equally distant hubs.

## Confidence

### `confidence`

```python
api.confidence(atom_id: AtomId) -> float
```

Returns confidence for a live atom.

### `set_confidence`

```python
api.set_confidence(atom_id: AtomId, value: float) -> None
```

Updates confidence without changing graph structure. Values in `[0, 1]` are
accepted. Creation requires confidence in `(0, 1]`. Confidence zero does not
delete an atom.

## Current and deletion

### `transition`

```python
api.transition(
    before: AtomId,
    after: AtomId,
    *,
    label: str | None = None,
    confidence: float = 1.0,
) -> AtomId
```

Creates and returns one binary `Transition` relationship atom whose arguments
are exactly `(before, after)`. It is neither a Node nor a Predicate application;
there is no intermediate structural atom.

If `Current(before)` exists, Core removes it and ensures `Current(after)`
exists. If `before` is not Current, no Current assertions are changed. Labels
remain optional human-readable metadata.

```python
api.make_current(before)
change = api.transition(before, after)
assert api.has_predicate(api.current_predicate, after)
```

### `make_current`

```python
api.make_current(atom_id: AtomId) -> AtomId
```

Creates and returns a `Current(atom_id)` Predicate. A duplicate live Current
assertion raises `DuplicateCurrentError`. Different atoms may be Current at the
same time. Generic `create_predicate` rejects the Core-owned Current definition. A
Current assertion cannot itself be made Current or used by another Predicate,
Transition, or Ligature.

### `remove_current`

```python
api.remove_current(atom_id: AtomId) -> None
```

Physically removes the unary `Current(atom_id)` assertion. It does not create a
Delete assertion, and the target atom remains live. A later `make_current` call
may create a new assertion for the same target. Removal affects only that flag;
it performs no deletion cascade.

### `delete`

```python
api.delete(atom_id: AtomId) -> AtomId
```

Creates and returns an immutable `Delete(atom_id)` Predicate. Normal access then
hides the target and every live Predicate, Transition, or Ligature incident to it; raw access
retains their physical history. The tombstone is permanent, and attempting to
recreate an exact deleted Predicate raises `InvalidAtomOperationError`. Repeated
deletion raises `AlreadyDeletedError`. Core vocabulary atoms, Delete assertion
Predicates and Current assertions cannot be deleted. Generic `create_predicate` rejects
all Core-owned predicate names; Transitions are created with `transition()`.

Deletion closure is cycle-safe: revisiting an already scheduled relationship
does not fail. Deleting a KindAtom fails while any stored Node uses it, and
deleting a PredicateAtom fails while any live Predicate uses it. Core does not
cascade-delete those users merely to remove their definition; unused
application definitions may be deleted normally.

```python
deletion = api.delete(membership)
assert api.get(membership) is None
assert api.get_raw(membership).deleted
assert api.get(deletion).predicate == api.delete_predicate
```

## Rendering

### `pretty`

```python
api.pretty(atom_id: AtomId, *, max_depth: int = 2) -> str
```

Returns compact logical rendering for diagnostics. Deleted atoms render as
`"<deleted>"`; Predicates use their PredicateAtom label, Transitions render as
`Transition(before, after)`, and Ligatures use their own name.

For template-based rendering, pass the facade to
`atomforge.renderer.Renderer`.

## Public data types

- `Atom(id, label, created_at_utc)`
- `Node(kind, props)`
- `Predicate(predicate, args)`
- `Transition(args=(before, after))`
- `Ligature(name, args)`
- `KindAtom`
- `PredicateAtom(arity, roles, template, anti_reflexive, acyclic)`
- `RawAtomResult(atom, atom_id, confidence, deleted)`
- `SearchResult(atom, matched_id)`
- `TraversalResult(atom, matched_id, depth)`
- `StructuralSearchResult(atom_id, depth)`

## Public errors

- `UnknownAtomError`
- `UnknownPredicateError`
- `InvalidAtomOperationError`
- `AlreadyDeletedError`
- `InvalidConfidenceError`
- `DuplicateCurrentError`
- `SchemaVersionError`
- `GraphInvariantError`
- `MalformedPersistenceError`

All invalid operations fail explicitly; command methods do not return success
booleans.
