"""Each unimplemented integration gate is visible, never silently counted as passed."""
import json
import unittest
from pathlib import Path

CATALOG = json.loads((Path(__file__).parent/"acceptance-catalog.json").read_text())


class PendingIntegrationTests(unittest.TestCase):
    pass


def pending(gate):
    def test(self):
        self.skipTest(f"Phase {gate['required_phase']} {gate['id']}: {gate['assertion']} — {gate['reason']}")
    return test


for gate in CATALOG["gates"]:
    setattr(PendingIntegrationTests,"test_"+gate["id"].replace("-","_"),pending(gate))
