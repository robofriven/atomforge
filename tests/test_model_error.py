"""Unit tests for the epistemic ModelError flag (elena-brain-v1 branch)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atomforge import AtomSpaceAPI
from atomforge.infrastructure import UnknownAtomError
from atomforge.stdagent.epistemic import install as install_epistemic
from atomforge.stdagent.speech import install as install_speech


class TestModelError(unittest.TestCase):
    def setUp(self):
        self.api = AtomSpaceAPI.create()
        self.speech = install_speech(self.api)
        self.ep = install_epistemic(self.api)
        person = self.api.kind("Person")
        self.elena = self.api.create_node("Elena", kind=person)
        self.claim = self.speech.claim_node("we have been married for six days")

    def test_flag_and_query(self):
        self.assertFalse(self.ep.is_model_error(self.claim))
        flag = self.ep.flag_model_error(self.claim)
        self.assertTrue(self.ep.is_model_error(self.claim))
        self.assertEqual(self.ep.model_errors(), [self.claim])
        atom = self.api.get(flag)
        self.assertEqual(atom.args, (self.claim,))

    def test_flag_is_unary(self):
        flag = self.ep.flag_model_error(self.claim)
        self.assertEqual(self.api.get(flag).arity, 1)

    def test_flag_unknown_atom_ftfo(self):
        with self.assertRaises(UnknownAtomError):
            self.ep.flag_model_error(999999)

    def test_flag_dedups(self):
        first = self.ep.flag_model_error(self.claim)
        second = self.ep.flag_model_error(self.claim)
        self.assertEqual(first, second)
        self.assertEqual(len(self.ep.model_errors()), 1)

    def test_downstream_taint(self):
        other = self.speech.claim_node("the road trip starts Friday")
        dependent = self.speech.claim_node("we leave on our six-day anniversary")
        self.ep.evidence_for(dependent, other)
        self.assertEqual(self.ep.downstream_of_flagged(), [])
        self.ep.flag_model_error(other)
        self.assertEqual(self.ep.downstream_of_flagged(), [dependent])
        # Flagging the dependent itself removes it from the report.
        self.ep.flag_model_error(dependent)
        self.assertEqual(self.ep.downstream_of_flagged(), [])

    def test_flag_is_orthogonal_to_tier(self):
        self.ep.relate(self.ep.Believes, self.elena, self.claim,
                       via="learned", teacher=self.elena)
        self.ep.flag_model_error(self.claim)
        self.assertEqual(self.ep.tier_of(self.elena, self.claim), "Believes")
        self.assertTrue(self.ep.is_model_error(self.claim))


if __name__ == "__main__":
    unittest.main()
