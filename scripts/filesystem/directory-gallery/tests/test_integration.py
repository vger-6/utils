from __future__ import annotations

import json
import hashlib
import io
import os
import re
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import pymupdf
from PIL import Image

from directory_gallery.cli import main
from directory_gallery.output import DATABASE_NAME, MANIFEST_FORMAT, MANIFEST_NAME


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


def embedded_data(document: str, selector: str = 'id="overview-data"') -> list[dict]:
    match = re.search(
        rf'<script type="application/json" {selector}>(.*?)</script>',
        document,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing embedded data: {selector}")
    value = json.loads(match.group(1))
    if not isinstance(value, list):
        raise AssertionError("embedded data is not a list")
    return value


def rail_data(document: str) -> list[list[dict]]:
    return [
        json.loads(value)
        for value in re.findall(
            r'<script type="application/json" data-rail-data>(.*?)</script>',
            document,
            flags=re.DOTALL,
        )
    ]


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
            creator_items = embedded_data(index)
            project_items = embedded_data(projects)
            self.assertEqual([item["title"] for item in creator_items], ["Creator & Co"])
            self.assertNotIn("First Project", [item["title"] for item in creator_items])
            self.assertEqual([item["title"] for item in project_items], ["First Project"])
            self.assertEqual(project_items[0]["meta"], "Creator & Co")
            self.assertIn("Biography", creator_html)
            self.assertIn("<strong>Important</strong>", creator_html)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", creator_html)
            for detail_html in (creator_html, project_html):
                self.assertIn('class="readme-container"', detail_html)
                self.assertIn('class="readme-body"', detail_html)
                self.assertIn('aria-controls="readme-content"', detail_html)
                self.assertNotIn('class="readme is-collapsed"', detail_html)
            self.assertIn(">Projects</h2>", creator_html)
            self.assertIn(">Images</h2>", creator_html)
            self.assertIn("artist.jpg", creator_html)
            self.assertIn("Project <a href=", project_html)
            self.assertIn(">Images</h2>", project_html)
            self.assertIn(">Images · Scans</h2>", project_html)
            self.assertIn(">PDFs</h2>", project_html)
            self.assertIn(">Videos</h2>", project_html)
            self.assertIn(">Audio</h2>", project_html)
            self.assertIn('class="lightbox-viewer"', project_html)
            self.assertRegex(
                project_html,
                r'class="lightbox-media" id="lightbox-media"></div>\s*'
                r'<div class="audio-playlist" id="audio-playlist" hidden></div>',
            )
            kinds = {
                item["kind"] for row in rail_data(project_html) for item in row
            }
            self.assertTrue({"image", "pdf", "video", "audio"}.issubset(kinds))
            self.assertNotIn("ignored.json", project_html)
            media_titles = {
                item["title"] for row in rail_data(project_html) for item in row
            }
            self.assertNotIn("movie.poster.jpg", media_titles)
            self.assertTrue((output / "assets" / "directory-gallery.css").is_file())
            self.assertTrue((output / "assets" / "directory-gallery.js").is_file())

            manifest = json.loads((output / MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertEqual(manifest["format"], MANIFEST_FORMAT)
            self.assertEqual(manifest["database"], DATABASE_NAME)
            with sqlite3.connect(output / DATABASE_NAME) as database:
                generated_count = database.execute(
                    "SELECT count(*) FROM generated_files"
                ).fetchone()[0]
                preview_count = database.execute(
                    "SELECT count(*) FROM previews"
                ).fetchone()[0]
                pdf_count = database.execute(
                    "SELECT count(*) FROM previews WHERE kind = 'pdf'"
                ).fetchone()[0]
            self.assertEqual(generated_count, 6)
            self.assertGreaterEqual(preview_count, 7)
            self.assertEqual(pdf_count, 1)
            self.assertTrue(
                all(
                    len(path.relative_to(output / "thumbnails").parts) == 3
                    for path in (output / "thumbnails").rglob("*.jpg")
                )
            )

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
            self.assertEqual(len(list((output / "thumbnails").rglob("*.jpg"))), 1)

            new = old.rename(source / "Creator" / "New Project")
            make_image(new / "cover.jpg", "blue")
            self.assertEqual(main([str(source), str(output)]), 0)

            self.assertFalse(old_page.exists())
            self.assertEqual(len(list((output / "projects").glob("*.html"))), 1)
            self.assertEqual(len(list((output / "thumbnails").rglob("*.jpg"))), 1)

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
            self.assertEqual(
                [item["title"] for item in embedded_data(index)],
                ["Creator A", "Creator B"],
            )
            self.assertEqual(
                [item["title"] for item in embedded_data(projects)], ["Keep"]
            )

    def test_global_project_overview_is_ordered_by_project_title(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            (source / "Creator A" / "Zulu").mkdir(parents=True)
            (source / "Creator B" / "Alpha").mkdir(parents=True)
            output = temporary / "site"

            self.assertEqual(main([str(source), str(output)]), 0)

            projects = (output / "projects.html").read_text(encoding="utf-8")
            self.assertEqual(
                [item["title"] for item in embedded_data(projects)],
                ["Alpha", "Zulu"],
            )

    def test_grouped_overview_stacks_creators_and_projects_without_portrait_placeholders(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            creator_a = source / "Creator A"
            creator_b = source / "Creator B"
            make_image(creator_a / "portrait.jpg", "navy")
            make_image(creator_a / "Zulu" / "cover.jpg", "red")
            make_image(creator_a / "Alpha" / "cover.jpg", "green")
            make_image(creator_b / "Only Project" / "cover.jpg", "blue")
            output = temporary / "site"

            self.assertEqual(
                main(
                    [
                        str(source),
                        str(output),
                        "--overview",
                        "grouped",
                        "--quiet",
                    ]
                ),
                0,
            )

            index = (output / "index.html").read_text(encoding="utf-8")
            items = embedded_data(index, 'id="grouped-data"')
            self.assertEqual(
                [item["title"] for item in items], ["Creator A", "Creator B"]
            )
            self.assertEqual(
                [project["title"] for project in items[0]["projects"]],
                ["Alpha", "Zulu"],
            )
            self.assertIsNotNone(items[0]["image"])
            self.assertIsNone(items[1]["image"])
            self.assertIn('class="overview-page grouped-overview"', index)
            self.assertIn("data-grouped-list", index)
            self.assertIn(">Overview</a>", index)
            self.assertNotIn(">Creators</a>", index)
            self.assertNotIn(">Projects</a>", index)
            self.assertNotIn("portrait-placeholder", index)
            self.assertFalse((output / "projects.html").exists())
            self.assertEqual(len(list((output / "creators").glob("*.html"))), 2)
            self.assertEqual(len(list((output / "projects").glob("*.html"))), 3)

            project_detail = next((output / "projects").glob("*.html"))
            detail_html = project_detail.read_text(encoding="utf-8")
            self.assertIn(">Overview</a>", detail_html)
            self.assertNotIn('href="../projects.html">Projects</a>', detail_html)

    def test_switching_overview_modes_removes_and_restores_projects_overview(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            (source / "Creator" / "Project").mkdir(parents=True)
            output = temporary / "site"

            self.assertEqual(main([str(source), str(output), "--quiet"]), 0)
            self.assertTrue((output / "projects.html").is_file())

            self.assertEqual(
                main(
                    [
                        str(source),
                        str(output),
                        "--overview",
                        "grouped",
                        "--quiet",
                    ]
                ),
                0,
            )
            self.assertFalse((output / "projects.html").exists())

            self.assertEqual(main([str(source), str(output), "--quiet"]), 0)
            self.assertTrue((output / "projects.html").is_file())

    def test_grouped_overview_embeds_large_catalog_without_static_creator_sections(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            for creator_number in range(45):
                for project_number in range(2):
                    project = (
                        source
                        / f"Creator {creator_number:02d}"
                        / f"Project {project_number}"
                    )
                    project.mkdir(parents=True)
            output = temporary / "site"

            self.assertEqual(
                main(
                    [
                        str(source),
                        str(output),
                        "--overview",
                        "grouped",
                        "--quiet",
                    ]
                ),
                0,
            )

            index = (output / "index.html").read_text(encoding="utf-8")
            items = embedded_data(index, 'id="grouped-data"')
            self.assertEqual(len(items), 45)
            self.assertTrue(all(len(item["projects"]) == 2 for item in items))
            self.assertNotIn('class="grouped-creator"', index)
            self.assertIn("data-grouped-pagination", index)

    def test_unreadable_artwork_falls_back_to_placeholder(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            project = source / "Creator" / "Project"
            project.mkdir(parents=True)
            (project / "cover.jpg").write_text("not an image", encoding="utf-8")
            output = temporary / "site"

            self.assertEqual(main([str(source), str(output)]), 0)

            project_page = generated_page(output, "projects")
            project_html = project_page.read_text(encoding="utf-8")
            index = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("cover-placeholder", project_html)
            self.assertNotIn('class="readme-toggle"', project_html)
            self.assertIn("Could not create thumbnail", index)

    def test_migrates_legacy_manifest_and_flat_thumbnail_without_regeneration(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            cover = source / "Creator" / "Project" / "cover.jpg"
            make_image(cover, "purple")
            output = temporary / "site"
            (output / "thumbnails").mkdir(parents=True)
            source_key = os.fspath(cover.resolve())
            digest = hashlib.sha256(os.fsencode(source_key)).hexdigest()[:24]
            legacy_thumbnail = output / "thumbnails" / f"{digest}.jpg"
            make_image(legacy_thumbnail, "purple")
            source_stat = cover.stat()
            (output / MANIFEST_NAME).write_text(
                json.dumps(
                    {
                        "format": 1,
                        "generator": "directory-gallery",
                        "generated_files": [],
                        "thumbnails": {
                            source_key: {
                                "kind": "image",
                                "file": legacy_thumbnail.name,
                                "mtime_ns": source_stat.st_mtime_ns,
                                "size": source_stat.st_size,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(main([str(source), str(output), "--quiet"]), 0)

            manifest = json.loads((output / MANIFEST_NAME).read_text(encoding="utf-8"))
            migrated = output / "thumbnails" / digest[:2] / digest[2:4] / f"{digest}.jpg"
            self.assertEqual(manifest["format"], MANIFEST_FORMAT)
            self.assertFalse(legacy_thumbnail.exists())
            self.assertTrue(migrated.is_file())
            with sqlite3.connect(output / DATABASE_NAME) as database:
                row = database.execute(
                    "SELECT file, last_seen FROM previews WHERE source_key = ?",
                    (source_key,),
                ).fetchone()
            self.assertEqual(row[0], migrated.relative_to(output).as_posix())
            self.assertGreater(row[1], 0)

    def test_reuses_unchanged_previews_from_sqlite_cache(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            cover = source / "Creator" / "Project" / "cover.jpg"
            make_image(cover, "navy")
            output = temporary / "site"

            self.assertEqual(main([str(source), str(output), "--quiet"]), 0)
            preview = next((output / "thumbnails").rglob("*.jpg"))
            preview_mtime = preview.stat().st_mtime_ns
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main([str(source), str(output), "--quiet"]), 0)

            self.assertEqual(preview.stat().st_mtime_ns, preview_mtime)
            self.assertIn("previews: 0 generated, 1 reused", stdout.getvalue())

    def test_large_overview_and_media_row_use_bounded_initial_dom(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            for number in range(205):
                (source / "Many Projects" / f"Project {number:03d}").mkdir(
                    parents=True
                )
            large_project = source / "Audio Creator" / "Large Album"
            large_project.mkdir(parents=True)
            for number in range(1000):
                (large_project / f"track-{number:04d}.mp3").touch()
            output = temporary / "site"

            self.assertEqual(main([str(source), str(output), "--quiet"]), 0)

            projects_html = (output / "projects.html").read_text(encoding="utf-8")
            project_items = embedded_data(projects_html)
            self.assertEqual(len(project_items), 206)
            self.assertIn("data-pagination", projects_html)
            self.assertNotIn('class="overview-card', projects_html)

            index_html = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("208 catalog notices", index_html)
            self.assertIn("8 additional notices", index_html)

            detail_pages = (output / "projects").glob("*.html")
            album_html = next(
                document
                for document in (path.read_text(encoding="utf-8") for path in detail_pages)
                if "track-0999.mp3" in document
            )
            audio_rows = [
                row
                for row in rail_data(album_html)
                if row and row[0]["kind"] == "audio"
            ]
            self.assertEqual(len(audio_rows), 1)
            self.assertEqual(len(audio_rows[0]), 1000)
            self.assertNotIn('class="media-card', album_html)
