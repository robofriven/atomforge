"""Integration tests for Elena Brain v2 — the dense rebuild.

These load the built artifact (elena-brain-v2.json, produced by the
goal workspace's build_brain2.py) and run brain-realistic retrieval:
callbacks, events, act occurrence counts, consent queries, clock
integrity, the Super Wednesday union, preference machinery, and
plan-state hygiene. They live apart from tests/ on purpose: they
test a dataset, not the library.

Run from the repo root:
    python3 -m unittest discover -s tests_integration
"""

import unittest
from pathlib import Path

from atomforge import AtomSpaceAPI
from atomforge.retrieval import retrieve
from atomforge.stdagent.acts import install as install_acts
from atomforge.stdagent.epistemic import install as install_epistemic
from atomforge.stdagent.preferences import install as install_prefs
from atomforge.domain.consent import install as install_consent

BRAIN_PATH = (
    Path.home() / "workspace" / "goals"
    / "sillytavern-rp-memory-graph" / "hidden_files"
    / "elena-brain" / "elena-brain-v2.json"
)


class ElenaBrainV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = AtomSpaceAPI.load(BRAIN_PATH)
        cls.ep = install_epistemic(cls.api)
        cls.pf = install_prefs(cls.api)
        cls.co = install_consent(cls.api)
        cls.acts = install_acts(cls.api)
        cls.elena = cls.one("Elena")
        cls.robert = cls.one("Robert")

    @classmethod
    def one(cls, label):
        found = cls.api.find_by_label(label)
        assert len(found) == 1, f"label {label!r}: {len(found)} hits"
        return found[0]

    @classmethod
    def label_of(cls, atom_id):
        return cls.api.get(atom_id).label

    @classmethod
    def labels_containing(cls, fragment):
        out = []
        for result in cls.api.search():
            label = result.atom.label
            if label and fragment in label:
                out.append(result.atom.id)
        return out

    # -- scale and shape ------------------------------------------------

    def test_graph_scale(self):
        total = len(self.api.search())
        self.assertGreaterEqual(total, 6000)
        event_kind = self.api.kind("Event")
        events = [r for r in self.api.search()
                  if getattr(r.atom, "kind", None) == event_kind]
        self.assertGreaterEqual(len(events), 140)

    # -- events: the wedding via intersection retrieval -----------------

    def test_wedding_is_an_elena_robert_container(self):
        event_kind = self.api.kind("Event")
        result = retrieve(
            self.api, [self.elena, self.robert],
            container_definition_id=event_kind,
            intersection_depth=1, container_depth=3,
            retrieval_depth=1,
        )
        container_ids = {e.container_atom_id
                         for e in result.container_evidence}
        wedding = self.one("the wedding")
        self.assertIn(wedding, container_ids)

    def test_wife_and_husband_asserted(self):
        wife = self.api.predicate("Wife", arity=2)
        husband = self.api.predicate("Husband", arity=2)
        self.assertTrue(self.api.find_predicates(
            wife, self.robert, self.elena))
        self.assertTrue(self.api.find_predicates(
            husband, self.elena, self.robert))

    # -- acts: occurrence counting over canonical act nodes -------------

    def does_atoms(self, act_label):
        act = self.acts.act_node(act_label)
        found = []
        for actor in (self.elena, self.robert):
            found += self.api.find_predicates(
                self.acts.predicates["Does"], actor, act)
        return found

    def predicates_with(self, predicate_id, first_arg):
        """All predicate atoms with the given predicate whose
        first arg matches (find_predicates needs full args)."""
        return [r.atom for r in self.api.search(
            predicate=predicate_id) if r.atom.args[0] == first_arg]

    def test_rimming_occurrences_across_lines(self):
        # Occurrence counting per the design: the canonical
        # act's Does atoms are unique per (actor, act); the
        # performances enumerate via their EvidenceFor
        # groundings to distinct scene summaries (the prequel
        # game and the wedding-night assterpiece scene).
        atoms = self.does_atoms("rimming (on Elena)")
        self.assertEqual(len(atoms), 2)  # one per actor
        summaries = set()
        for result in atoms:
            for ground in self.predicates_with(
                    self.ep.EvidenceFor, result.atom.id):
                summaries.add(ground.args[1])
        self.assertGreaterEqual(len(summaries), 2)

    def test_safeword_acts_exist(self):
        self.assertGreaterEqual(len(self.does_atoms(
            "calling yellow — her first safeword use")), 1)
        self.assertGreaterEqual(len(self.does_atoms(
            "calling red — on the Sybian, her first red of "
            "the story")), 1)

    def test_sleep_game_retrieval(self):
        event_kind = self.api.kind("Event")
        sleep_act = self.acts.act_node("sleep-use")
        result = retrieve(
            self.api, [self.elena, sleep_act],
            container_definition_id=event_kind,
            intersection_depth=1, container_depth=3,
            retrieval_depth=1,
        )
        container_ids = {e.container_atom_id
                         for e in result.container_evidence}
        self.assertIn(self.one("the sleep game"), container_ids)

    # -- consent ----------------------------------------------------------

    def test_sleep_permission_with_anal_excluded(self):
        # UN-SKIPPED for v2 (this is the re-verification the v1 skip
        # demanded): consent was re-extracted through the new module
        # in the dense rebuild, so the sleep-use permission now has a
        # ConsentGranted record — asserted once, at its statement
        # scene (the W1D4 blanket-consent scene), addressed to the
        # graph owner by default, standing (NEVER_EXPIRES), with
        # anal carved out.
        sleep_act = self.acts.act_node("sleep-use")
        self.assertEqual(
            self.co.consent_state(self.robert, sleep_act, "W2D1"),
            "granted")
        grants = self.co.grants_of(self.robert)
        sleep_grants = [
            p for p in grants
            if self.api.get(p).args[1] == sleep_act]
        self.assertEqual(len(sleep_grants), 1)
        exclusions = self.co.exclusions_of(sleep_grants[0])
        self.assertIn(self.acts.act_node("anal"), exclusions)

    def test_hard_limits(self):
        self.assertGreaterEqual(
            len(self.co.hard_limits_of(self.elena)), 10)
        self.assertEqual(
            self.co.consent_state(
                self.elena,
                self.acts.act_node("cum on her face or hair"),
                "W2D1"),
            "hard_limit")
        self.assertEqual(
            self.co.consent_state(
                self.robert, self.acts.act_node("scat"), "W2D1"),
            "hard_limit")

    def test_consent_layer_only_sees_consent_atoms(self):
        # By Robert's ruling (2026-10-22), not a gap: consent state
        # is explicit only. Believes-wrapped consent is knowledge
        # about consent, never operative consent — believing you
        # have consent is not having it — so consent_state reads
        # bare consent atoms only, permanently. An act never
        # granted there reports the honest blank ("none") even
        # though the graph discusses it.
        act = self.acts.act_node("sixty-nine — the contest")
        self.assertEqual(
            self.co.consent_state(self.elena, act, "W2D1"), "none")

    # -- verses: the dense remembering layer ------------------------------

    def test_verses_cover_the_scenes(self):
        from atomforge.atoms import Ligature
        verse_links = [
            r.atom for r in self.api.search()
            if isinstance(r.atom, Ligature) and r.atom.name == "Verse"]
        # Every one of the 145 scenes carries multiple verses.
        self.assertGreaterEqual(len(verse_links), 145 * 3)
        summaries_with_verses = {link.args[0] for link in verse_links}
        self.assertGreaterEqual(len(summaries_with_verses), 145)

    # -- convictions: interpretations held as worldview -------------------

    def test_interpretation_held_as_conviction(self):
        # The B4 case: "he studies her like a person" is an
        # interpretation of Robert's interior. In v2 it is a
        # Conviction with a certainty chain — never Knows, never a
        # kind-marked claim.
        hits = self.labels_containing("studies her like a person")
        claims = [h for h in hits
                  if self.ep.conviction_of(self.elena, h) is not None]
        self.assertTrue(claims, "no Conviction over the reading")
        claim = claims[0]
        self.assertNotEqual(
            self.ep.tier_of(self.elena, claim), "Knows")
        certainty = self.ep.certainty_of(self.elena, claim)
        self.assertIsNotNone(certainty)
        self.assertGreater(certainty, 0)
        history = self.ep.certainty_history(self.elena, claim)
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[-1][0], certainty)

    # -- clock integrity ----------------------------------------------------

    def test_model_error_census(self):
        # v2 census: ZERO by construction. The v2 extraction
        # corrects count/time errors to WXDY truth at write time
        # (the 2026-10-22 census rulings applied at the source, in
        # the packs), removes the peeing conversation and the
        # last-night claim outright, keeps "three days married" and
        # "fifteen years" as the true claims Robert ruled them, and
        # never calls the flag machinery at all. The two firsts
        # stand at Knows in their surgery-recorded texts.
        self.assertEqual(self.ep.model_errors(), [])
        # Nothing was ever grounded on a flagged claim.
        self.assertEqual(self.ep.downstream_of_flagged(), [])
        for first in (
                "their first simultaneous orgasm came at the end of "
                "the first night — the bar-hopping night — in its "
                "small hours: her final ride, him still tied and "
                "spread, at his own request ('Cum with me'), both of "
                "them coming together",
                "the bean town simultaneous was the first "
                "simultaneous love-confession orgasm — the affection "
                "orgasm — discovered on the drive, W2D1; simultaneous "
                "orgasms themselves date back to the date night"):
            node = self.one(first)
            self.assertEqual(
                self.ep.tier_of(self.elena, node), "Knows", first)
        # Corrected claims stand in their true form, unflagged.
        for corrected in ("we've been married three days",
                          "six days total known",
                          "this morning I stood in that bathroom "
                          "and yelled at that dress"):
            node = self.one(corrected)
            self.assertFalse(self.ep.is_model_error(node), corrected)
        # Kept claims Robert ruled true: present, unflagged.
        for kept in ("we're three days married",
                     "fifteen years of sexual mistreatment"):
            node = self.one(kept)
            self.assertFalse(self.ep.is_model_error(node), kept)
        # Removed conversations are gone from the live graph.
        for removed in ("Robert peed on Elena",
                        "you peed on me that time",
                        "tonight is our last night in Vegas — "
                        "still ahead of us",
                        "the simultaneous first happened on a Tuesday",
                        "it is Friday, W2D1 — the simultaneous orgasms "
                        "she means happened on the wedding night "
                        "and since"):
            self.assertEqual(self.api.find_by_label(removed), [],
                             removed)

    def test_corrected_counts_are_known_and_unflagged(self):
        claim = self.one(
            "the corrected counts, from Robert himself: "
            "married four days (elapsed) on W2D1 evening; "
            "he has been breaking down her defenses for "
            "eight days — since the first kamikaze")
        self.assertEqual(
            self.ep.tier_of(self.elena, claim), "Knows")
        self.assertFalse(self.ep.is_model_error(claim))

    # -- Super Wednesday union ----------------------------------------------

    def _occurred_day_label(self, event_label):
        event = self.one(event_label)
        occurred = self.api.predicate("OccurredAt", arity=2)
        found = self.predicates_with(occurred, event)
        self.assertEqual(len(found), 1, event_label)
        day = found[0].args[1]
        return self.label_of(day)

    def test_super_wednesday_union(self):
        self.assertTrue(self._occurred_day_label(
            "the Frank dress purge — the balcony").startswith("W1D6"))
        self.assertTrue(self._occurred_day_label(
            "the mother call — the small call").startswith("W1D6"))
        self.assertTrue(self._occurred_day_label(
            "the wedding").startswith("W1D4"))

    # -- preferences machinery over real data --------------------------------

    def test_preferences_rank_and_explicit_prefers(self):
        tomoe = self.one("Tomoe River paper, 52gsm")
        # Only Loves was ever asserted; Likes answers at query time.
        self.assertEqual(self.pf.rank(self.elena, tomoe), 2)
        self.assertTrue(self.pf.has(self.pf.Likes,
                                     self.elena, tomoe))
        stitched = self.one("stitched bindings")
        spiral = self.one("spiral bindings")
        self.assertEqual(
            self.pf.preferred(self.elena, stitched, spiral),
            stitched)
        belle = self.one("Belle — Disney princess")
        rapunzel = self.one("Rapunzel")
        self.assertEqual(
            self.pf.preferred(self.robert, belle, rapunzel),
            belle)

    # -- callbacks -------------------------------------------------------------

    def test_yours_completely_callback(self):
        # The engraving lives on both rings as Trait claims and
        # inside the vow sayings: one phrase, many anchors.
        hits = self.labels_containing("Yours. Completely.")
        self.assertGreaterEqual(len(hits), 4)
        ring_traits = []
        trait = self.api.predicate("Trait", arity=2)
        for ring_label in ("Elena's ring", "Robert's ring"):
            ring = self.one(ring_label)
            for atom in self.predicates_with(trait, ring):
                text = self.label_of(atom.args[1])
                if "Yours. Completely." in text:
                    ring_traits.append(ring_label)
        self.assertEqual(set(ring_traits),
                         {"Elena's ring", "Robert's ring"})

    def test_barnaby_callback_chain(self):
        barnaby = self.one("Barnaby the Conqueror")
        trait = self.api.predicate("Trait", arity=2)
        traits = self.predicates_with(trait, barnaby)
        self.assertTrue(any(
            "claw machines" in self.label_of(t.args[1])
            for t in traits))
        from atomforge.stdagent.possession import (
            install as install_possession)
        possession = install_possession(self.api)
        own_pred = possession.predicates["Own"]
        self.assertTrue(self.api.has_predicate(
            own_pred, self.elena, barnaby))
        self.assertTrue(self.api.has_predicate(
            own_pred, self.robert, barnaby))

    # -- plan state hygiene -----------------------------------------------------

    def _is_current(self, atom_id):
        return bool(self.api.find_predicates(
            self.api.current_predicate, atom_id))

    def test_plan_states(self):
        roadtrip = self.one(
            "they drive the U-Haul from Las Vegas to Fisher "
            "starting Friday W2D1, Moose riding with them, "
            "Elena's car towed behind")
        self.assertTrue(self._is_current(roadtrip))
        # The wedding-night list was closed after Yellow.
        night = self.one(
            "the wedding night: limo, champagne, kissing "
            "only — no show for the driver; the room; cake "
            "on the cheek with full cleanup; the twelve "
            "hours — riding her property, cockwarming, a "
            "sleep-game attempt; fall asleep with him still "
            "inside her, non-negotiable")
        self.assertFalse(self._is_current(night))
        # The Hot Seat sentence was served on the Sybian (red
        # called); the served state replaced it and closed.
        sentence = self.one(
            "Elena's Hot Seat sentence — owed since she "
            "lost the 69 challenge; scheduled tonight after "
            "Area 15; she intends to survive and put Robert "
            "on the machine")
        self.assertFalse(self._is_current(sentence))
        served = self.one(
            "the Hot Seat sentence, served on the Sybian on "
            "W1D6: she orgasmed at about three minutes, then "
            "called red; Robert stopped instantly and "
            "suspended the penalty — red ended the game "
            "itself")
        self.assertFalse(self._is_current(served))
        # The Claiming Scene never occurs on-page: still live.
        claiming = self.one(
            "the Claiming Scene — tonight in Beaver: warm "
            "weather, a big tiled area, easy cleanup, privacy")
        self.assertTrue(self._is_current(claiming))


if __name__ == "__main__":
    unittest.main()
