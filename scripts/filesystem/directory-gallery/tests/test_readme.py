from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from directory_gallery.readme import render_readme


class ReadmeTests(unittest.TestCase):
    def test_renders_safe_markdown_and_rewrites_only_allowed_local_links(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "Creator"
            output = root / "site" / "creators" / "page.html"
            source.mkdir()
            output.parent.mkdir(parents=True)
            (source / "photo.jpg").touch()
            (source / "secret.txt").touch()
            outside = root / "outside.jpg"
            outside.touch()
            readme = source / "README.md"
            readme.write_text(
                "**Bold** <b>raw</b>\n\n"
                "[photo](photo.jpg) [text](secret.txt) "
                "[outside](../outside.jpg) [web](https://example.com)",
                encoding="utf-8",
            )
            warnings = []

            rendered = render_readme(readme, source, output, warnings)

            self.assertIn("<strong>Bold</strong>", rendered)
            self.assertIn("&lt;b&gt;raw&lt;/b&gt;", rendered)
            self.assertIn("photo.jpg", rendered)
            self.assertEqual(rendered.count('href="#"'), 2)
            self.assertIn('href="https://example.com"', rendered)
            self.assertIn('rel="noopener noreferrer"', rendered)
            self.assertEqual(warnings, [])

    def test_unreadable_or_missing_readme_is_nonfatal(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            warnings = []
            self.assertEqual(render_readme(None, root, root / "page.html", warnings), "")
            self.assertEqual(warnings, [])
