from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from directory_gallery.scanner import scan_catalog


class ScannerTests(unittest.TestCase):
    def test_discovers_roles_and_prefers_jpg(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            creator = root / "Creator"
            project = creator / "Project"
            project.mkdir(parents=True)
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

    def test_nested_cover_fallback_is_breadth_first_and_all_covers_are_reserved(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "Creator" / "Project"
            (project / "A" / "Deep").mkdir(parents=True)
            (project / "B").mkdir()
            (project / "A" / "cover.png").touch()
            (project / "A" / "Deep" / "cover.jpg").touch()
            (project / "B" / "cover.jpg").touch()
            (project / "A" / "photo.jpg").touch()

            catalog = scan_catalog(root, [])
            discovered = catalog.creators[0].projects[0]

            self.assertEqual(discovered.cover, project / "A" / "cover.png")
            self.assertEqual(
                [item.name for group in discovered.media for item in group.items],
                ["photo.jpg"],
            )
            self.assertEqual(
                [warning.code for warning in catalog.warnings],
                ["multiple-covers", "missing-portrait"],
            )

    def test_direct_cover_prevents_recursive_cover_search(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "Creator" / "Project"
            nested = project / "Extras"
            nested.mkdir(parents=True)
            (project / "cover.png").touch()
            (nested / "cover.jpg").touch()

            catalog = scan_catalog(root, [])
            discovered = catalog.creators[0].projects[0]

            self.assertEqual(discovered.cover, project / "cover.png")
            self.assertEqual(
                [item.path for group in discovered.media for item in group.items],
                [nested / "cover.jpg"],
            )
            self.assertNotIn(
                "multiple-covers", [warning.code for warning in catalog.warnings]
            )

    def test_meta_is_creator_content_and_media_groups_are_type_first(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            creator = root / "Creator"
            (creator / "Album").mkdir(parents=True)
            (creator / "root.JPG").touch()
            (creator / "song.M4A").touch()
            (creator / "notes.txt").touch()
            meta = creator / "meta"
            (meta / "Press").mkdir(parents=True)
            (meta / "portrait-two.jpg").touch()
            (meta / "Press" / "photo.png").touch()
            (meta / "clip.mp4").touch()
            (meta / "clip.poster.jpg").touch()
            (meta / "data.json").touch()

            catalog = scan_catalog(root, [])
            discovered = catalog.creators[0]

            self.assertEqual([project.name for project in discovered.projects], ["Album"])
            self.assertEqual(
                [(group.kind, group.directory) for group in discovered.media],
                [
                    ("image", None),
                    ("image", Path("Press")),
                    ("video", None),
                    ("audio", None),
                ],
            )
            root_images = discovered.media[0]
            self.assertEqual(
                [item.name for item in root_images.items],
                ["portrait-two.jpg", "root.JPG"],
            )
            video = discovered.media[2].items[0]
            self.assertEqual(video.poster, meta / "clip.poster.jpg")
            all_names = {item.name for group in discovered.media for item in group.items}
            self.assertNotIn("clip.poster.jpg", all_names)
            self.assertNotIn("notes.txt", all_names)
            self.assertNotIn("data.json", all_names)

    def test_creators_remain_when_all_projects_are_excluded(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for creator, project in [
                ("Creator A", "Keep"),
                ("Creator B", "Draft"),
                ("Empty Creator", None),
            ]:
                if project:
                    (root / creator / project).mkdir(parents=True)
                else:
                    (root / creator).mkdir()

            catalog = scan_catalog(root, ["Creator B/*"])

            self.assertEqual(
                [item.name for item in catalog.creators],
                ["Creator A", "Creator B", "Empty Creator"],
            )
            self.assertEqual(catalog.creators[1].projects, ())
            self.assertEqual(catalog.creators[2].projects, ())

    def test_exclusions_apply_to_every_scanned_entry_and_artwork_role(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "_Archive" / "Book").mkdir(parents=True)
            creator = root / "Creator"
            project = creator / "Book"
            (creator / "_Draft").mkdir(parents=True)
            (project / "_Scans").mkdir(parents=True)
            scans = project / "Scans"
            scans.mkdir()
            for file in [
                creator / "portrait.jpg",
                creator / "README.md",
                creator / "song.mp3",
                creator / "_song.mp3",
                project / "README.md",
                project / "cover.jpg",
                project / "_photo.jpg",
                scans / "cover.png",
                scans / "photo.jpg",
                scans / "_photo.jpg",
                project / "_Scans" / "hidden.jpg",
            ]:
                file.touch()

            catalog = scan_catalog(
                root,
                [
                    "_*",
                    "!_Scans/hidden.jpg",
                    "portrait.jpg",
                    "/Creator/Book/cover.jpg",
                    "README.md",
                ],
            )

            self.assertEqual([item.name for item in catalog.creators], ["Creator"])
            discovered = catalog.creators[0]
            self.assertIsNone(discovered.portrait)
            self.assertIsNone(discovered.readme)
            self.assertEqual([item.name for item in discovered.projects], ["Book"])
            self.assertEqual(
                [item.name for group in discovered.media for item in group.items],
                ["song.mp3"],
            )
            book = discovered.projects[0]
            self.assertEqual(book.cover, scans / "cover.png")
            self.assertIsNone(book.readme)
            self.assertEqual(
                [item.name for group in book.media for item in group.items],
                ["photo.jpg"],
            )

    def test_excluded_video_poster_is_not_selected_or_listed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "Creator" / "Book"
            project.mkdir(parents=True)
            (project / "clip.mp4").touch()
            (project / "clip.poster.jpg").touch()

            catalog = scan_catalog(root, ["*.poster.jpg"])

            media = catalog.creators[0].projects[0].media
            self.assertEqual([group.kind for group in media], ["video"])
            self.assertIsNone(media[0].items[0].poster)

    def test_reserved_meta_directory_can_be_excluded(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            meta = root / "Creator" / "meta"
            meta.mkdir(parents=True)
            (meta / "photo.jpg").touch()

            catalog = scan_catalog(root, ["meta/"])

            self.assertEqual(catalog.creators[0].projects, ())
            self.assertEqual(catalog.creators[0].media, ())

    def test_hidden_and_symbolic_link_directories_and_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".Hidden" / "Project").mkdir(parents=True)
            project = root / "Visible" / "Real project"
            (project / ".Hidden").mkdir(parents=True)
            (project / ".hidden.jpg").touch()
            (project / ".Hidden" / "photo.jpg").touch()
            project.mkdir(parents=True, exist_ok=True)

            linked_project = root / "Visible" / "Linked project"
            linked_image = project / "linked.jpg"
            try:
                os.symlink(project, linked_project, target_is_directory=True)
                os.symlink(project / ".hidden.jpg", linked_image)
            except (OSError, NotImplementedError):
                linked_project = None

            catalog = scan_catalog(root, [])

            self.assertEqual([creator.name for creator in catalog.creators], ["Visible"])
            self.assertEqual(
                [item.name for item in catalog.creators[0].projects], ["Real project"]
            )
            self.assertEqual(catalog.creators[0].projects[0].media, ())
            if linked_project is not None:
                self.assertNotIn(
                    "Linked project",
                    [project.name for project in catalog.creators[0].projects],
                )
