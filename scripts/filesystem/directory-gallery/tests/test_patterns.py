from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from directory_gallery.errors import UserError
from directory_gallery.patterns import ExclusionRules, load_exclusion_patterns


class ExclusionTests(unittest.TestCase):
    def test_underscore_pattern_matches_files_and_directories_at_any_depth(self):
        root = Path("/catalog")
        rules = ExclusionRules(root, ["_*"])

        for name, directory in [
            ("_Archive", True),
            ("Creator/_Drafts", True),
            ("Creator/Book/Scans/_page.jpg", False),
        ]:
            with self.subTest(name=name):
                self.assertTrue(rules.excludes(root / name, directory=directory))
        self.assertFalse(
            rules.excludes(root / "Creator/Book/page.jpg", directory=False)
        )

    def test_directory_anchoring_recursive_globs_and_case_sensitivity(self):
        root = Path("/catalog")
        rules = ExclusionRules(root, ["Drafts/", "/Astra/Archive/", "**/Extras/"])

        self.assertTrue(rules.excludes(root / "Astra/Drafts", directory=True))
        self.assertFalse(rules.excludes(root / "Astra/Drafts", directory=False))
        self.assertTrue(rules.excludes(root / "Astra/Archive", directory=True))
        self.assertFalse(rules.excludes(root / "Other/Astra/Archive", directory=True))
        self.assertTrue(rules.excludes(root / "Astra/Book/Extras", directory=True))
        self.assertFalse(rules.excludes(root / "Astra/drafts", directory=True))

    def test_negation_is_ordered_but_cannot_reinclude_excluded_parent(self):
        root = Path("/catalog")
        rules = ExclusionRules(
            root, ["*.jpg", "!keep.jpg", "Private/", "!Private/keep.jpg"]
        )

        self.assertTrue(rules.excludes(root / "A/Book/photo.jpg", directory=False))
        self.assertFalse(rules.excludes(root / "A/Book/keep.jpg", directory=False))
        self.assertTrue(rules.excludes_file_or_parent(root / "A/Private/keep.jpg"))

    def test_pattern_files_are_expanded_in_command_line_order(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            file = Path(temporary_directory) / ".galleryignore"
            file.write_text("\ufeff# Gallery rules\n*.jpg\n\n", encoding="utf-8")
            patterns = load_exclusion_patterns(
                [("pattern", "_*/"), ("file", str(file)), ("pattern", "!keep.jpg")]
            )

        self.assertEqual(
            patterns, ["_*/", "# Gallery rules", "*.jpg", "", "!keep.jpg"]
        )
        rules = ExclusionRules(Path("/catalog"), patterns)
        self.assertTrue(rules.excludes(Path("/catalog/A/_Drafts"), directory=True))
        self.assertTrue(rules.excludes(Path("/catalog/A/photo.jpg"), directory=False))
        self.assertFalse(rules.excludes(Path("/catalog/A/keep.jpg"), directory=False))

    def test_missing_file_and_empty_inline_pattern_are_errors(self):
        with self.assertRaises(UserError):
            load_exclusion_patterns([("file", "/does-not-exist/.galleryignore")])
        with self.assertRaises(UserError):
            load_exclusion_patterns([("pattern", "")])
        with self.assertRaises(UserError):
            ExclusionRules(Path("/catalog"), ["invalid\\"])
