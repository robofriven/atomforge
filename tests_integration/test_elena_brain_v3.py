"""Integration tests for Elena Brain v3 — the grammar migration.

These load the migrated artifact (elena-brain-v3.json, produced by
the goal workspace's build3/migrate.py from elena-brain-v2.json) and
check both that everything v2 guaranteed still holds (scenes, verses,
consent, convictions, clock integrity, plan state) and that the new
grammar is what the graph now speaks: vocabulary-term Does targets,
Gives frames with payloads, Object-kind nodes, the body-object state
predicates, response atoms, and the W1D2 retcon scenes.

Run from the repo root:
    python3 -m unittest discover -s tests_integration
"""

import unittest
from pathlib import Path

from atomforge import AtomSpaceAPI
from atomforge.retrieval import retrieve
from atomforge.stdagent.actions import install as install_actions
from atomforge.stdagent.acts import install as install_acts
from atomforge.stdagent.epistemic import install as install_epistemic
from atomforge.stdagent.feels import install as install_feels
from atomforge.stdagent.possession import install as install_possession
from atomforge.stdagent.preferences import install as install_prefs
from atomforge.stdagent.relational import install as install_relational
from atomforge.stdagent.speech import install as install_speech
from atomforge.domain.consent import install as install_consent

BRAIN_PATH = (
    Path.home() / "workspace" / "goals"
    / "sillytavern-rp-memory-graph" / "hidden_files"
    / "elena-brain" / "elena-brain-v3.json"
)

# The two Does targets the migration was forbidden to touch: both are
# consent-referenced act atoms (draft vocabulary section 4).
EXEMPT_DOES_LABELS = {"rimming (on Elena)", "sleep-use"}

FEELING_TERMS = {
    "afraid", "safe", "safe and protected", "safe being his",
    "safe and confident", "overwhelmed", "overstimulated",
    "intimidated", "ashamed", "guilty", "annoyed", "proud", "sure",
    "ready", "hopeful", "peaceful", "trusted", "cared for",
    "worshipped", "hurt", "seen", "lost", "relieved", "undecided",
}


class ElenaBrainV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = AtomSpaceAPI.load(BRAIN_PATH)
        cls.ep = install_epistemic(cls.api)
        cls.pf = install_prefs(cls.api)
        cls.co = install_consent(cls.api)
        cls.acts = install_acts(cls.api)
        cls.actions = install_actions(cls.api)
        cls.feels = install_feels(cls.api)
        cls.rel = install_relational(cls.api)
        cls.speech = install_speech(cls.api)
        cls.possession = install_possession(cls.api)
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
        # v2's 148 events plus the two retcon events.
        self.assertGreaterEqual(len(events), 150)

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

    # -- acts -------------------------------------------------------------

    def does_atoms(self, act_label):
        act = self.acts.act_node(act_label)
        found = []
        for actor in (self.elena, self.robert):
            found += self.api.find_predicates(
                self.acts.predicates["Does"], actor, act)
        return found

    def predicates_with(self, predicate_id, first_arg):
        return [r.atom for r in self.api.search(
            predicate=predicate_id) if r.atom.args[0] == first_arg]

    def test_rimming_occurrences_across_lines(self):
        # The exempt atom: untouched by the migration, occurrences
        # still counted through its Does atoms' groundings.
        atoms = self.does_atoms("rimming (on Elena)")
        self.assertEqual(len(atoms), 2)  # one per actor
        summaries = set()
        for result in atoms:
            for ground in self.predicates_with(
                    self.ep.EvidenceFor, result.atom.id):
                summaries.add(ground.args[1])
        self.assertGreaterEqual(len(summaries), 2)

    def test_does_targets_are_vocabulary_terms(self):
        # The v3 grammar: outside the two consent-exempt atoms, every
        # Does target in the graph is an approved vocabulary term.
        terms = set(self.acts.vocabulary_terms())
        for result in self.api.search(predicate=self.acts.Does):
            target = result.atom.args[1]
            label = self.label_of(target)
            self.assertTrue(self.acts.is_act(target), label)
            self.assertIn(label, terms | EXEMPT_DOES_LABELS, label)

    def test_no_phrase_act_nodes_survive(self):
        # Scoped to Act-kind nodes: an EVENT may share the label (the
        # Tour event is named for its scene) — the act node must not.
        for phrase in (
                "fellatio to completion — she swallows",
                "the Tour, main pass — thirteen waves",
                "bondage — spreader bar and foot restraint",
                "the plastic wrap — the cocoon soft launch, hips only"):
            survivors = [i for i in self.api.find_by_label(phrase)
                         if self.acts.is_act(i)]
            self.assertEqual(survivors, [], phrase)

    def test_safeword_calls_are_term_atoms(self):
        # All three calls are Elena's: one Does application whose
        # occurrences enumerate through its EvidenceFor groundings.
        atoms = self.does_atoms("safeword call")
        self.assertGreaterEqual(len(atoms), 1)
        grounds = set()
        for result in atoms:
            for ground in self.predicates_with(
                    self.ep.EvidenceFor, result.atom.id):
                grounds.add(ground.args[1])
        # red on the Sybian + two yellow calls, in distinct scenes.
        self.assertGreaterEqual(len(grounds), 3)

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

    # -- feelings -----------------------------------------------------------

    def test_feels_targets_are_terms_and_because_repointed(self):
        for result in self.api.search(predicate=self.feels.Feels):
            label = self.label_of(result.atom.args[1])
            self.assertIn(label, FEELING_TERMS, label)
        for result in self.api.search(predicate=self.feels.Because):
            subject = result.atom.args[0]
            self.assertIn(self.label_of(subject), FEELING_TERMS)

    def test_wrapped_feeling_was_rebased_not_dropped(self):
        # Wrapper identity: Robert's terror when he booked her stood
        # as Feels(Robert, phrase) wrapped in Says(Robert, .) under
        # Believes(Elena, .). The migration re-terms the feeling; the
        # wrapper chain must follow onto the new application atom.
        afraid = self.feels.feeling_node("afraid")
        apps = [r.atom for r in self.api.search(
            predicate=self.feels.Feels)
            if r.atom.args == (self.robert, afraid)]
        self.assertTrue(apps)
        says = self.speech.Says
        wrapped = [app for app in apps
                   if self.api.find_predicates(says, self.robert, app.id)]
        self.assertTrue(wrapped,
                        "no Says(Robert, Feels(Robert, afraid)) wrapper")

    # -- Gives frames, objects, states, responses --------------------------

    def test_every_gives_frame_carries_one_payload(self):
        # Frames dedup per (giver, recipient, payload) by design —
        # 19 distinct frames carry the 40+ directed occurrences,
        # which enumerate through the frames' groundings.
        frames = (self.actions.givings_from(self.elena)
                  + self.actions.givings_from(self.robert))
        self.assertGreaterEqual(len(frames), 19)
        groundings = 0
        for frame in frames:
            payload = self.actions.payload_of(frame)  # raises unless 1
            self.assertTrue(
                self.acts.is_act(payload)
                or self.actions.is_object(payload),
                self.label_of(payload))
            groundings += len(self.predicates_with(
                self.ep.EvidenceFor, frame))
        self.assertGreaterEqual(groundings, 40)

    def test_ring_transfer_frames_with_custody(self):
        from atomforge.atoms import Transition
        for giver, recipient, ring_label in (
                (self.robert, self.elena, "Elena's ring"),
                (self.elena, self.robert, "Robert's ring")):
            ring = self.one(ring_label)
            frames = [f for f in self.actions.givings_from(giver)
                      if self.api.get(f).args[1] == recipient
                      and self.actions.payload_of(f) == ring]
            self.assertEqual(len(frames), 1, ring_label)
            self.assertTrue(self.api.has_predicate(
                self.possession.Holds, recipient, ring))
            receipts = [r.atom for r in self.api.search()
                        if isinstance(r.atom, Transition)
                        and r.atom.args[0] == frames[0]]
            self.assertTrue(receipts, f"no custody receipt for {ring_label}")

    def test_object_kind_rename_landed(self):
        kind_labels = set()
        for result in self.api.search():
            kind = getattr(result.atom, "kind", None)
            if kind is not None:
                kind_labels.add(self.label_of(kind))
        self.assertNotIn("Thing", kind_labels)
        self.assertIn("Object", kind_labels)
        self.assertTrue(self.actions.is_object(
            self.one("Epic Spell Wars")))
        self.assertTrue(self.actions.is_object(self.one("Elena's ring")))

    def test_body_object_states(self):
        plug = self.one("the emerald plug")
        self.assertTrue(self.rel.has(
            self.rel.InsertedIn, plug, self.elena))
        vibrator = self.actions.object_node("vibrator")
        self.assertTrue(self.rel.has(
            self.rel.AffixedTo, vibrator, self.elena))
        cage = self.actions.object_node("cock cage")
        self.assertTrue(self.api.has_predicate(
            self.actions.Wears, self.robert, cage))

    def test_simultaneous_orgasm_is_two_atoms_and_a_link(self):
        self.assertTrue(self.acts.has_orgasm(self.elena))
        self.assertTrue(self.acts.has_orgasm(self.robert))
        oe = self.predicates_with(self.acts.Orgasms, self.elena)[0]
        orr = self.predicates_with(self.acts.Orgasms, self.robert)[0]
        self.assertTrue(self.rel.has(self.rel.Simultaneous, oe.id, orr.id))

    # -- consent (untouched layer) -----------------------------------------

    def test_sleep_permission_with_anal_excluded(self):
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
        # Consent state is explicit only (Robert, 2026-10-22): an act
        # never granted in the consent layer reports "none". In v3
        # the probe act is the sixty-nine TERM (its v2 phrase label
        # was re-termed away).
        act = self.acts.act_node("sixty-nine")
        self.assertEqual(
            self.co.consent_state(self.elena, act, "W2D1"), "none")

    # -- verses --------------------------------------------------------------

    def test_verses_cover_the_scenes(self):
        from atomforge.atoms import Ligature
        verse_links = [
            r.atom for r in self.api.search()
            if isinstance(r.atom, Ligature) and r.atom.name == "Verse"]
        # 147 scenes now (145 + the two retcon scenes).
        self.assertGreaterEqual(len(verse_links), 147 * 3)
        summaries_with_verses = {link.args[0] for link in verse_links}
        self.assertGreaterEqual(len(summaries_with_verses), 147)

    # -- retcon ----------------------------------------------------------------

    def test_retcon_scenes_at_w1d2(self):
        occurred = self.api.predicate("OccurredAt", arity=2)
        for event_label, needle in (
                ("the Saturday talk — giving 'us' a chance",
                 "give 'us' a real chance"),
                ("the Saturday date night — Meepleville, the Raven Inn, "
                 "the Fly LINQ", "Raven Inn")):
            event = self.one(event_label)
            found = self.predicates_with(occurred, event)
            self.assertEqual(len(found), 1, event_label)
            self.assertTrue(
                self.label_of(found[0].args[1]).startswith("W1D2"))
            incontext = self.api.predicate("InContext", arity=2)
            claims = [r.atom for r in self.api.search(
                predicate=incontext) if r.atom.args[1] == event]
            joined = "\n".join(self.label_of(a.args[0]) for a in claims)
            self.assertIn(needle, joined)

    def test_retcon_register_kept_out(self):
        # No Circus Circus bear anywhere in the live graph; the fork's
        # not-quitting talk never entered the talk scene.
        self.assertEqual(self.labels_containing("Circus Circus"), [])
        self.assertEqual(self.labels_containing("Sir Fluffington"), [])

    # -- convictions ------------------------------------------------------------

    def test_interpretation_held_as_conviction(self):
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

    def test_all_six_convictions_at_their_certainties(self):
        certainties = []
        for result in self.api.search(predicate=self.ep.Conviction):
            holder, claim = result.atom.args
            certainties.append(self.ep.certainty_of(holder, claim))
        self.assertEqual(sorted(certainties), [75, 80, 80, 85, 85, 85])

    # -- clock integrity (carried from v2) ---------------------------------------

    def test_model_error_census(self):
        self.assertEqual(self.ep.model_errors(), [])
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
        for corrected in ("we've been married three days",
                          "six days total known",
                          "this morning I stood in that bathroom "
                          "and yelled at that dress"):
            node = self.one(corrected)
            self.assertFalse(self.ep.is_model_error(node), corrected)
        for kept in ("we're three days married",
                     "fifteen years of sexual mistreatment"):
            node = self.one(kept)
            self.assertFalse(self.ep.is_model_error(node), kept)
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

    # -- Super Wednesday union -----------------------------------------------------

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

    # -- preferences -----------------------------------------------------------------

    def test_preferences_rank_and_explicit_prefers(self):
        tomoe = self.one("Tomoe River paper, 52gsm")
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

    # -- callbacks ---------------------------------------------------------------------

    def test_yours_completely_callback(self):
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
        own_pred = self.possession.predicates["Own"]
        self.assertTrue(self.api.has_predicate(
            own_pred, self.elena, barnaby))
        self.assertTrue(self.api.has_predicate(
            own_pred, self.robert, barnaby))

    # -- plan state hygiene --------------------------------------------------------------

    def _is_current(self, atom_id):
        return bool(self.api.find_predicates(
            self.api.current_predicate, atom_id))

    def test_current_count_unchanged(self):
        currents = [r for r in self.api.search(
            predicate=self.api.current_predicate)]
        self.assertEqual(len(currents), 17)

    def test_plan_states(self):
        roadtrip = self.one(
            "they drive the U-Haul from Las Vegas to Fisher "
            "starting Friday W2D1, Moose riding with them, "
            "Elena's car towed behind")
        self.assertTrue(self._is_current(roadtrip))
        night = self.one(
            "the wedding night: limo, champagne, kissing "
            "only — no show for the driver; the room; cake "
            "on the cheek with full cleanup; the twelve "
            "hours — riding her property, cockwarming, a "
            "sleep-game attempt; fall asleep with him still "
            "inside her, non-negotiable")
        self.assertFalse(self._is_current(night))
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
        claiming = self.one(
            "the Claiming Scene — tonight in Beaver: warm "
            "weather, a big tiled area, easy cleanup, privacy")
        self.assertTrue(self._is_current(claiming))


if __name__ == "__main__":
    unittest.main()
