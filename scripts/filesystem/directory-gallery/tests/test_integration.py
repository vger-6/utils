from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from directory_gallery.cli import main
from directory_gallery.output import MANIFEST_NAME


def make_image(path: Path, color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 48), color).save(path)


class IntegrationTests(unittest.TestCase):
    def test_builds_and_updates_a_self_contained_catalog(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            creator = source / "Creator & Co"
            first = creator / "First Project"
            second = creator / "Second Project"
            first.mkdir(parents=True)
            second.mkdir()
            make_image(creator / "portrait.jpg", "#244b75")
            make_image(first / "cover.png", "#8f3d58")
            output = temporary / "site"

            result = main(
                [str(source), str(output), "--title", "Things <&> Projects"]
            )

            self.assertEqual(result, 0)
            index = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("Things &lt;&amp;&gt; Projects", index)
            self.assertIn("Creator &amp; Co", index)
            self.assertIn("First Project", index)
            self.assertIn("Second Project", index)
            self.assertIn("cover-placeholder", index)
            self.assertIn("Creator%20%26%20Co/First%20Project/", index)
            self.assertTrue((output / "assets" / "directory-gallery.css").is_file())
            self.assertTrue((output / "assets" / "directory-gallery.js").is_file())
            self.assertEqual(len(list((output / "thumbnails").glob("*.jpg"))), 2)

            manifest = json.loads((output / MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["thumbnails"]), 2)

            (creator / "portrait.jpg").unlink()
            self.assertEqual(main([str(source), str(output)]), 0)
            self.assertEqual(len(list((output / "thumbnails").glob("*.jpg"))), 1)
            updated = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("portrait-placeholder", updated)

    def test_repeatable_exclusions_are_applied(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            for creator, project in [
                ("Creator A", "Keep"),
                ("Creator A", "meta"),
                ("Creator B", "Draft"),
            ]:
                (source / creator / project).mkdir(parents=True)
            output = temporary / "site"

            result = main(
                [
                    str(source),
                    str(output),
                    "--exclude",
                    "meta",
                    "--exclude",
                    "Creator B/*",
                ]
            )

            self.assertEqual(result, 0)
            index = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("Keep", index)
            self.assertNotIn(">meta<", index)
            self.assertNotIn("Draft", index)

    def test_unreadable_artwork_falls_back_to_placeholder(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            project = source / "Creator" / "Project"
            project.mkdir(parents=True)
            (project / "cover.jpg").write_text("not an image", encoding="utf-8")
            output = temporary / "site"

            self.assertEqual(main([str(source), str(output)]), 0)

            index = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("cover-placeholder", index)
            self.assertIn("Could not create thumbnail", index)
