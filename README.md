# AtomForge

AtomForge is a minimal, domain-agnostic atom graph. Core owns identity, storage,
physical indexes, confidence, logical deletion, traversal, and persistence.
Applications own the meaning of their graph vocabulary.

The six stored atom primitives are:

- `Node` — a thing with a required live `KindAtom` reference.
- `Predicate` — an application of a `PredicateAtom` to ordered arguments.
- `Transition` — a Core-owned binary state-change relationship.
- `Ligature` — a named semantic relationship discovered through local topology.
- `KindAtom` — a Node category.
- `PredicateAtom` — a predicate definition/schema.

Atoms are structurally immutable. World changes are represented by creating new
atoms and relationships. Confidence is mutable Core metadata. Logical deletion
is represented by the Core-owned unary `Delete(X)` predicate: normal APIs hide
`X`, while raw APIs retain its physical history. Deletion also tombstones every
live Predicate, Transition, and Ligature incident to `X`. Core owns `Current(X)` as
removable plumbing rather than historical graph state.

`Current`, `Delete`, and `Transition` are reserved relationship names.
Application vocabulary cannot reuse them. Kind and predicate definitions may be deleted only while no
live Node or Predicate, respectively, uses them.

```python
from atomforge import AtomSpaceAPI

api = AtomSpaceAPI.create()
person = api.kind("Person")
food = api.kind("Food")
body_side = api.kind("BodySide")
likes = api.predicate("Likes", arity=2)

john = api.create_node("John", kind=person)
donuts = api.create_node("donuts", kind=food)
statement = api.create_predicate(likes, john, donuts, confidence=0.8)

left = api.create_node("left", kind=body_side)
arm = api.create_ligature("Arm", john, left)
assert arm in api.in_ligatures(john)

delete_assertion = api.delete(statement)
assert api.get(statement) is None
assert api.get_raw(statement).deleted
assert api.get(delete_assertion).predicate == api.delete_predicate
```

## Relational predicates

Relational behavior is optional and lives outside Core:

```python
from atomforge import AtomSpaceAPI
from atomforge.predicates.relational import install

api = AtomSpaceAPI.create()
rel = install(api)
place = api.kind("Place")

# Relational assertions canonicalize in the domain layer. Symmetric and
# transitive consequences are evaluated at query time, not stored as Predicates.
room = api.create_node("room", kind=place)
hallway = api.create_node("hallway", kind=place)
rel.relate(rel.Near, room, hallway)
assert rel.has(rel.Near, hallway, room)
assert not api.has_predicate(rel.Near, hallway, room)

```

Transitions are generic Core state machinery. A Transition atom directly
connects its source and result. Creating one moves `Current` only when its
source is Current:

```python
state = api.kind("State")
before = api.create_node("before", kind=state)
after = api.create_node("after", kind=state)
api.make_current(before)
change = api.transition(before, after, label="state changed")

assert api.transition_args(change) == (before, after)
assert not api.has_predicate(api.current_predicate, before)
assert api.has_predicate(api.current_predicate, after)
```

Actions are deliberately not Core or relational concepts. Domain layers may
associate their own first-class Action atoms with Transition atoms.

See [api.md](api.md) for the complete public API.

Structural traversal is breadth-first, depth-aware, and Kind-safe: searches do
not cross from a Node into its Kind definition. Core also provides deterministic
container and nearest-hub searches for retrieval pipelines; semantic candidate
selection and ranking remain application responsibilities.

The optional [`atomforge.retrieval`](atomforge/retrieval/README.md) package
implements the deterministic candidate → intersection → container → bounded
context pipeline on top of the supported Core façade.
