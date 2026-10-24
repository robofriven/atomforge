"""stdagent — shipped predicate vocabularies that presuppose agents.

Core (the ``atomforge`` package) is domain-agnostic graph mechanics and
makes no assumptions about what a graph describes.  The modules in this
package are one level up: each is a vocabulary for worlds that contain
agents — things that hold stances, make claims, and commit.  A pure-data
graph (say, every coordinate of a mountain) needs none of them and would
bring its own predicates instead; even its logic may work differently.

Presuppositions, per module:

- ``logic`` — presupposes propositions (claims that can contradict,
  imply, or support one another).
- ``relational`` — presupposes things standing in spatial, temporal, and
  part/whole relations.
- ``speech`` — presupposes speakers.  ``Says`` mints the claim atoms
  other modules wrap; it is the foundation the rest of this shelf
  quietly stands on.
- ``epistemic`` — presupposes believers: holders whose Believes /
  Suspects / Knows are judged inside their own graph.  Depends on
  ``speech``.
- ``obligation`` — presupposes committers: agents that can want, need,
  promise, and agree.
- ``preferences`` — presupposes holders of stances (loves/likes/hates).
- ``feels`` — presupposes feelers: feelings are canonical ``Feeling``
  kind nodes hung on holders by one ``Feels`` predicate, with
  ``Because`` as the generic reason pointer.
- ``possession`` — presupposes holders of things: title (``Own``) and
  custody (``Holds``) as separate axes; ``Has`` is not coming back.
- ``acts`` — presupposes actors: act types are canonical ``Act`` kind
  nodes minted only from an approved vocabulary (unapproved labels
  queue as proposals); the mechanism predicate is ``Does``, alongside
  ``Restrains`` and the sex response predicates.
- ``actions`` — presupposes agents with objects and each other: the
  verb family partitions by its second argument — ``Use`` / ``Wears``
  / ``Play`` take objects; ``Gives`` takes a recipient agent and
  requires a payload (an act term or an object) on the frame.  It
  also registers the ``Object`` kind and its ``object_node`` factory
  (instances ungated; the verbs' object slots kind-gated).

Dependency rule: stdagent modules may depend on Core and on stdagent
modules below them (``preferences`` on ``logic``, ``epistemic`` on
``speech``); nothing here depends on any domain package, and Core never
depends on this package.
"""
