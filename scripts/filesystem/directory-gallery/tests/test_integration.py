from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pymupdf
from PIL import Image

from directory_gallery.cli import main
from directory_gallery.output import MANIFEST_NAME


def make_image(path: Path, color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 48), color).save(path)


def make_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=200, height=300)
    page.insert_text((24, 40), "Preview")
    document.save(path)
    document.close()


def generated_page(output: Path, directory: str) -> Path:
    pages = list((output / directory).glob("*.html"))
    if len(pages) != 1:
        raise AssertionError(f"expected one {directory} page, found {pages}")
    return pages[0]


class IntegrationTests(unittest.TestCase):
    def test_builds_overviews_details_markdown_previews_and_media_rows(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            creator = source / "Creator & Co"
            project = creator / "First Project"
            scans = project / "Scans"
            scans.mkdir(parents=True)
            make_image(creator / "portrait.jpg", "#244b75")
            make_image(creator / "meta" / "artist.jpg", "#455d7a")
            make_image(project / "cover.png", "#8f3d58")
            make_image(project / "photo.gif", "#662244")
            make_image(scans / "scan.webp", "#335577")
            make_image(project / "movie.poster.jpg", "#663322")
            (project / "movie.mp4").touch()
            (project / "track.m4a").touch()
            (project / "ignored.json").write_text("{}", encoding="utf-8")
            make_pdf(project / "document.pdf")
            (creator / "README.md").write_text(
                "# Biography\n\n**Important** <script>alert(1)</script>",
                encoding="utf-8",
            )
            (project / "README.md").write_text(
                "Project [photo](photo.gif).", encoding="utf-8"
            )
            output = temporary / "site"

            result = main([str(source), str(output), "--title", "Things <&> Projects"])

            self.assertEqual(result, 0)
            index = (output / "index.html").read_text(encoding="utf-8")
            projects = (output / "projects.html").read_text(encoding="utf-8")
            creator_page = generated_page(output, "creators")
            project_page = generated_page(output, "projects")
            creator_html = creator_page.read_text(encoding="utf-8")
            project_html = project_page.read_text(encoding="utf-8")

            self.assertIn("Things &lt;&amp;&gt; Projects", index)
            self.assertIn("Creator &amp; Co", index)
            self.assertNotIn("First Project", index)
            self.assertIn("First Project", projects)
            self.assertIn("Creator &amp; Co", projects)
            self.assertIn("Biography", creator_html)
            self.assertIn("<strong>Important</strong>", creator_html)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", creator_html)
            self.assertIn(">Projects</h2>", creator_html)
            self.assertIn(">Images</h2>", creator_html)
            self.assertIn("artist.jpg", creator_html)
            self.assertIn("Project <a href=", project_html)
            self.assertIn(">Images</h2>", project_html)
            self.assertIn(">Images · Scans</h2>", project_html)
            self.assertIn(">PDFs</h2>", project_html)
            self.assertIn(">Videos</h2>", project_html)
            self.assertIn(">Audio</h2>", project_html)
            self.assertIn('data-media-kind="pdf"', project_html)
            self.assertIn('data-media-kind="video"', project_html)
            self.assertIn('data-media-kind="audio"', project_html)
            self.assertNotIn("ignored.json", project_html)
            self.assertNotIn("movie.poster.jpg</span>", project_html)
            self.assertTrue((output / "assets" / "directory-gallery.css").is_file())
            self.assertTrue((output / "assets" / "directory-gallery.js").is_file())

            manifest = json.loads((output / MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["generated_files"]), 6)
            self.assertGreaterEqual(len(manifest["thumbnails"]), 7)
            self.assertTrue(any(key.startswith("pdf:") for key in manifest["thumbnails"]))

    def test_removes_stale_generated_pages_and_cached_thumbnails(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            old = source / "Creator" / "Old Project"
            old.mkdir(parents=True)
            make_image(old / "cover.jpg", "red")
            output = temporary / "site"

            self.assertEqual(main([str(source), str(output)]), 0)
            old_page = generated_page(output, "projects")
            self.assertEqual(len(list((output / "thumbnails").glob("*.jpg"))), 1)

            new = old.rename(source / "Creator" / "New Project")
            make_image(new / "cover.jpg", "blue")
            self.assertEqual(main([str(source), str(output)]), 0)

            self.assertFalse(old_page.exists())
            self.assertEqual(len(list((output / "projects").glob("*.html"))), 1)
            self.assertEqual(len(list((output / "thumbnails").glob("*.jpg"))), 1)

    def test_repeatable_project_exclusions_do_not_hide_creators_or_reserved_meta(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            (source / "Creator A" / "Keep").mkdir(parents=True)
            (source / "Creator A" / "meta").mkdir()
            (source / "Creator B" / "Draft").mkdir(parents=True)
            make_image(source / "Creator A" / "meta" / "photo.jpg", "green")
            output = temporary / "site"

            result = main(
                [str(source), str(output), "--exclude", "Creator B/*"]
            )

            self.assertEqual(result, 0)
            index = (output / "index.html").read_text(encoding="utf-8")
            projects = (output / "projects.html").read_text(encoding="utf-8")
            self.assertIn("Creator A", index)
            self.assertIn("Creator B", index)
            self.assertIn("Keep", projects)
            self.assertNotIn(">meta<", projects)
            self.assertNotIn("Draft", projects)

    def test_global_project_overview_is_ordered_by_project_title(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            (source / "Creator A" / "Zulu").mkdir(parents=True)
            (source / "Creator B" / "Alpha").mkdir(parents=True)
            output = temporary / "site"

            self.assertEqual(main([str(source), str(output)]), 0)

            projects = (output / "projects.html").read_text(encoding="utf-8")
            self.assertLess(projects.index(">Alpha</span>"), projects.index(">Zulu</span>"))

    def test_unreadable_artwork_falls_back_to_placeholder(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            project = source / "Creator" / "Project"
            project.mkdir(parents=True)
            (project / "cover.jpg").write_text("not an image", encoding="utf-8")
            output = temporary / "site"

            self.assertEqual(main([str(source), str(output)]), 0)

            projects = (output / "projects.html").read_text(encoding="utf-8")
            index = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("cover-placeholder", projects)
            self.assertIn("Could not create thumbnail", index)
