# predicates.py
from __future__ import annotations

from types import MethodType
from typing import Any, Dict, Tuple

from .atoms import AtomId

# One canonical place: what predicates exist + their structural metadata.
# Add to this dict and you're basically done.
DEFAULT_PREDICATE_SPECS: Dict[str, Dict[str, Any]] = {
    "IsA": dict(
        arity=2,
        roles=("instance", "class"),
        anti_reflexive=True,
        acyclic=True,
    ),
    "HasA": dict(arity=2, roles=("owner", "thing")),
    "Wants": dict(arity=2, roles=("agent", "target")),
    "Because": dict(arity=-1, roles=("conclusion", "evidence")),
    "Believes": dict(arity=2, roles=("agent", "proposition")),
    "HappensAt": dict(arity=2, roles=("proposition", "time")),
    # Story framing v0 (uncomment when you're ready)
    "Does": dict(arity=2, roles=("Any", "Any")),
    "At": dict(arity=2, roles=("thing", "place")),
    "Claims": dict(arity=2, roles=("speaker", "proposition")),
    "Called": dict(arity=2, roles=("thing", "name")),
    "Causes": dict(arity=2, roles=("cause", "effect")),
    "During": dict(arity=2, roles=("Any", "Any")),
    "With": dict(arity=2, roles=("Any", "Any")),
    "IsFeeling": dict(arity=2, roles=("Any", "Any")),
    "Sees": dict(arity=2, roles=("agent", "thing")),
    # Arity 1 Wrappers
    "Axiom": dict(
        arity=1, roles=("proposition")
    ),  # This is the "always and definitely true fact
    "Not": dict(arity=1, roles=("proposition",)),
}


def _snake(name: str) -> str:
    # IsA -> is_a, HappensAt -> happens_at
    out = []
    for i, ch in enumerate(name):
        if i and ch.isupper():
            prev = name[i - 1]
            nxt = name[i + 1] if i + 1 < len(name) else ""
            if prev.islower() or (nxt and nxt.islower()):
                out.append("_")
        out.append(ch.lower())
    return "".join(out)


# Some names need polish for Python (keyword-ish / style)
_METHOD_OVERRIDES = {
    "Not": "not_",
    "With": "with_",
}


def install_default_predicates(space: Any) -> Dict[str, AtomId]:
    """
    Registers the predicate atoms on the AtomSpace via space.predicate(...).
    Returns name -> predicate atom id (same convention as your current space.P).
    """
    P: Dict[str, AtomId] = {}
    for name, cfg in DEFAULT_PREDICATE_SPECS.items():
        P[name] = space.predicate(name, **cfg)
    return P


def install_api_predicates(A: Any) -> None:
    """
    Installs sugar methods on A.add / A.check / A.retrieve based on the registry.
    After this, you can call A.add.is_a(...), A.check.is_a(...), etc.
    """

    # ---- AddAPI sugar ----
    def make_add(pred_name: str):
        def _fn(self, *args: AtomId, label: str | None = None) -> AtomId:
            # label is optional; ignored if not used by caller
            return self.link(pred_name, *args, label=label)

        return _fn

    # ---- CheckAPI sugar ----
    def make_check(pred_name: str):
        def _fn(self, *args: AtomId) -> bool:
            return self.link(pred_name, *args)

        return _fn

    # ---- RetrieveAPI sugar ----
    def make_retrieve(pred_name: str):
        def _fn(self, *args: AtomId):
            return self.link(pred_name, *args)

        return _fn

    for pred_name, cfg in DEFAULT_PREDICATE_SPECS.items():
        meth = _METHOD_OVERRIDES.get(pred_name, _snake(pred_name))

        setattr(A.add, meth, MethodType(make_add(pred_name), A.add))
        setattr(A.check, meth, MethodType(make_check(pred_name), A.check))
        setattr(A.retrieve, meth, MethodType(make_retrieve(pred_name), A.retrieve))

        # Optional: by-label helpers for check/retrieve for fixed-arity predicates only
        arity = int(cfg.get("arity", -1))
        if arity != -1:
            by_label_name = f"{meth}_by_label"
            setattr(
                A.check,
                by_label_name,
                MethodType(
                    lambda self, *labels, _p=pred_name: self.link_by_label(_p, *labels),
                    A.check,
                ),
            )
            setattr(
                A.retrieve,
                by_label_name,
                MethodType(
                    lambda self, *labels, _p=pred_name: self.link_by_label(_p, *labels),
                    A.retrieve,
                ),
            )
