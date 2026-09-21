from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr

from directory_gallery.cli import build_parser
from directory_gallery.labels import DOMAIN_PRESETS


class CliTests(unittest.TestCase):
    def test_creator_grid_is_enabled_by_default(self):
        arguments = build_parser().parse_args(["input", "output"])

        self.assertTrue(arguments.creator_grid)

    def test_creator_grid_can_be_disabled(self):
        arguments = build_parser().parse_args(
            ["input", "output", "--no-creator-grid"]
        )

        self.assertFalse(arguments.creator_grid)

    def test_domain_presets(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args(["input", "output"]).domain, "generic")
        self.assertEqual(tuple(DOMAIN_PRESETS), ("generic", "book", "film", "music", "model"))
        expected = {
            "generic": ("creator", "creators", "project", "projects"),
            "book": ("author", "authors", "book", "books"),
            "film": ("director", "directors", "movie", "movies"),
            "music": ("artist", "artists", "album", "albums"),
            "model": ("model", "models", "scene", "scenes"),
        }
        for domain, forms in expected.items():
            with self.subTest(domain=domain):
                self.assertEqual(
                    parser.parse_args(["input", "output", "--domain", domain]).domain,
                    domain,
                )
                labels = DOMAIN_PRESETS[domain]
                self.assertEqual(
                    (labels.creator.singular, labels.creator.plural,
                     labels.project.singular, labels.project.plural),
                    forms,
                )

        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["input", "output", "--domain", "unknown"])

    def test_collaboration_links_are_opt_in(self):
        parser = build_parser()

        self.assertFalse(parser.parse_args(["input", "output"]).link_collaborations)
        self.assertTrue(
            parser.parse_args(["input", "output", "--link-collaborations"])
            .link_collaborations
        )

    def test_exclusion_patterns_and_files_keep_command_line_order(self):
        arguments = build_parser().parse_args(
            [
                "input",
                "output",
                "--exclude",
                "_*",
                "--exclude-from",
                ".galleryignore",
                "--exclude",
                "!_keep.jpg",
            ]
        )

        self.assertEqual(
            arguments.exclusion_sources,
            [
                ("pattern", "_*"),
                ("file", ".galleryignore"),
                ("pattern", "!_keep.jpg"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
