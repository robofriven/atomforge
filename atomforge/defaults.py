from __future__ import annotations

from typing import Dict, Optional, Tuple

from .atoms import AtomId, Node, PredicateAtom
from .core import AtomSpace
from .predicates import install_default_predicates

# Predicate label -> tuple of expected kind names per arg position.
# Use None to mean "don't enforce this arg yet".
DEFAULT_ARG_KIND_RULES: Dict[str, Tuple[Optional[str], ...]] = {
    # "IsA": ("None", "None"),
    # "HappensAt": (None, "TimeInstant"),
}


def validate_arg_kinds(
    space: AtomSpace, predicate_atom: PredicateAtom, arg_ids: Tuple[AtomId, ...]
) -> None:
    rules = getattr(space, "_arg_kind_rules", None)
    if not rules:
        return

    pred_name = predicate_atom.label
    if not pred_name:
        return

    expected = rules.get(pred_name)
    if expected is None:
        return

    for index, expected_kind_name in enumerate(expected):
        if expected_kind_name is None:
            continue
        if index >= len(arg_ids):
            break

        atom_id = arg_ids[index]
        atom = space._atoms.get(atom_id)

        if not isinstance(atom, Node):
            raise TypeError(
                f"{pred_name} arg{index} must be a Node(kind={expected_kind_name}), "
                f"got {type(atom).__name__} (id={atom_id})"
            )

        expected_kind_id = space._kind_intern.get(expected_kind_name)
        if expected_kind_id is None:
            raise KeyError(
                f"Kind '{expected_kind_name}' not installed "
                f"(needed by rule for {pred_name} arg{index})"
            )

        if atom.kind != expected_kind_id:
            got_kind_atom = space._atoms.get(atom.kind)
            got_kind_name = getattr(got_kind_atom, "label", str(atom.kind))
            got_label = getattr(atom, "label", None)
            raise TypeError(
                f"{pred_name} arg{index} must be kind '{expected_kind_name}', got '{got_kind_name}' "
                f"(atom={got_label!r} id={atom_id})"
            )


def install_defaults(space: AtomSpace) -> None:
    space.K = _init_default_kinds(space)
    space.P = install_default_predicates(space)

    # Store rule configuration (data)
    space._arg_kind_rules = dict(DEFAULT_ARG_KIND_RULES)

    # Register validators (behavior)
    space._validators.append(validate_arg_kinds)

    # Convenience anchor
    space.now = space.add.node("NOW", kind="Entity")


def _init_default_kinds(space: AtomSpace) -> Dict[str, AtomId]:
    return {
        "Entity": space.kind("Entity"),
        "Class": space.kind("Class"),
        "TimeInstant": space.kind("TimeInstant"),
        "Proposition": space.kind("Proposition"),
    }


def _init_default_predicates(space: AtomSpace) -> Dict[str, AtomId]:
    P: Dict[str, AtomId] = {}
    P["IsA"] = space.predicate(
        "IsA",
        arity=2,
        roles=("instance", "class"),
        anti_reflexive=True,
        acyclic=True,
    )
    P["HasA"] = space.predicate("HasA", arity=2, roles=("owner", "thing"))
    P["Wants"] = space.predicate("Wants", arity=2, roles=("agent", "target"))
    P["Not"] = space.predicate("Not", arity=1, roles=("proposition",))
    P["Because"] = space.predicate(
        "Because", arity=-1, roles=("conclusion", "evidence")
    )
    P["Believes"] = space.predicate("Believes", arity=2, roles=("agent", "proposition"))
    P["HappensAt"] = space.predicate(
        "HappensAt", arity=2, roles=("proposition", "time")
    )
    return P
