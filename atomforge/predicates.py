# predicates.py
from __future__ import annotations

from types import MethodType
from typing import Any, Dict, Tuple

from .atoms import AtomId

# One canonical place: what predicates exist + their structural metadata.
# Add to this dict and you're basically done.
from typing import Dict, Any

DEFAULT_PREDICATE_SPECS: Dict[str, Dict[str, Any]] = {
    # --- Core ontology ---
    "IsA": dict(
        arity=2,
        roles=("instance", "class"),
        template="{instance} is a {class}",
        anti_reflexive=True,
        acyclic=True,
    ),
    "HasA": dict(
        arity=2,
        roles=("owner", "thing"),
        template="{owner} has {thing}",
    ),
    "Called": dict(
        arity=2,
        roles=("thing", "name"),
        template="{thing} is called {name}",
    ),
    # --- Mental / epistemic ---
    "Wants": dict(
        arity=2,
        roles=("agent", "target"),
        template="{agent} wants {target}",
    ),
    "Believes": dict(
        arity=2,
        roles=("agent", "proposition"),
        template="{agent} believes {proposition}",
    ),
    "Claims": dict(
        arity=2,
        roles=("speaker", "proposition"),
        template="{speaker} claims {proposition}",
    ),
    "Knows": dict(
        arity=2,
        roles=("agent", "fact"),
        template="{agent} knows {fact}",
    ),
    "Learns": dict(
        arity=2,
        roles=("agent", "topic"),
        template="{agent} learns {topic}",
    ),
    "Fears": dict(
        arity=2,
        roles=("agent", "thing"),
        template="{agent} fears {thing}",
    ),
    "Trusts": dict(
        arity=2,
        roles=("agent", "other"),
        template="{agent} trusts {other}",
    ),
    "Distrusts": dict(
        arity=2,
        roles=("agent", "other"),
        template="{agent} distrusts {other}",
    ),
    # --- Causality / logic / time ---
    "Because": dict(
        arity=-1,
        roles=("conclusion", "evidence"),
        template="{conclusion} because {evidence}",
    ),
    "Causes": dict(
        arity=2,
        roles=("cause", "effect"),
        template="{cause} causes {effect}",
    ),
    "LeadsTo": dict(
        arity=2,
        roles=("source", "outcome"),
        template="{source} leads to {outcome}",
    ),
    "HappensAt": dict(
        arity=2,
        roles=("proposition", "time"),
        template="{proposition} happens at {time}",
    ),
    "During": dict(
        arity=2,
        roles=("event", "time_or_event"),
        template="{event} happens during {time_or_event}",
    ),
    "Changes": dict(
        arity=2,
        roles=("thing", "new_state"),
        template="{thing} changes to {new_state}",
    ),
    # --- Action / interaction / state ---
    "Does": dict(
        arity=2,
        roles=("agent", "action"),
        template="{agent} does {action}",
    ),
    "At": dict(
        arity=2,
        roles=("thing", "place"),
        template="{thing} is at {place}",
    ),
    "With": dict(
        arity=2,
        roles=("thing", "other"),
        template="{thing} is with {other}",
    ),
    "IsFeeling": dict(
        arity=2,
        roles=("agent", "feeling"),
        template="{agent} is feeling {feeling}",
    ),
    "Sees": dict(
        arity=2,
        roles=("agent", "thing"),
        template="{agent} sees {thing}",
    ),
    "Can": dict(
        arity=2,
        roles=("agent", "ability"),
        template="{agent} can {ability}",
    ),
    "Needs": dict(
        arity=2,
        roles=("agent", "thing"),
        template="{agent} needs {thing}",
    ),
    "Uses": dict(
        arity=2,
        roles=("agent", "thing"),
        template="{agent} uses {thing}",
    ),
    "Consumes": dict(
        arity=2,
        roles=("agent", "resource"),
        template="{agent} consumes {resource}",
    ),
    # --- Unary wrappers / logical helpers ---
    "Axiom": dict(
        arity=1,
        roles=("proposition",),
        template="it is axiomatic that {proposition}",
    ),
    "Not": dict(
        arity=1,
        roles=("proposition",),
        template="it is not true that {proposition}",
    ),
    # --- Personal / world seed predicates ---
    "WorksAt": dict(
        arity=2,
        roles=("person", "organization"),
        template="{person} works at {organization}",
    ),
    "LivesIn": dict(
        arity=2,
        roles=("person", "place"),
        template="{person} lives in {place}",
    ),
    "Builds": dict(
        arity=2,
        roles=("builder", "project"),
        template="{builder} builds {project}",
    ),
    "IsWorkingOn": dict(
        arity=2,
        roles=("person", "project"),
        template="{person} is working on {project}",
    ),
    "Loves": dict(
        arity=2,
        roles=("lover", "beloved"),
        template="{lover} loves {beloved}",
    ),
    "Likes": dict(
        arity=2,
        roles=("person", "thing"),
        template="{person} likes {thing}",
    ),
    "Enjoys": dict(
        arity=2,
        roles=("person", "thing"),
        template="{person} enjoys {thing}",
    ),
    "Prefers": dict(
        arity=2,
        roles=("person", "thing"),
        template="{person} prefers {thing}",
    ),
    "Dislikes": dict(
        arity=2,
        roles=("person", "thing"),
        template="{person} dislikes {thing}",
    ),
    "Plays": dict(
        arity=2,
        roles=("person", "game_or_activity"),
        template="{person} plays {game_or_activity}",
    ),
    "Encourages": dict(
        arity=2,
        roles=("person", "other"),
        template="{person} encourages {other}",
    ),
    "Teaches": dict(
        arity=3,
        roles=("teacher", "student", "topic"),
        template="{teacher} teaches {student} about {topic}",
    ),
    "HasSkill": dict(
        arity=2,
        roles=("agent", "skill"),
        template="{agent} has the skill {skill}",
    ),
    "SkillLevel": dict(
        arity=3,
        roles=("agent", "skill", "level"),
        template="{agent}'s {skill} skill is level {level}",
    ),
    "HasSpell": dict(
        arity=2,
        roles=("agent", "spell"),
        template="{agent} knows the spell {spell}",
    ),
    "Casts": dict(
        arity=2,
        roles=("caster", "spell"),
        template="{caster} casts {spell}",
    ),
    "SpellEffect": dict(
        arity=2,
        roles=("spell", "effect"),
        template="{spell} produces {effect}",
    ),
    "HasMana": dict(
        arity=2,
        roles=("agent", "amount"),
        template="{agent} has {amount} mana",
    ),
    "ManaCost": dict(
        arity=2,
        roles=("spell", "amount"),
        template="{spell} costs {amount} mana",
    ),
    "RequiresSkill": dict(
        arity=2,
        roles=("ability", "skill"),
        template="{ability} requires the skill {skill}",
    ),
    "Discovers": dict(
        arity=2,
        roles=("agent", "thing"),
        template="{agent} discovers {thing}",
    ),
    "Guides": dict(
        arity=2,
        roles=("guide", "other"),
        template="{guide} guides {other}",
    ),
    "Trains": dict(
        arity=2,
        roles=("trainer", "student"),
        template="{trainer} trains {student}",
    ),
    "IsDangerous": dict(
        arity=1,
        roles=("thing",),
        template="{thing} is dangerous",
    ),
    "ExperimentsWith": dict(
        arity=2,
        roles=("agent", "thing"),
        template="{agent} experiments with {thing}",
    ),
    "HasClass": dict(
        arity=2,
        roles=("agent", "class"),
        template="{agent} has the class {class}",
    ),
    "HasTrait": dict(
        arity=2,
        roles=("agent", "trait"),
        template="{agent} has the trait {trait}",
    ),
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
