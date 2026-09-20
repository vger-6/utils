from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from directory_gallery.output import DATABASE_NAME
from directory_gallery.state import CatalogState


class CatalogStateTests(unittest.TestCase):
    def test_stale_records_are_removed_in_bounded_batches(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            output.mkdir()
            warnings = []

            with CatalogState(output, source, warnings) as state:
                for number in range(501):
                    digest = f"{number:024x}"
                    relative = f"thumbnails/{digest[:2]}/{digest[2:4]}/{digest}.jpg"
                    preview = output / relative
                    preview.parent.mkdir(parents=True, exist_ok=True)
                    preview.touch()
                    state.record_preview(
                        f"/source/{number}", "image", relative, number, number
                    )

                    page_relative = f"projects/{number:016x}.html"
                    page = output / page_relative
                    page.parent.mkdir(parents=True, exist_ok=True)
                    page.touch()
                    state.record_generated(page_relative)
                state.finish()

            with CatalogState(output, source, warnings) as state:
                state.finish()

            self.assertEqual(list((output / "thumbnails").rglob("*.jpg")), [])
            self.assertEqual(list((output / "projects").glob("*.html")), [])
            with sqlite3.connect(output / DATABASE_NAME) as database:
                self.assertEqual(
                    database.execute("SELECT count(*) FROM previews").fetchone()[0],
                    0,
                )
                self.assertEqual(
                    database.execute(
                        "SELECT count(*) FROM generated_files"
                    ).fetchone()[0],
                    0,
                )


if __name__ == "__main__":
    unittest.main()
