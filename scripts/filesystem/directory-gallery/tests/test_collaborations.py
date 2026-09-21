from __future__ import annotations

import unittest
from pathlib import Path

from directory_gallery.collaborations import collaboration_members


class CollaborationNameTests(unittest.TestCase):
    def test_literal_separator_and_existing_member(self):
        creators = {"A": Path("/library/A"), "B": Path("/library/B")}

        self.assertEqual(
            collaboration_members("A & B & Missing", creators),
            (
                ("A", Path("/library/A")),
                ("B", Path("/library/B")),
                ("Missing", None),
            ),
        )
        self.assertEqual(
            collaboration_members("A & Missing", creators),
            (("A", Path("/library/A")), ("Missing", None)),
        )

    def test_no_guessing_or_duplicate_members(self):
        creators = {"A": Path("/library/A")}

        for name in ("A&B", "A and B", "A & ", "A & A", "X & Y", "a & B"):
            with self.subTest(name=name):
                self.assertEqual(collaboration_members(name, creators), ())


if __name__ == "__main__":
    unittest.main()
