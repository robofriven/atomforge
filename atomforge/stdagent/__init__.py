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
- ``obligation`` — presupposes committers: agents that can want, need,
  promise, and agree.
- ``preferences`` — presupposes holders of stances (loves/likes/hates).

Dependency rule: stdagent modules may depend on Core (and ``preferences``
on ``logic``); nothing here depends on any domain package, and Core never
depends on this package.
"""
