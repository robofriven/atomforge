from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .atoms import AtomId, Node, Link, KindAtom, PredicateAtom

# Compile once
_TEMPLATE_TOKEN = re.compile(r"\{(?:(a|paren|join):)?([A-Za-z_][A-Za-z0-9_]*)\}")


def _is_ident(s: str) -> bool:
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", s))


def _norm_role(role: str, idx: int) -> str:
    # Always provide arg0/arg1... keys. Roles like "Any" are not helpful as keys.
    if not role or role == "Any" or not _is_ident(role):
        return f"arg{idx}"
    return role


@dataclass(frozen=True)
class RenderOptions:
    max_depth: int = 4
    show_ids: bool = False
    show_kinds: bool = False
    use_roles: bool = True


class Renderer:
    def __init__(self, space) -> None:
        self.space = space

    # -----------------------
    # Structural renderer (debug)
    # -----------------------

    def render(self, atom_id: AtomId, *, opts: RenderOptions = RenderOptions()) -> str:
        atom = self.space._atoms[atom_id]

        if isinstance(atom, Node):
            text = atom.label or f"Node#{atom_id}"
            if opts.show_kinds and atom.kind:
                kind_atom = self.space._atoms.get(atom.kind)
                kind_name = getattr(kind_atom, "label", str(atom.kind))
                text = f"{text}:{kind_name}"
            return self._maybe_id(text, atom_id, opts)

        if isinstance(atom, KindAtom):
            text = f"Kind({atom.label})" if atom.label else f"Kind#{atom_id}"
            return self._maybe_id(text, atom_id, opts)

        if isinstance(atom, PredicateAtom):
            text = f"Pred({atom.label})" if atom.label else f"Pred#{atom_id}"
            return self._maybe_id(text, atom_id, opts)

        if isinstance(atom, Link):
            return self.render_link(atom_id, opts=opts)

        return self._maybe_id(f"Atom#{atom_id}", atom_id, opts)

    def render_link(
        self, link_id: AtomId, *, opts: RenderOptions = RenderOptions()
    ) -> str:
        return self._render_link_inner(link_id, depth=opts.max_depth, opts=opts)

    def _render_link_inner(
        self, link_id: AtomId, depth: int, *, opts: RenderOptions
    ) -> str:
        atom = self.space._atoms[link_id]
        if not isinstance(atom, Link):
            return self.render(link_id, opts=opts)

        pred_atom = self.space._atoms.get(atom.predicate)
        pred_name = getattr(pred_atom, "label", None) or f"Pred#{atom.predicate}"

        if depth <= 0:
            return self._maybe_id(f"{pred_name}(...)", link_id, opts)

        rendered_args: List[str] = []
        for i, aid in enumerate(atom.args):
            rendered_args.append(self._render_arg(aid, depth - 1, opts=opts))

        if opts.use_roles and isinstance(pred_atom, PredicateAtom) and pred_atom.roles:
            rendered_args = [
                f"{pred_atom.role_for_index(i)}={txt}"
                if pred_atom.role_for_index(i)
                else txt
                for i, txt in enumerate(rendered_args)
            ]

        inside = ", ".join(rendered_args)
        text = f"{pred_name}({inside})"
        return self._maybe_id(text, link_id, opts)

    def _render_arg(self, atom_id: AtomId, depth: int, *, opts: RenderOptions) -> str:
        atom = self.space._atoms[atom_id]
        if isinstance(atom, Link):
            return self._render_link_inner(atom_id, depth=depth, opts=opts)
        return self.render(atom_id, opts=opts)

    # -----------------------
    # Pretty-first renderer (human)
    # -----------------------

    def render_pretty(self, atom_id: AtomId, *, depth: int = 4) -> str:
        atom = self.space._atoms[atom_id]
        if isinstance(atom, Link):
            return self._render_link_pretty(atom, depth=depth)
        return self._render_atom_pretty(atom_id)

    def _render_atom_pretty(self, atom_id: AtomId) -> str:
        atom = self.space._atoms[atom_id]
        if isinstance(atom, Node):
            return atom.label or f"#{atom_id}"
        return self.render(atom_id)

    @staticmethod
    def _article_for(phrase: str) -> str:
        s = phrase.strip().lower()
        if not s:
            return "a"
        return "an" if s[0] in "aeiou" else "a"

    @staticmethod
    def _join_english(items: List[str]) -> str:
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} and {items[1]}"
        return ", ".join(items[:-1]) + f", and {items[-1]}"

    def _render_link_pretty(self, link: Link, *, depth: int) -> str:
        """
        Template-driven pretty rendering.

        Uses pred_atom.template if present.
        Template tokens support:
          {role}             -> substituted value
          {a:role}           -> adds a/an article
          {paren:role}       -> wraps in (...) if that arg is a Link
          {join:role}        -> joins all args mapped to that role (useful for variadic)
        Always provides arg0, arg1, ... keys.
        """
        if depth <= 0:
            return "…"

        pred_atom = self.space._atoms.get(link.predicate)
        template = getattr(pred_atom, "template", None) if pred_atom else None

        # No template? Fall back to structural renderer.
        if not template or not isinstance(template, str) or not template.strip():
            return self.render(link.id)

        def r(aid: AtomId) -> str:
            return self.render_pretty(aid, depth=depth - 1)

        def is_link(aid: AtomId) -> bool:
            return isinstance(self.space._atoms.get(aid), Link)

        mapping: Dict[str, str] = {}
        role_to_vals: Dict[str, List[Tuple[AtomId, str]]] = {}

        roles = getattr(pred_atom, "roles", None) if pred_atom else None

        for i, aid in enumerate(link.args):
            txt = r(aid)
            mapping[f"arg{i}"] = txt

            role_name = roles[i] if roles and i < len(roles) else ""
            key = _norm_role(role_name, i)

            # Add role-key mapping if it isn't already set.
            mapping.setdefault(key, txt)
            role_to_vals.setdefault(key, []).append((aid, txt))

        def repl(m: re.Match) -> str:
            directive = m.group(1)  # a / paren / join / None
            key = m.group(2)

            if directive == "join":
                items = [txt for (_aid, txt) in role_to_vals.get(key, [])]
                return self._join_english(items)

            txt = mapping.get(key, "")

            if directive == "a":
                art = self._article_for(txt)
                return f"{art} {txt}".strip()

            if directive == "paren":
                vals = role_to_vals.get(key, [])
                if vals and is_link(vals[0][0]):
                    return f"({vals[0][1]})"
                return txt

            return txt

        out = _TEMPLATE_TOKEN.sub(repl, template.strip())
        return out

    @staticmethod
    def _maybe_id(text: str, atom_id: AtomId, opts: RenderOptions) -> str:
        if opts.show_ids:
            return f"{text}#{atom_id}"
        return text

