# AtomForge

AtomForge is a minimal, domain-agnostic atom graph. Core owns identity, storage,
physical indexes, confidence, logical deletion, traversal, and persistence.
Applications own the meaning of their graph vocabulary.

The five stored atom primitives are:

- `Node` — a thing.
- `Link` — a globally predicate-indexed relationship.
- `Ligature` — a named semantic relationship discovered through local topology.
- `KindAtom` — a Node category.
- `PredicateAtom` — a Link relationship form.

Atoms are structurally immutable. World changes are represented by creating new
atoms and relationships. Confidence is mutable Core metadata. Logical deletion
is represented by the Core-owned unary `Delete(X)` predicate: normal APIs hide
`X`, while raw APIs retain its physical history. Deletion also tombstones every
live Link and Ligature incident to `X`. Core owns `Current(X)` as removable
plumbing rather than historical graph state.

`Current` and `Delete` are reserved predicate names. Application predicates
cannot use them. Kind and predicate definitions may be deleted only while no
live Node or Link, respectively, uses them.

```python
from atomforge import AtomSpaceAPI

api = AtomSpaceAPI.create()
person = api.kind("Person")
likes = api.predicate("Likes", arity=2)

john = api.create_node("John", kind=person)
donuts = api.create_node("donuts")
statement = api.create_link(likes, john, donuts, confidence=0.8)

left = api.create_node("left")
arm = api.create_ligature("Arm", john, left)
assert arm in api.in_ligatures(john)

delete_assertion = api.delete(statement)
assert api.get(statement) is None
assert api.get_raw(statement).deleted
assert api.get(delete_assertion).predicate == api.delete_predicate
```

See [api.md](api.md) for the complete public API.
