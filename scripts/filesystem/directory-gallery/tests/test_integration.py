from __future__ import annotations

import json
import io
import re
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
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
            creators_grid = (output / "creators.html").read_text(encoding="utf-8")
            creator_page = generated_page(output, "creators")
            project_page = generated_page(output, "projects")
            creator_html = creator_page.read_text(encoding="utf-8")
            project_html = project_page.read_text(encoding="utf-8")

            self.assertIn("Things &lt;&amp;&gt; Projects", index)
            creator_items = embedded_data(creators_grid)
            catalog_items = embedded_data(index, 'id="catalog-data"')
            project_items = catalog_items[0]["projects"]
            self.assertEqual([item["title"] for item in creator_items], ["Creator & Co"])
            self.assertNotIn("First Project", [item["title"] for item in creator_items])
            self.assertEqual([item["title"] for item in project_items], ["First Project"])
            self.assertEqual(catalog_items[0]["title"], "Creator & Co")
            self.assertIn('data-catalog-creator-list hidden', index)
            self.assertIn('data-catalog-project-grid', index)
            self.assertFalse((output / "projects.html").exists())
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

    def test_opt_in_collaboration_links_use_sqlite_without_source_changes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            first = "Dietrich Fischer-Dieskau"
            second = "Jörg Demus"
            full = f"{first} & {second}"
            partial = f"{first} & Guest Artist"
            band = "Earth, Wind & Fire"
            (source / first / "Solo Album").mkdir(parents=True)
            (source / second).mkdir()
            (source / full / "Shared Album").mkdir(parents=True)
            (source / partial / "Guest Album").mkdir(parents=True)
            (source / band / "Band Album").mkdir(parents=True)
            make_image(source / first / "portrait.jpg", "red")
            make_image(source / second / "portrait.jpg", "blue")
            make_image(source / full / "Shared Album" / "cover.jpg", "green")
            make_image(source / partial / "Guest Album" / "cover.jpg", "yellow")
            output = temporary / "site"
            original_entries = {
                path.relative_to(source) for path in source.rglob("*")
            }

            def catalog():
                items = embedded_data(
                    (output / "index.html").read_text(encoding="utf-8"),
                    'id="catalog-data"',
                )
                return {item["title"]: item for item in items}

            self.assertEqual(main([str(source), str(output), "--quiet"]), 0)
            entries = catalog()
            first_page = output / entries[first]["href"]
            self.assertNotIn(
                ">Collaborations</h2>", first_page.read_text(encoding="utf-8")
            )
            with sqlite3.connect(output / DATABASE_NAME) as database:
                self.assertEqual(
                    database.execute("SELECT count(*) FROM collaboration_members").fetchone()[0],
                    0,
                )

            self.assertEqual(
                main([str(source), str(output), "--link-collaborations", "--quiet"]),
                0,
            )
            entries = catalog()
            self.assertEqual(sum(len(item["projects"]) for item in entries.values()), 7)
            self.assertEqual(
                len({project["href"] for item in entries.values() for project in item["projects"]}),
                4,
            )
            creator_cards = embedded_data(
                (output / "creators.html").read_text(encoding="utf-8")
            )
            creator_counts = {item["title"]: item["meta"] for item in creator_cards}
            self.assertEqual(creator_counts[first], "3 projects")
            self.assertEqual(creator_counts[second], "1 project")
            first_html = first_page.read_text(encoding="utf-8")
            self.assertIn("3 projects", first_html)
            self.assertEqual(first_html.count(">Projects</h2>"), 1)
            self.assertNotIn(">Collaborations</h2>", first_html)
            rows = rail_data(first_html)
            self.assertEqual(
                [(item["title"], item.get("meta")) for item in rows[0]],
                [
                    ("Guest Album", partial),
                    ("Shared Album", full),
                    ("Solo Album", None),
                ],
            )
            second_html = (output / entries[second]["href"]).read_text(encoding="utf-8")
            self.assertIn("1 project", second_html)
            self.assertEqual(
                [item["title"] for item in rail_data(second_html)[0]],
                ["Shared Album"],
            )

            full_html = (output / entries[full]["href"]).read_text(encoding="utf-8")
            self.assertIn('aria-label="Collaboration members"', full_html)
            self.assertEqual(full_html.count('<a class="member-chip"'), 2)
            self.assertIn(
                f'href="{Path(entries[first]["href"]).name}"', full_html
            )
            self.assertIn(
                f'href="{Path(entries[second]["href"]).name}"', full_html
            )
            self.assertIn('class="member-avatar"><img', full_html)
            self.assertEqual(
                (output / entries[band]["href"]).read_text(encoding="utf-8")
                .count('class="member-chip"'),
                0,
            )
            project_page = output / entries[full]["projects"][0]["href"]
            self.assertEqual(
                project_page.read_text(encoding="utf-8").count('<a class="member-chip"'),
                2,
            )
            partial_html = (output / entries[partial]["href"]).read_text(encoding="utf-8")
            self.assertEqual(partial_html.count('<a class="member-chip"'), 1)
            self.assertIn('<span class="member-chip is-unlinked">', partial_html)
            self.assertIn('Guest Artist</span>', partial_html)
            with sqlite3.connect(output / DATABASE_NAME) as database:
                self.assertEqual(
                    database.execute("SELECT count(*) FROM collaboration_members").fetchone()[0],
                    4,
                )

            self.assertEqual(
                main([
                    str(source), str(output), "--link-collaborations",
                    "--exclude", f"/{second}/", "--quiet",
                ]),
                0,
            )
            entries = catalog()
            self.assertNotIn(second, entries)
            full_html = (output / entries[full]["href"]).read_text(encoding="utf-8")
            self.assertEqual(full_html.count('<a class="member-chip"'), 1)
            self.assertIn(f'{second}</span>', full_html)

            self.assertEqual(
                main([
                    str(source), str(output), "--link-collaborations",
                    "--no-creator-grid", "--quiet",
                ]),
                0,
            )
            self.assertFalse((output / "creators.html").exists())
            entries = catalog()
            self.assertEqual(
                (output / entries[full]["href"])
                .read_text(encoding="utf-8")
                .count('<a class="member-chip"'),
                2,
            )

            self.assertEqual(main([str(source), str(output), "--quiet"]), 0)
            entries = catalog()
            first_html = (output / entries[first]["href"]).read_text(encoding="utf-8")
            self.assertEqual(
                [item["title"] for item in rail_data(first_html)[0]],
                ["Solo Album"],
            )
            with sqlite3.connect(output / DATABASE_NAME) as database:
                self.assertEqual(
                    database.execute("SELECT count(*) FROM collaboration_members").fetchone()[0],
                    0,
                )
            self.assertEqual(
                {path.relative_to(source) for path in source.rglob("*")},
                original_entries,
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

    def test_path_pattern_can_exclude_projects_without_hiding_their_creator(self):
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
            items = embedded_data(index, 'id="catalog-data"')
            self.assertEqual(
                [item["title"] for item in items],
                ["Creator A", "Creator B"],
            )
            self.assertEqual(
                [project["title"] for item in items for project in item["projects"]],
                ["Keep"],
            )

    def test_exclude_from_removes_underscore_entries_and_prunes_stale_pages(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            make_image(source / "_Archive" / "Old" / "cover.jpg", "red")
            make_image(source / "Creator" / "_Draft" / "cover.jpg", "blue")
            project = source / "Creator" / "Book"
            make_image(project / "cover.jpg", "green")
            make_image(project / "_scan.jpg", "purple")
            make_image(project / "scan.jpg", "orange")
            ignore_file = source / ".galleryignore"
            ignore_file.write_text(
                "# Private collection entries\n_*\n", encoding="utf-8"
            )
            output = temporary / "site"

            self.assertEqual(main([str(source), str(output), "--quiet"]), 0)
            self.assertEqual(len(list((output / "creators").glob("*.html"))), 2)
            self.assertEqual(len(list((output / "projects").glob("*.html"))), 3)

            self.assertEqual(
                main(
                    [
                        str(source),
                        str(output),
                        "--exclude-from",
                        str(ignore_file),
                        "--quiet",
                    ]
                ),
                0,
            )
            self.assertEqual(len(list((output / "creators").glob("*.html"))), 1)
            self.assertEqual(len(list((output / "projects").glob("*.html"))), 1)
            self.assertEqual(len(list((output / "thumbnails").rglob("*.jpg"))), 2)
            project_html = generated_page(output, "projects").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("_scan.jpg", project_html)
            self.assertIn("scan.jpg", project_html)

    def test_invalid_exclusion_pattern_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            source.mkdir()
            output = temporary / "site"

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(
                    main([str(source), str(output), "--exclude", "invalid\\"]), 1
                )
            self.assertIn("invalid exclusion pattern", stderr.getvalue())
            self.assertFalse(output.exists())

    def test_catalog_contains_projects_from_all_creators(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            (source / "Creator A" / "Zulu").mkdir(parents=True)
            (source / "Creator B" / "Alpha").mkdir(parents=True)
            output = temporary / "site"

            self.assertEqual(main([str(source), str(output)]), 0)

            index = (output / "index.html").read_text(encoding="utf-8")
            items = embedded_data(index, 'id="catalog-data"')
            self.assertEqual(
                [project["title"] for item in items for project in item["projects"]],
                ["Zulu", "Alpha"],
            )
            self.assertFalse((output / "projects.html").exists())

    def test_catalog_stacks_creators_and_projects_with_initial_fallback(self):
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

            self.assertEqual(main([str(source), str(output), "--quiet"]), 0)

            index = (output / "index.html").read_text(encoding="utf-8")
            items = embedded_data(index, 'id="catalog-data"')
            self.assertEqual(
                [item["title"] for item in items], ["Creator A", "Creator B"]
            )
            self.assertEqual(
                [project["title"] for project in items[0]["projects"]],
                ["Alpha", "Zulu"],
            )
            self.assertEqual(
                [project["initial"] for project in items[0]["projects"]],
                ["A", "Z"],
            )
            self.assertIsNotNone(items[0]["image"])
            self.assertIsNone(items[1]["image"])
            self.assertEqual(items[1]["placeholder"], "C")
            self.assertIn('class="overview-page catalog-overview"', index)
            self.assertIn('data-catalog-view="creators" aria-pressed="false"', index)
            self.assertIn('data-catalog-view="projects" aria-pressed="true"', index)
            self.assertIn("data-catalog-creator-list hidden", index)
            self.assertIn("data-catalog-project-grid", index)
            self.assertIn(">Catalog</a>", index)
            self.assertIn(">Creators</a>", index)
            self.assertNotIn(">Projects</a>", index)
            self.assertFalse((output / "projects.html").exists())
            self.assertTrue((output / "creators.html").exists())
            self.assertEqual(len(list((output / "creators").glob("*.html"))), 2)
            self.assertEqual(len(list((output / "projects").glob("*.html"))), 3)

            project_detail = next((output / "projects").glob("*.html"))
            detail_html = project_detail.read_text(encoding="utf-8")
            self.assertIn(">Catalog</a>", detail_html)
            self.assertNotIn('href="../projects.html">Projects</a>', detail_html)

    def test_opt_out_removes_and_restores_creator_grid(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "Source"
            (source / "Creator" / "Project").mkdir(parents=True)
            output = temporary / "site"

            self.assertEqual(main([str(source), str(output), "--quiet"]), 0)
            self.assertTrue((output / "creators.html").is_file())

            self.assertEqual(
                main([str(source), str(output), "--no-creator-grid", "--quiet"]),
                0,
            )
            self.assertFalse((output / "creators.html").exists())
            self.assertFalse((output / "projects.html").exists())
            index = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn('data-catalog-creator-list hidden', index)
            self.assertIn('data-catalog-project-grid', index)
            self.assertNotIn(">Creators</a>", index)
            creator_detail = generated_page(output, "creators").read_text(
                encoding="utf-8"
            )
            self.assertIn(">Catalog</a>", creator_detail)
            self.assertNotIn(">Creators</a>", creator_detail)

            self.assertEqual(main([str(source), str(output), "--quiet"]), 0)
            self.assertTrue((output / "creators.html").is_file())

    def test_catalog_embeds_large_collection_without_static_creator_sections(self):
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

            self.assertEqual(main([str(source), str(output), "--quiet"]), 0)

            index = (output / "index.html").read_text(encoding="utf-8")
            items = embedded_data(index, 'id="catalog-data"')
            self.assertEqual(len(items), 45)
            self.assertTrue(all(len(item["projects"]) == 2 for item in items))
            self.assertNotIn('class="grouped-creator"', index)
            self.assertIn("data-catalog-pagination", index)

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

            index_html = (output / "index.html").read_text(encoding="utf-8")
            catalog_items = embedded_data(index_html, 'id="catalog-data"')
            self.assertEqual(
                sum(len(item["projects"]) for item in catalog_items), 206
            )
            self.assertIn("data-catalog-pagination", index_html)
            self.assertNotIn('class="overview-card', index_html)
            self.assertIn("208 catalog notices", index_html)
            self.assertIn("8 additional notices", index_html)
            self.assertFalse((output / "projects.html").exists())

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
