from __future__ import annotations

import unittest

from directory_gallery.cli import build_parser


class CliTests(unittest.TestCase):
    def test_creator_grid_is_enabled_by_default(self):
        arguments = build_parser().parse_args(["input", "output"])

        self.assertTrue(arguments.creator_grid)

    def test_creator_grid_can_be_disabled(self):
        arguments = build_parser().parse_args(
            ["input", "output", "--no-creator-grid"]
        )

        self.assertFalse(arguments.creator_grid)

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
