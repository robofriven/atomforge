from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .atoms import AtomId, Node, Link, KindAtom, PredicateAtom


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
        if depth <= 0:
            return "…"

        pred_atom = self.space._atoms.get(link.predicate)
        pred_name = getattr(pred_atom, "label", None)

        args = link.args

        def r(aid: AtomId) -> str:
            return self.render_pretty(aid, depth=depth - 1)

        def r_paren_if_link(aid: AtomId) -> str:
            inner_atom = self.space._atoms.get(aid)
            txt = r(aid)
            if isinstance(inner_atom, Link):
                return f"({txt})"
            return txt

        if pred_name == "IsA" and len(args) == 2:
            subj = r(args[0])
            cls = r(args[1])
            art = self._article_for(cls)
            return f"{subj} is {art} {cls}"

        if pred_name == "HasA" and len(args) == 2:
            owner = r(args[0])
            thing = r(args[1])
            art = self._article_for(thing)
            return f"{owner} has {art} {thing}"

        if pred_name == "Wants" and len(args) == 2:
            agent = r(args[0])
            target = r(args[1])
            return f"{agent} wants {target}"

        if pred_name == "Believes" and len(args) == 2:
            agent = r(args[0])
            prop = r_paren_if_link(args[1])
            return f"{agent} believes that {prop}"

        if pred_name == "Not" and len(args) == 1:
            return f"not {r_paren_if_link(args[0])}"

        if pred_name == "Because" and len(args) >= 2:
            conclusion = r(args[0])
            evidence = [r(a) for a in args[1:]]
            return f"{conclusion} because {self._join_english(evidence)}"

        if pred_name == "HappensAt" and len(args) == 2:
            prop = r_paren_if_link(args[0])
            t = r(args[1])
            return f"{prop} happens at {t}"

        # fallback
        return self.render(link.id)

    @staticmethod
    def _maybe_id(text: str, atom_id: AtomId, opts: RenderOptions) -> str:
        if opts.show_ids:
            return f"{text}#{atom_id}"
        return text
