# AtomForge Public API

Consumers use `atomforge.AtomSpaceAPI`. The facade is flat and explicit; Core's
storage dictionaries and indexes are not public API.

## Model

Every stored object has a permanent positive integer `AtomId`. IDs are never
redirected or reused. The stored primitives are `Node`, `Link`, `Ligature`,
`KindAtom`, and `PredicateAtom`.

Atoms are structurally immutable. Create a new atom to represent a changed
thing or relationship. Confidence is separate mutable metadata and may be
updated without changing graph structure.

Core creates two unary predicates:

- `Current(X)` marks an atom as currently active or relevant. It is managed only
  through `make_current` and `remove_current`.
- `Delete(X)` permanently makes `X` logically absent while retaining its
  physical atom and tombstones all live Links and Ligatures incident to `X`.

`Current` and `Delete` are reserved Core predicate names. Calls to `predicate`
with either name raise `InvalidAtomOperationError`, regardless of structure or
interning options.

Normal APIs hide atoms targeted by `Delete`; logical traversal stops at every
deleted atom or relationship. Raw APIs traverse and expose purely physical
history and report deletion status. Core has no phantom or ephemeral primitive.

## Construction and persistence

### `AtomSpaceAPI.create`

```python
AtomSpaceAPI.create(*, dedup_links: bool = True) -> AtomSpaceAPI
```

Creates a graph containing only the Core-owned `Current` and `Delete`
PredicateAtoms. With link deduplication enabled, creating the same live
`(predicate, args)` Link returns its existing ID.

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
predicate IDs, and link-deduplication configuration. Derived indexes and the
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
is returned if it already exists.

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

Creates a PredicateAtom defining a globally indexed Link form. `arity=-1` is
variadic. Roles are descriptive. Anti-reflexive predicates reject repeated
arguments; acyclic binary predicates reject cycles. Renderer may use `template`.
For an interned name, every immutable structure field must match the existing
PredicateAtom or creation raises `GraphInvariantError`.
The names `Current` and `Delete` are unavailable to domain predicates.

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
    kind: str | AtomId = 0,
    props: dict[str, Any] | None = None,
    intern: bool = False,
    confidence: float = 1.0,
) -> AtomId
```

Creates a Node. A nonzero kind must identify a live KindAtom. Node properties
are immutable application data. `intern=True` returns an existing live Node
with the same label only when both kind and properties exactly match; a conflict
raises `GraphInvariantError`. Labels are otherwise not identity.

```python
john = api.create_node("John", kind=person, props={"source": "import"})
```

### `create_link`

```python
api.create_link(
    predicate: str | AtomId,
    *args: AtomId,
    label: str | None = None,
    confidence: float = 1.0,
) -> AtomId
```

Creates a predicate-backed Link and applies its structural contract. The
predicate and every argument must be live. Arguments may reference any stored
atom primitive. The Core-owned Current and Delete predicates are rejected here;
use their dedicated operations. An exact Link identity that has ever been
deleted cannot be recreated. A live Current assertion cannot be an argument.

```python
group = api.create_node("group")
membership = api.create_link(contains, group, john)
```

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
left = api.create_node("left")
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
from atomforge import Ligature, Link, Node

people = api.search(atom_type=Node, kind=person)
links = api.search(atom_type=Link, predicate=contains)
ligatures = api.search(atom_type=Ligature)
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

### `links_of`

```python
api.links_of(predicate: str | AtomId) -> set[AtomId]
```

Returns live Link IDs indexed under the predicate.

### `find_links`

```python
api.find_links(predicate: str | AtomId, *args: AtomId) -> list[SearchResult]
```

Returns live Links exactly matching the predicate and complete argument tuple.

### `has_link`

```python
api.has_link(predicate: str | AtomId, *args: AtomId) -> bool
```

Returns whether `find_links()` has a match.

### `find_links_by_label`

```python
api.find_links_by_label(
    predicate: str | AtomId,
    *labels: str,
) -> list[SearchResult]
```

Matches Link arguments by exact live labels. `"*"` is a wildcard position.

### `has_link_by_label`

```python
api.has_link_by_label(predicate: str | AtomId, *labels: str) -> bool
```

Returns whether `find_links_by_label()` has a match.

## Local topology

### `in_links`

```python
api.in_links(
    atom_id: AtomId,
    *,
    predicate: str | AtomId | None = None,
) -> set[AtomId]
```

Reads only the atom's local incoming-reference bucket and returns live incident
Links. The optional predicate is resolved once and filters those candidates.

### `in_ligatures`

```python
api.in_ligatures(atom_id: AtomId) -> set[AtomId]
```

Reads only the atom's local incoming-reference bucket and returns live incident
Ligatures. It does not scan atoms, Ligatures, or relation names.

### `out`

```python
api.out(link_id: AtomId) -> tuple[AtomId, ...]
```

Returns a live Link's argument IDs, omitting arguments targeted by Delete.

### `connected`

```python
api.connected(ligature_id: AtomId) -> tuple[AtomId, ...]
```

Returns a live Ligature's connected IDs, omitting atoms targeted by Delete.

## Traversal

### `traverse`

```python
api.traverse(
    start: AtomId,
    *,
    max_depth: int | None = None,
) -> list[TraversalResult]
```

Traverses logical topology. It follows Node kinds, Link predicates and
arguments, Ligature connections, and incoming relationships, but hard-stops at
deleted atoms and relationships and never crosses through them. Each result
contains `atom` and permanent `matched_id`.

### `traverse_raw`

```python
api.traverse_raw(
    start: AtomId,
    *,
    max_depth: int | None = None,
) -> list[RawAtomResult]
```

Traverses purely physical topology and includes deleted atoms with their raw
deletion status. This operation does not call logical resolution or filtering
helpers.

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

### `make_current`

```python
api.make_current(atom_id: AtomId) -> AtomId
```

Creates and returns a `Current(atom_id)` Link. A duplicate live Current
assertion raises `DuplicateCurrentError`. Different atoms may be Current at the
same time. Generic `create_link` rejects the Core-owned Current predicate. A
Current assertion cannot itself be made Current or used by another Link or
Ligature.

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

Creates and returns an immutable `Delete(atom_id)` Link. Normal access then
hides the target and every live Link or Ligature incident to it; raw access
retains their physical history. The tombstone is permanent, and attempting to
recreate an exact deleted Link raises `InvalidAtomOperationError`. Repeated
deletion raises `AlreadyDeletedError`. Core's Current/Delete PredicateAtoms,
Delete assertion Links, and Current assertions cannot be deleted. Generic
`create_link` rejects both Core predicates.

Deletion closure is cycle-safe: revisiting an already scheduled relationship
does not fail. Deleting a KindAtom fails while any live Node uses it, and
deleting a PredicateAtom fails while any live Link uses it. Core does not
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
`"<deleted>"`; Links use their PredicateAtom label and Ligatures use their own
name.

For template-based rendering, pass the facade to
`atomforge.renderer.Renderer`.

## Public data types

- `Atom(id, label, created_at_utc)`
- `Node(kind, props)`
- `Link(predicate, args)`
- `Ligature(name, args)`
- `KindAtom`
- `PredicateAtom(arity, roles, template, anti_reflexive, acyclic)`
- `RawAtomResult(atom, atom_id, confidence, deleted)`
- `SearchResult(atom, matched_id)`
- `TraversalResult(atom, matched_id)`

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
