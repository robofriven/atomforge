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


class ConsentTests(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        # Robert owns this graph: the standing default recipient.
        self.kind = self.api.kind("Person")
        self.robert = self.api.create_node("Robert", kind=self.kind)
        self.elena = self.api.create_node("Elena", kind=self.kind)
        self.consent = install(self.api, owner=self.robert)
        self.acts = install_acts(self.api)
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
        consent = install(api)  # no owner installed
        acts = install_acts(api)
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


if __name__ == "__main__":
    unittest.main()
