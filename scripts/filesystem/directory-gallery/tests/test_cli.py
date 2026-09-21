from __future__ import annotations

import unittest

from directory_gallery.cli import build_parser


class CliTests(unittest.TestCase):
    def test_overview_defaults_to_separate(self):
        arguments = build_parser().parse_args(["input", "output"])

        self.assertEqual(arguments.overview, "separate")

    def test_grouped_overview_can_be_selected(self):
        arguments = build_parser().parse_args(
            ["input", "output", "--overview", "grouped"]
        )

        self.assertEqual(arguments.overview, "grouped")

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
