from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from directory_gallery.errors import UserError
from directory_gallery.output import (
    DATABASE_NAME,
    MANIFEST_NAME,
    prepare_output,
    resolve_paths,
)


class OutputTests(unittest.TestCase):
    def test_input_and_output_must_not_overlap(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "input"
            root.mkdir()

            with self.assertRaises(UserError):
                resolve_paths(str(root), str(root / "catalog"))

            output_parent = Path(temporary_directory) / "output"
            nested_input = output_parent / "input"
            nested_input.mkdir(parents=True)
            with self.assertRaises(UserError):
                resolve_paths(str(nested_input), str(output_parent))

    def test_nonempty_unmanaged_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "output"
            output.mkdir()
            sentinel = output / "sentinel.txt"
            sentinel.write_text("unchanged", encoding="utf-8")

            with self.assertRaises(UserError):
                prepare_output(output)

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged")

    def test_empty_and_current_outputs_are_accepted(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            empty = root / "empty"
            empty.mkdir()
            prepare_output(empty)

            current = root / "current"
            current.mkdir()
            (current / MANIFEST_NAME).write_text(
                '{"format": 2, "generator": "directory-gallery"}',
                encoding="utf-8",
            )
            (current / DATABASE_NAME).touch()
            prepare_output(current)

    def test_older_manifest_is_rejected_without_modifying_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "output"
            output.mkdir()
            manifest = output / MANIFEST_NAME
            original = '{"format": 1, "generator": "directory-gallery"}'
            manifest.write_text(original, encoding="utf-8")

            with self.assertRaises(UserError):
                prepare_output(output)

            self.assertEqual(manifest.read_text(encoding="utf-8"), original)
            self.assertFalse((output / DATABASE_NAME).exists())

    def test_current_manifest_requires_its_cache_database(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "output"
            output.mkdir()
            (output / MANIFEST_NAME).write_text(
                '{"format": 2, "generator": "directory-gallery"}',
                encoding="utf-8",
            )

            with self.assertRaises(UserError):
                prepare_output(output)

    def test_current_cache_database_must_not_be_a_symbolic_link(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "output"
            output.mkdir()
            (output / MANIFEST_NAME).write_text(
                '{"format": 2, "generator": "directory-gallery"}',
                encoding="utf-8",
            )
            target = root / "database.sqlite3"
            target.touch()
            try:
                (output / DATABASE_NAME).symlink_to(target)
            except (OSError, NotImplementedError):
                return

            with self.assertRaises(UserError):
                prepare_output(output)

    def test_invalid_manifest_and_symbolic_link_output_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            source.mkdir()
            output = root / "output"
            output.mkdir()
            (output / MANIFEST_NAME).write_text("[]", encoding="utf-8")

            with self.assertRaises(UserError):
                prepare_output(output)

            link = root / "output-link"
            try:
                link.symlink_to(output, target_is_directory=True)
            except (OSError, NotImplementedError):
                return
            with self.assertRaises(UserError):
                resolve_paths(str(source), str(link))
