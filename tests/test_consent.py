"""Permanent tests for the consent domain module (ConsentGranted model)."""

import unittest

from atomforge import AtomSpaceAPI
from atomforge.infrastructure import (
    InvalidAtomOperationError, UnknownAtomError,
)
from atomforge.stdagent.acts import install as install_acts
from atomforge.stdagent.logic import install as install_logic
from atomforge.stdagent.speech import install as install_speech
from atomforge.domain.consent import NEVER_EXPIRES, install, wxdy_key

# These tests are about consent, not the act factory: they install the
# acts module with a small fixture vocabulary so their act labels mint
# under the v3 gated factory exactly as they did before it existed.
FIXTURE_VOCABULARY = (
    "hug", "being photographed", "surprise hugs", "plain act",
)


class ConsentTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        # Robert owns this graph: the standing default recipient.
        self.kind = self.api.kind("Person")
        self.robert = self.api.create_node("Robert", kind=self.kind)
        self.elena = self.api.create_node("Elena", kind=self.kind)
        self.acts = install_acts(
            self.api, vocabulary=FIXTURE_VOCABULARY)
        self.consent = install(self.api, owner=self.robert)
        self.speech = install_speech(self.api)
        self.logic = install_logic(self.api)
        self.hug = self.acts.act_node("hug")
        self.photographs = self.acts.act_node("being photographed")

    # -- helpers -----------------------------------------------------------

    def say(self, speaker, text):
        return self.speech.say(speaker, text)

    def grant_hug(self, **overrides):
        kwargs = dict(
            statement=self.say(self.elena, "hugs are always fine"),
            stated_on="W1D1",
            expires=NEVER_EXPIRES,
        )
        kwargs.update(overrides)
        return self.consent.grant(self.elena, self.hug, **kwargs)

    # -- vocabulary ----------------------------------------------------------

    def test_vocabulary_is_exactly_the_three(self):
        self.assertEqual(
            set(self.consent.predicates),
            {"ConsentGranted", "HardLimit", "ConsentRevoked"},
        )

    def test_install_is_idempotent(self):
        self.assertIs(install(self.api), self.consent)

    def test_wxdy_key_orders_and_validates(self):
        self.assertLess(wxdy_key("W1D6"), wxdy_key("W2D1"))
        self.assertLess(wxdy_key("W2D1"), wxdy_key(NEVER_EXPIRES))
        with self.assertRaises(TypeError):
            wxdy_key("next Friday")
        with self.assertRaises(TypeError):
            wxdy_key("2026-10-22")

    # -- grants: the happy path ------------------------------------------------

    def test_grant_state_inside_and_outside_window(self):
        self.grant_hug(expires="W1D3")
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W1D1"),
            "granted")
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W1D3"),
            "granted")
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W1D4"),
            "expired")

    def test_standing_grant_never_expires(self):
        self.grant_hug()
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W52D7"),
            "granted")

    def test_no_record_is_an_honest_blank(self):
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W1D1"),
            "none")

    def test_hangers_round_trip(self):
        saying = self.say(self.elena, "hugs through the weekend")
        grant = self.consent.grant(
            self.elena, self.hug,
            statement=saying, stated_on="W1D5", expires="W1D7",
            note="not when I have a headache",
        )
        hangers = self.consent.hangers_of(grant)
        self.assertEqual(hangers["to"], self.robert)  # owner default
        self.assertEqual(hangers["statement"], saying)
        self.assertEqual(hangers["stated_on"], "W1D5")
        self.assertEqual(hangers["active_from"], "W1D5")
        self.assertEqual(hangers["expires"], "W1D7")
        self.assertEqual(hangers["mode"], "declared")
        self.assertEqual(hangers["note"], "not when I have a headache")
        # The statement is also the grant's evidence.
        self.assertEqual(self.consent.epistemic.evidence_of(grant), [saying])

    def test_explicit_recipient_overrides_owner_default(self):
        stephanie = self.api.create_node("Stephanie", kind=self.kind)
        grant = self.grant_hug(to=stephanie)
        self.assertEqual(self.consent.hangers_of(grant)["to"], stephanie)

    def test_active_from_opens_window_after_statement(self):
        self.grant_hug(stated_on="W1D1", active_from="W1D4",
                       expires="W1D5")
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W1D2"),
            "none")
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W1D4"),
            "granted")

    # -- grants: FTFO validation ----------------------------------------------

    def test_grant_without_recipient_or_owner_is_refused(self):
        api = AtomSpaceAPI.create()
        acts = install_acts(api, vocabulary=FIXTURE_VOCABULARY)
        consent = install(api)  # no owner installed
        speech = install_speech(api)
        elena = api.create_node("Elena", kind=api.kind("Person"))
        hug = acts.act_node("hug")
        with self.assertRaises(TypeError):
            consent.grant(
                elena, hug,
                statement=speech.say(elena, "fine"),
                stated_on="W1D1", expires=NEVER_EXPIRES,
            )
        self.assertEqual(consent.grants_of(elena), [])

    def test_grant_requires_a_decided_window(self):
        with self.assertRaises(TypeError):
            self.consent.grant(
                self.elena, self.hug,
                statement=self.say(self.elena, "fine"),
                stated_on="W1D1",
                # expires omitted entirely: a grant with no decided
                # window cannot be written.
            )
        self.assertEqual(self.consent.grants_of(self.elena), [])

    def test_grant_rejects_malformed_dates(self):
        with self.assertRaises(TypeError):
            self.grant_hug(stated_on="Friday")
        with self.assertRaises(TypeError):
            self.grant_hug(expires="whenever")
        self.assertEqual(self.consent.grants_of(self.elena), [])

    def test_grant_rejects_empty_window(self):
        with self.assertRaises(TypeError):
            self.grant_hug(stated_on="W1D5", expires="W1D3")
        with self.assertRaises(TypeError):
            self.grant_hug(stated_on="W1D5", active_from="W1D4")

    def test_someone_elses_words_cannot_declare_my_consent(self):
        saying = self.say(self.robert, "she said hugs are fine")
        with self.assertRaises(TypeError):
            self.grant_hug(statement=saying)
        self.assertEqual(self.consent.grants_of(self.elena), [])

    def test_self_authorization_is_inexpressible(self):
        # Robert cannot write Elena's consent at all: a grant with
        # Elena as holder refuses Robert's statement as its ground.
        with self.assertRaises(TypeError):
            self.consent.grant(
                self.elena, self.hug,
                statement=self.say(self.robert, "I consent for her"),
                stated_on="W1D1", expires=NEVER_EXPIRES,
            )
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W1D1"),
            "none")

    def test_declared_grant_requires_a_saying(self):
        with self.assertRaises(TypeError):
            self.grant_hug(statement=self.hug)

    def test_grant_rejects_non_act_target(self):
        steak = self.api.create_node("Steak", kind=self.kind)
        with self.assertRaises(TypeError):
            self.consent.grant(
                self.elena, steak,
                statement=self.say(self.elena, "fine"),
                stated_on="W1D1", expires=NEVER_EXPIRES,
            )

    def test_grant_rejects_unknown_holder(self):
        with self.assertRaises(UnknownAtomError):
            self.consent.grant(
                999999, self.hug,
                statement=self.say(self.elena, "fine"),
                stated_on="W1D1", expires=NEVER_EXPIRES,
            )

    def test_exclusion_of_the_act_itself_is_refused(self):
        with self.assertRaises(TypeError):
            self.grant_hug(excludes=(self.hug,))

    # -- exclusions and blanket scope -------------------------------------------

    def test_exclusions_are_data_and_carve_the_grant(self):
        excluded = self.acts.act_node("surprise hugs")
        grant = self.grant_hug(excludes=(excluded,))
        self.assertEqual(self.consent.exclusions_of(grant), [excluded])
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W1D1"),
            "granted")

    def test_blanket_grant_covers_member_acts_via_kind(self):
        # Consent addressed to a kind covers the acts under that kind
        # (through the IsA closure); exclusions carve specific
        # members back out and outrank the blanket.
        sex_kind = self.api.kind("SexAct")
        self.consent.relational.relate(
            self.consent.relational.IsA, sex_kind, self.acts.act_kind)
        member = self.api.create_node("member act", kind=sex_kind)
        carved = self.api.create_node("carved act", kind=sex_kind)
        outsider = self.acts.act_node("plain act")
        self.consent.grant(
            self.elena, sex_kind,
            statement=self.say(self.elena, "blanket, with limits"),
            stated_on="W1D1", expires=NEVER_EXPIRES,
            excludes=(carved,),
        )
        self.assertEqual(
            self.consent.consent_state(self.elena, member, "W1D2"),
            "granted")
        self.assertEqual(
            self.consent.consent_state(self.elena, carved, "W1D2"),
            "none")
        self.assertEqual(
            self.consent.consent_state(self.elena, outsider, "W1D2"),
            "none")

    # -- enacted mode -------------------------------------------------------------

    def test_enacted_grant_is_retrospective_only(self):
        scene = self.api.create_node(
            "the wedding night scene", kind=self.api.kind("Scene"))
        self.consent.grant(
            self.elena, self.hug, mode="enacted",
            statement=scene, stated_on="W1D4", expires="W1D4",
        )
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W1D4"),
            "enacted")
        # The next day it is history, not a license.
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W1D5"),
            "expired")

    # -- hard limits ----------------------------------------------------------------

    def test_hard_limit_state(self):
        self.consent.hard_limit(self.elena, self.photographs)
        self.assertEqual(
            self.consent.consent_state(
                self.elena, self.photographs, "W3D2"),
            "hard_limit")
        self.assertEqual(len(self.consent.hard_limits_of(self.elena)), 1)

    def test_conflict_is_preserved_and_reported(self):
        limit = self.consent.hard_limit(self.elena, self.photographs)
        grant = self.consent.grant(
            self.elena, self.photographs,
            statement=self.say(self.elena, "actually, photos are fine"),
            stated_on="W1D2", expires=NEVER_EXPIRES,
        )
        self.assertTrue(self.consent.has(
            self.consent.HardLimit, self.elena, self.photographs))
        self.assertTrue(self.consent.has(
            self.consent.ConsentGranted, self.elena, self.photographs))
        self.assertEqual(
            self.consent.consent_state(
                self.elena, self.photographs, "W1D3"),
            "conflicted")
        contradictions = self.api.find_predicates(
            self.logic.Contradicts, grant, limit)
        self.assertEqual(len(contradictions), 1)

    # -- revocation -------------------------------------------------------------------

    def test_revoke_transitions_the_grant_and_holds(self):
        grant = self.grant_hug()
        red = self.say(self.elena, "Red.")
        revocation = self.consent.revoke(
            self.elena, self.hug, statement=red, stated_on="W1D3")
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W1D2"),
            "granted")
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W1D3"),
            "revoked")
        # Revoked until stated otherwise: still revoked far later.
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W9D9"),
            "revoked")
        # The chain is walkable: grant record -> revocation record.
        grant_record = self.consent.records_of(grant)[-1]
        revocation_record = self.consent.records_of(revocation)[-1]
        incoming = self.api.in_transitions(revocation_record)
        befores = {self.api.transition_args(t)[0] for t in incoming}
        self.assertIn(grant_record, befores)

    def test_regrant_after_revocation_supersedes(self):
        self.grant_hug()
        self.consent.revoke(
            self.elena, self.hug,
            statement=self.say(self.elena, "Red."), stated_on="W1D3")
        self.grant_hug(
            statement=self.say(self.elena, "hugs are fine again"),
            stated_on="W1D5")
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W1D4"),
            "revoked")
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W1D5"),
            "granted")

    def test_revoke_with_nothing_standing_is_refused(self):
        with self.assertRaises(InvalidAtomOperationError):
            self.consent.revoke(
                self.elena, self.hug,
                statement=self.say(self.elena, "Red."),
                stated_on="W1D1")

    def test_someone_else_cannot_revoke_my_consent(self):
        self.grant_hug()
        with self.assertRaises(TypeError):
            self.consent.revoke(
                self.elena, self.hug,
                statement=self.say(self.robert, "she said stop"),
                stated_on="W1D2")
        self.assertEqual(
            self.consent.consent_state(self.elena, self.hug, "W1D2"),
            "granted")

    def test_revoked_cannot_be_asserted_directly(self):
        with self.assertRaises(TypeError):
            self.consent.relate(
                self.consent.ConsentRevoked, self.elena, self.hug)


class RestatementTests(unittest.TestCase):
    """Renaming restatements: a category coined mid-stream.

    The naming scene mints a restatement record Transition-chained
    to the original record, carrying the new term — "the thing we
    granted back then, we now call this."  Distinct from a
    revoke-restate: the predecessor is a grant record, no revocation
    is written, and the original grant's state is unchanged.
    """

    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.kind = self.api.kind("Person")
        self.robert = self.api.create_node("Robert", kind=self.kind)
        self.elena = self.api.create_node("Elena", kind=self.kind)
        self.acts = install_acts(
            self.api, vocabulary=FIXTURE_VOCABULARY)
        self.consent = install(self.api, owner=self.robert)
        self.speech = install_speech(self.api)
        self.old_act = self.acts.act_node("plain act")
        self.new_act = self.acts.act_node("surprise hugs")

    def say(self, speaker, text):
        return self.speech.say(speaker, text)

    def grant_old(self, **overrides):
        kwargs = dict(
            statement=self.say(self.elena, "plain acts are fine"),
            stated_on="W1D1",
            expires=NEVER_EXPIRES,
        )
        kwargs.update(overrides)
        return self.consent.grant(self.elena, self.old_act, **kwargs)

    def restate(self, **overrides):
        kwargs = dict(
            statement=self.say(
                self.elena, "the thing we granted back then, "
                "we now call surprise hugs"),
            stated_on="W1D4",
        )
        kwargs.update(overrides)
        return self.consent.restate_grant(
            self.elena, self.old_act, self.new_act, **kwargs)

    def restates_targets(self, record):
        found = []
        for ligature_id in self.api.in_ligatures(record):
            ligature = self.api.get(ligature_id)
            if ligature.name == "Restates" \
                    and len(ligature.args) == 2 \
                    and ligature.args[0] == record:
                found.append(ligature.args[1])
        return found

    def test_restatement_chains_to_original_and_carries_new_term(self):
        grant = self.grant_old()
        original_record = self.consent.records_of(grant)[-1]
        restated = self.restate()
        # The new atom is a genuine grant on the new term.
        self.assertEqual(self.api.get(restated).args[1], self.new_act)
        restatement_record = self.consent.records_of(restated)[-1]
        # (1) Transition-chained to the original record.
        incoming = self.api.in_transitions(restatement_record)
        befores = {self.api.transition_args(t)[0] for t in incoming}
        self.assertIn(original_record, befores)
        # (2) Carries the new term, marked restated, pointing back.
        hangers = self.consent.hangers_of(restated)
        self.assertEqual(hangers["mode"], "restated")
        self.assertEqual(hangers["stated_on"], "W1D4")
        self.assertEqual(
            self.restates_targets(restatement_record),
            [original_record])

    def test_consent_state_resolves_through_the_chain(self):
        self.grant_old()
        self.restate()
        # (3) Granted at and after the naming scene.
        self.assertEqual(
            self.consent.consent_state(self.elena, self.new_act, "W1D4"),
            "granted")
        self.assertEqual(
            self.consent.consent_state(self.elena, self.new_act, "W2D1"),
            "granted")
        # (4) None before the naming scene: the name did not exist yet.
        self.assertEqual(
            self.consent.consent_state(self.elena, self.new_act, "W1D3"),
            "none")

    def test_original_grant_state_unchanged(self):
        grant = self.grant_old()
        restated = self.restate()
        # (5) The original term still resolves, its records untouched.
        self.assertEqual(
            self.consent.consent_state(self.elena, self.old_act, "W1D4"),
            "granted")
        self.assertEqual(len(self.consent.records_of(grant)), 1)
        # The window and recipient were inherited, not re-decided.
        restated_hangers = self.consent.hangers_of(restated)
        self.assertEqual(restated_hangers["to"], self.robert)
        self.assertEqual(restated_hangers["expires"], NEVER_EXPIRES)

    def test_restatement_is_not_a_revocation(self):
        self.grant_old()
        restated = self.restate()
        # (6) No revocation atom exists, nothing reads revoked, and
        # the chain predecessor is a grant record, not a revocation.
        self.assertEqual(self.consent.revocations_of(self.elena), [])
        self.assertNotEqual(
            self.consent.consent_state(self.elena, self.old_act, "W1D4"),
            "revoked")
        self.assertNotEqual(
            self.consent.consent_state(self.elena, self.new_act, "W1D4"),
            "revoked")
        restatement_record = self.consent.records_of(restated)[-1]
        befores = {
            self.api.transition_args(t)[0]
            for t in self.api.in_transitions(restatement_record)
        }
        grant_records = set()
        for atom_id in self.consent.grants_of(self.elena):
            grant_records.update(self.consent.records_of(atom_id))
        self.assertTrue(befores & grant_records)
        revocation_records = set()
        for atom_id in self.consent.revocations_of(self.elena):
            revocation_records.update(self.consent.records_of(atom_id))
        self.assertFalse(befores & revocation_records)

    def test_restatement_requires_a_standing_grant(self):
        with self.assertRaises(InvalidAtomOperationError):
            self.restate()
        # Revoked grants cannot be resurrected by renaming.
        self.grant_old()
        self.consent.revoke(
            self.elena, self.old_act,
            statement=self.say(self.elena, "Red."),
            stated_on="W1D2")
        with self.assertRaises(InvalidAtomOperationError):
            self.restate()

    def test_restatement_must_rename_and_be_spoken_by_holder(self):
        self.grant_old()
        with self.assertRaises(TypeError):
            self.consent.restate_grant(
                self.elena, self.old_act, self.old_act,
                statement=self.say(self.elena, "same name"),
                stated_on="W1D4")
        with self.assertRaises(TypeError):
            self.consent.restate_grant(
                self.elena, self.old_act, self.new_act,
                statement=self.say(self.robert, "she renamed it"),
                stated_on="W1D4")


class RevokePropagationTests(unittest.TestCase):
    """Lineage-scoped revoke propagation (ruled 2026-10-25).

    Revoking any name in a restatement lineage revokes all names in
    that lineage — read-time only, no extra records written. But a
    label that later heads a new lineage (a fresh re-grant of the old
    name after the rename) is a different permission: revoking it
    leaves the old lineage untouched.
    """

    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.kind = self.api.kind("Person")
        self.robert = self.api.create_node("Robert", kind=self.kind)
        self.elena = self.api.create_node("Elena", kind=self.kind)
        self.acts = install_acts(
            self.api, vocabulary=FIXTURE_VOCABULARY)
        self.consent = install(self.api, owner=self.robert)
        self.speech = install_speech(self.api)
        self.old_act = self.acts.act_node("plain act")
        self.new_act = self.acts.act_node("surprise hugs")
        self.third_act = self.acts.act_node("hug")

    def say(self, speaker, text):
        return self.speech.say(speaker, text)

    def grant_old(self, **overrides):
        kwargs = dict(
            statement=self.say(self.elena, "plain acts are fine"),
            stated_on="W1D1",
            expires=NEVER_EXPIRES,
        )
        kwargs.update(overrides)
        return self.consent.grant(self.elena, self.old_act, **kwargs)

    def restate(self, **overrides):
        kwargs = dict(
            statement=self.say(
                self.elena, "the thing we granted back then, "
                "we now call surprise hugs"),
            stated_on="W1D4",
        )
        kwargs.update(overrides)
        return self.consent.restate_grant(
            self.elena, self.old_act, self.new_act, **kwargs)

    def revoke(self, act, date, text="Red."):
        return self.consent.revoke(
            self.elena, act,
            statement=self.say(self.elena, text),
            stated_on=date)

    def state(self, act, date):
        return self.consent.consent_state(self.elena, act, date)

    def test_revoke_old_propagates_to_restated_term(self):
        self.grant_old()
        self.restate()
        self.revoke(self.old_act, "W1D5")
        self.assertEqual(self.state(self.new_act, "W1D4"), "granted")
        self.assertEqual(self.state(self.new_act, "W1D6"), "revoked")
        self.assertEqual(self.state(self.old_act, "W1D6"), "revoked")

    def test_revoke_new_propagates_back_to_original(self):
        self.grant_old()
        self.restate()
        self.revoke(self.new_act, "W1D5")
        self.assertEqual(self.state(self.old_act, "W1D6"), "revoked")
        self.assertEqual(self.state(self.new_act, "W1D6"), "revoked")

    def test_label_reuse_revoke_hits_new_lineage_only(self):
        self.grant_old()
        self.restate()
        # A fresh re-grant of the old name heads a NEW lineage.
        self.consent.grant(
            self.elena, self.old_act,
            statement=self.say(self.elena, "plain acts are fine, again"),
            stated_on="W1D6",
            expires=NEVER_EXPIRES)
        self.assertEqual(self.state(self.new_act, "W1D6"), "granted")
        self.revoke(self.old_act, "W1D7")
        self.assertEqual(self.state(self.old_act, "W1D8"), "revoked")
        self.assertEqual(self.state(self.new_act, "W1D8"), "granted")

    def test_transitive_propagation_across_two_restatements(self):
        self.grant_old()
        self.restate()
        self.consent.restate_grant(
            self.elena, self.new_act, self.third_act,
            statement=self.say(
                self.elena, "surprise hugs, we now call hugs"),
            stated_on="W1D5")
        self.assertEqual(self.state(self.third_act, "W1D4"), "none")
        self.assertEqual(self.state(self.third_act, "W1D5"), "granted")
        self.revoke(self.old_act, "W1D6")
        self.assertEqual(self.state(self.third_act, "W1D7"), "revoked")
        self.assertEqual(self.state(self.new_act, "W1D7"), "revoked")
        self.assertEqual(self.state(self.old_act, "W1D7"), "revoked")

    def test_regrant_after_revoke_revives_lineage(self):
        self.grant_old()
        self.restate()
        self.revoke(self.old_act, "W1D5")
        self.assertEqual(self.state(self.old_act, "W1D6"), "revoked")
        self.assertEqual(self.state(self.new_act, "W1D6"), "revoked")
        self.consent.grant(
            self.elena, self.old_act,
            statement=self.say(self.elena, "plain acts are fine, again"),
            stated_on="W1D7",
            expires=NEVER_EXPIRES)
        self.assertEqual(self.state(self.old_act, "W1D8"), "granted")
        self.assertEqual(self.state(self.new_act, "W1D8"), "granted")

    def test_revoke_writes_a_single_record(self):
        self.grant_old()
        self.restate()
        self.revoke(self.old_act, "W1D5")
        # Propagation is read-time: no duplicate revocation records
        # are written across the lineage.
        revocations = self.consent.revocations_of(self.elena)
        self.assertEqual(len(revocations), 1)
        self.assertEqual(
            len(self.consent.records_of(revocations[0])), 1)


if __name__ == "__main__":
    unittest.main()
