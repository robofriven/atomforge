"""domain — vocabularies for specific worlds, built on stdagent.

Core is domain-agnostic mechanics.  ``stdagent`` is one level up:
vocabularies that presuppose agents but no particular world.  The
packages here are the third level: each presupposes a world — its
kinds of acts, its relationships, its stakes — and says so in its
docstring.

Dependency rule: a domain package may depend on Core and on any
``stdagent`` module; ``stdagent`` never depends on a domain package,
and Core depends on neither.  A graph that is not about a domain's
world simply never installs that domain's vocabulary.

- ``consent`` — presupposes agents with boundaries, over act types
  from ``stdagent.acts``: who has consented to what, what is
  permitted, and what is a hard limit.
"""
