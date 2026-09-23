"""Application compatibility: the final case requires a proposed timeline."""
from __future__ import annotations

import unittest

from src.models import Application


class ApplicationModelTests(unittest.TestCase):
    def test_older_application_can_omit_timeline(self):
        proposal = Application("task", "Team", "Idea", "Plan")
        self.assertEqual(proposal.timeline, "")
        self.assertEqual(proposal.to_dict()["timeline"], "")

    def test_old_positional_prototype_and_team_id_are_preserved(self):
        proposal = Application("task", "Team", "Idea", "Plan", "https://example.com/demo", "team")
        self.assertEqual(proposal.prototype_url, "https://example.com/demo")
        self.assertEqual(proposal.team_id, "team")
        self.assertEqual(proposal.timeline, "")

    def test_timeline_survives_dictionary_roundtrip(self):
        proposal = Application("task", "Team", "Idea", "Plan", timeline="4 недели после согласования")
        self.assertEqual(Application(**proposal.to_dict()), proposal)


if __name__ == "__main__":
    unittest.main()
