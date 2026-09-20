from __future__ import annotations

import unittest

from directory_gallery.errors import UserError
from directory_gallery.patterns import matches_exclusion, validate_exclusions


class ExclusionTests(unittest.TestCase):
    def test_project_and_creator_project_patterns(self):
        patterns = ["meta", "Astra Vey/Drafts", "Nia Solen/*"]
        validate_exclusions(patterns)

        self.assertTrue(matches_exclusion("Anyone", "meta", patterns))
        self.assertTrue(matches_exclusion("Astra Vey", "Drafts", patterns))
        self.assertTrue(matches_exclusion("Nia Solen", "Any Project", patterns))
        self.assertFalse(matches_exclusion("Astra Vey", "Published", patterns))

    def test_matching_is_case_sensitive(self):
        self.assertFalse(matches_exclusion("Creator", "Meta", ["meta"]))

    def test_wildcards_do_not_cross_components(self):
        self.assertTrue(matches_exclusion("Any Creator", "Draft 2", ["*/Draft ?"]))
        self.assertFalse(matches_exclusion("Any Creator", "Draft 20", ["*/Draft ?"]))

    def test_invalid_patterns_are_rejected(self):
        invalid = ["", "Creator\\Project", "Creator/**", "/Project", "A/B/C"]
        for pattern in invalid:
            with self.subTest(pattern=pattern), self.assertRaises(UserError):
                validate_exclusions([pattern])
