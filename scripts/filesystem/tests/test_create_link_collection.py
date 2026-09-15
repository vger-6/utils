from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "create-link-collection.py"
SPEC = importlib.util.spec_from_file_location("create_link_collection", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"could not load {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class LinkCollectionTests(unittest.TestCase):
    def run_main(self, *arguments: str):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = MODULE.main(arguments)
        return result, stdout.getvalue(), stderr.getvalue()

    def make_item(self, root: Path, group: str, item: str) -> Path:
        path = root / group / item
        path.mkdir(parents=True)
        return path

    def test_creates_named_relative_links_and_marker(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            root = temporary / "Library"
            first = self.make_item(root, "Astra Vey", "Glass Circuit")
            second = self.make_item(root, "Nia Solen", "Static Garden")
            (first / "extras" / "Booklet").mkdir(parents=True)
            output = root / "_All"

            with mock.patch.object(MODULE.os, "symlink") as symlink:
                result, stdout, stderr = self.run_main(
                    "--root", str(root), "--output", str(output)
                )

            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            self.assertIn("Created 2 link(s)", stdout)
            self.assertEqual(symlink.call_count, 2)
            symlink.assert_has_calls(
                [
                    mock.call(
                        os.path.relpath(first, start=output),
                        output / "Astra Vey - Glass Circuit",
                        target_is_directory=True,
                    ),
                    mock.call(
                        os.path.relpath(second, start=output),
                        output / "Nia Solen - Static Garden",
                        target_is_directory=True,
                    ),
                ]
            )

            marker = json.loads((output / MODULE.MARKER_NAME).read_text("utf-8"))
            self.assertEqual(marker["format"], 1)
            self.assertEqual(marker["root"], str(root.resolve()))

    def test_basename_exclusion_matches_items_only_and_is_case_sensitive(self):
        self.assertTrue(
            MODULE.matches_exclusion("ExcludeThis", "ExcludeThis", ["ExcludeThis"])
        )
        self.assertFalse(
            MODULE.matches_exclusion("ExcludeThis", "KeepThis", ["ExcludeThis"])
        )
        self.assertFalse(MODULE.matches_exclusion("Group", "Debut", ["debut"]))

    def test_path_patterns_match_group_and_item_components(self):
        self.assertTrue(
            MODULE.matches_exclusion("Nia Solen", "Static Garden", ["Nia Solen/*"])
        )
        self.assertTrue(
            MODULE.matches_exclusion("Any Artist", "ExcludeThis", ["*/ExcludeThis"])
        )
        self.assertFalse(
            MODULE.matches_exclusion("Other", "Static Garden", ["Nia Solen/*"])
        )
        self.assertTrue(MODULE.matches_exclusion("Group", "Book 1", ["Book ?"]))
        self.assertTrue(MODULE.matches_exclusion("Group", "Album B", ["Album [AB]"]))

    def test_repeated_exclusions_filter_discovered_items(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "Library"
            self.make_item(root, "Astra Vey", "_misc")
            self.make_item(root, "Nia Solen", "Debut")
            self.make_item(root, "Nia Solen", "Static Garden")
            output = root / "_All"

            result, stdout, stderr = self.run_main(
                "--root",
                str(root),
                "--output",
                str(output),
                "--exclude",
                "_misc",
                "--exclude",
                "Nia Solen/Static Garden",
                "--dry-run",
            )

            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            self.assertIn("would create 1 link(s)", stdout)
            self.assertIn("Nia Solen - Debut", stdout)
            self.assertNotIn("Astra Vey - _misc", stdout)
            self.assertNotIn("Nia Solen - Static Garden", stdout)

    def test_invalid_exclusion_pattern_fails_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "Library"
            self.make_item(root, "Group", "Item")
            output = root / "_All"

            result, _, stderr = self.run_main(
                "--root",
                str(root),
                "--output",
                str(output),
                "--exclude",
                "Group/**",
            )

            self.assertEqual(result, 1)
            self.assertIn("'**' is not supported", stderr)
            self.assertFalse(output.exists())

    def test_backslash_pattern_is_rejected_with_separator_guidance(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "Library"
            self.make_item(root, "Group", "Item")
            output = root / "_All"

            result, _, stderr = self.run_main(
                "--root",
                str(root),
                "--output",
                str(output),
                "--exclude",
                "Group\\Item",
            )

            self.assertEqual(result, 1)
            self.assertIn("use '/' as the separator", stderr)
            self.assertFalse(output.exists())

    def test_existing_output_is_an_unchanged_successful_no_op(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            output = temporary / "Existing"
            output.mkdir()
            sentinel = output / "sentinel.txt"
            sentinel.write_text("unchanged", encoding="utf-8")

            result, stdout, stderr = self.run_main(
                "--root",
                str(temporary / "missing-root"),
                "--output",
                str(output),
            )

            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            self.assertIn("already exists", stdout)
            self.assertEqual(sentinel.read_text("utf-8"), "unchanged")

    def test_existing_non_directory_output_is_an_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            root = temporary / "Library"
            root.mkdir()
            output = temporary / "output-file"
            output.write_text("existing", encoding="utf-8")

            result, _, stderr = self.run_main(
                "--root", str(root), "--output", str(output)
            )

            self.assertEqual(result, 1)
            self.assertIn("not a directory", stderr)
            self.assertEqual(output.read_text("utf-8"), "existing")

    def test_no_items_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "Library"
            (root / "Empty Group").mkdir(parents=True)
            output = root / "_All"

            result, stdout, stderr = self.run_main(
                "--root", str(root), "--output", str(output)
            )

            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            self.assertIn("No eligible items", stdout)
            self.assertFalse(output.exists())

    def test_missing_root_is_an_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            root = temporary / "Missing"
            output = temporary / "_All"

            result, _, stderr = self.run_main(
                "--root", str(root), "--output", str(output)
            )

            self.assertEqual(result, 1)
            self.assertIn("root does not exist", stderr)
            self.assertFalse(output.exists())

    def test_dry_run_lists_links_without_creating_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "Library"
            item = self.make_item(root, "Group", "Item")
            output = root / "_All"

            result, stdout, stderr = self.run_main(
                "--root",
                str(root),
                "--output",
                str(output),
                "--dry-run",
            )

            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            self.assertIn("Group - Item", stdout)
            self.assertIn(os.path.relpath(item, start=output), stdout)
            self.assertFalse(output.exists())

    def test_missing_output_parents_are_created(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            root = temporary / "Library"
            self.make_item(root, "Group", "Item")
            output = temporary / "new" / "parent" / "_All"

            with mock.patch.object(MODULE.os, "symlink"):
                result, stdout, stderr = self.run_main(
                    "--root", str(root), "--output", str(output)
                )

            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            self.assertIn("Created 1 link(s)", stdout)
            self.assertTrue((output / MODULE.MARKER_NAME).is_file())

    def test_generated_collection_markers_prevent_rediscovery(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "Library"
            self.make_item(root, "Real Group", "Real Item")

            previous_group_output = root / "_Previous"
            (previous_group_output / "Not a Link").mkdir(parents=True)
            (previous_group_output / MODULE.MARKER_NAME).write_text("{}", "utf-8")

            previous_item_output = root / "Group" / "_Previous Item Output"
            previous_item_output.mkdir(parents=True)
            (previous_item_output / MODULE.MARKER_NAME).write_text("{}", "utf-8")

            output = root / "_New"
            with mock.patch.object(MODULE.os, "symlink") as symlink:
                result, _, stderr = self.run_main(
                    "--root", str(root), "--output", str(output)
                )

            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(symlink.call_count, 1)
            self.assertEqual(symlink.call_args.args[1].name, "Real Group - Real Item")

    def test_duplicate_generated_name_aborts_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "Library"
            self.make_item(root, "A", "B - C")
            self.make_item(root, "A - B", "C")
            output = root / "_All"

            result, _, stderr = self.run_main(
                "--root", str(root), "--output", str(output)
            )

            self.assertEqual(result, 1)
            self.assertIn("collision", stderr)
            self.assertFalse(output.exists())

    def test_link_failure_rolls_back_new_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "Library"
            self.make_item(root, "A", "One")
            self.make_item(root, "B", "Two")
            output = root / "_All"

            with mock.patch.object(
                MODULE.os,
                "symlink",
                side_effect=[None, OSError("simulated failure")],
            ):
                result, _, stderr = self.run_main(
                    "--root", str(root), "--output", str(output)
                )

            self.assertEqual(result, 1)
            self.assertIn("simulated failure", stderr)
            self.assertFalse(output.exists())

    def test_interruption_rolls_back_new_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "Library"
            self.make_item(root, "A", "One")
            output = root / "_All"

            with mock.patch.object(MODULE.os, "symlink", side_effect=KeyboardInterrupt):
                result, _, stderr = self.run_main(
                    "--root", str(root), "--output", str(output)
                )

            self.assertEqual(result, 130)
            self.assertIn("rolled back", stderr)
            self.assertFalse(output.exists())

    def test_source_symbolic_links_are_ignored_when_supported(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "Library"
            real_item = self.make_item(root, "Real Group", "Real Item")
            linked_group = root / "Linked Group"
            linked_item = root / "Real Group" / "Linked Item"

            try:
                os.symlink(root / "Real Group", linked_group, target_is_directory=True)
                os.symlink(real_item, linked_item, target_is_directory=True)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symbolic links are unavailable: {error}")

            output = root / "_All"
            result, stdout, stderr = self.run_main(
                "--root", str(root), "--output", str(output), "--dry-run"
            )

            self.assertEqual(result, 0)
            self.assertEqual(stderr, "")
            self.assertIn("would create 1 link(s)", stdout)
            self.assertIn("Real Group - Real Item", stdout)
            self.assertNotIn("Linked", stdout)

    def test_existing_root_used_as_output_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "Library"
            root.mkdir()

            result, stdout, stderr = self.run_main(
                "--root", str(root), "--output", str(root)
            )

            # An existing directory is intentionally checked before other validation.
            self.assertEqual(result, 0)
            self.assertIn("already exists", stdout)
            self.assertEqual(stderr, "")


if __name__ == "__main__":
    unittest.main()
