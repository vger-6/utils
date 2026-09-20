from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from directory_gallery.scanner import scan_catalog


class ScannerTests(unittest.TestCase):
    def test_discovers_exactly_two_levels_and_prefers_jpg(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            creator = root / "Creator"
            project = creator / "Project"
            (project / "extras" / "Nested").mkdir(parents=True)
            (creator / "portrait.png").touch()
            (creator / "portrait.jpg").touch()
            (project / "cover.png").touch()
            (project / "cover.jpeg").touch()
            (project / "cover.jpg").touch()

            catalog = scan_catalog(root, [])

            self.assertEqual([item.name for item in catalog.creators], ["Creator"])
            discovered = catalog.creators[0]
            self.assertEqual(discovered.portrait, creator / "portrait.jpg")
            self.assertEqual([item.name for item in discovered.projects], ["Project"])
            self.assertEqual(discovered.projects[0].cover, project / "cover.jpg")
            self.assertEqual(
                [warning.code for warning in catalog.warnings],
                ["multiple-covers", "multiple-portraits"],
            )

    def test_exclusions_are_repeatable_and_empty_creators_are_omitted(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for creator, project in [
                ("Creator A", "meta"),
                ("Creator A", "Keep"),
                ("Creator B", "Draft"),
            ]:
                (root / creator / project).mkdir(parents=True)

            catalog = scan_catalog(root, ["meta", "Creator B/*"])

            self.assertEqual([item.name for item in catalog.creators], ["Creator A"])
            self.assertEqual(catalog.creators[0].projects[0].name, "Keep")

    def test_hidden_and_symbolic_link_directories_are_ignored(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".Hidden" / "Project").mkdir(parents=True)
            (root / "Visible" / ".Hidden project").mkdir(parents=True)
            real_project = root / "Visible" / "Real project"
            real_project.mkdir(parents=True)

            linked_project = root / "Visible" / "Linked project"
            try:
                os.symlink(real_project, linked_project, target_is_directory=True)
            except (OSError, NotImplementedError):
                linked_project = None

            catalog = scan_catalog(root, [])

            self.assertEqual(len(catalog.creators), 1)
            self.assertEqual(
                [project.name for project in catalog.creators[0].projects],
                ["Real project"],
            )
            if linked_project is not None:
                self.assertNotIn(
                    "Linked project",
                    [project.name for project in catalog.creators[0].projects],
                )
