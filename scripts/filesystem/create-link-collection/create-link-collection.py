#!/usr/bin/env python3
"""Create a flat collection of relative links from a ROOT/GROUP/ITEM tree."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional, Sequence, Tuple


MARKER_NAME = ".link-collection"
MARKER_FORMAT = 1
TOOL_NAME = "create-link-collection.py"
TOOL_VERSION = "1.0"


class UserError(Exception):
    """An expected error that should be reported without a traceback."""


class LinkPlan(NamedTuple):
    group_name: str
    item_name: str
    source: Path
    link: Path
    relative_target: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a flat directory of relative symbolic links from directories "
            "arranged as ROOT/GROUP/ITEM."
        ),
        epilog=(
            "Exclusion patterns use '/' between GROUP and ITEM on every platform. "
            "A pattern without '/' matches ITEM names only. Examples: "
            "--exclude '_misc', --exclude 'Nia Solen/Static Garden', "
            "--exclude 'Nia Solen/*'."
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "--root",
        required=True,
        metavar="PATH",
        help="root of the GROUP/ITEM hierarchy",
    )
    parser.add_argument(
        "--output",
        required=True,
        metavar="PATH",
        help="new directory in which to create the links",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="exclude one ITEM or GROUP/ITEM pattern; repeat for multiple patterns",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show the links that would be created without changing the filesystem",
    )
    return parser


def normalize_path(value: str) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def path_exists(path: Path) -> bool:
    """Return True for every existing directory entry, including broken links."""

    return os.path.lexists(os.fspath(path))


def validate_exclusions(patterns: Sequence[str]) -> None:
    for pattern in patterns:
        if not pattern:
            raise UserError("exclusion patterns must not be empty")
        if "\\" in pattern:
            raise UserError(
                f"invalid exclusion pattern {pattern!r}: use '/' as the separator"
            )
        if "**" in pattern:
            raise UserError(
                f"invalid exclusion pattern {pattern!r}: '**' is not supported"
            )

        parts = pattern.split("/")
        if len(parts) > 2 or any(not part for part in parts):
            raise UserError(
                f"invalid exclusion pattern {pattern!r}: use ITEM or GROUP/ITEM"
            )


def matches_exclusion(group_name: str, item_name: str, patterns: Sequence[str]) -> bool:
    for pattern in patterns:
        if "/" not in pattern:
            if fnmatch.fnmatchcase(item_name, pattern):
                return True
            continue

        group_pattern, item_pattern = pattern.split("/", 1)
        if fnmatch.fnmatchcase(group_name, group_pattern) and fnmatch.fnmatchcase(
            item_name, item_pattern
        ):
            return True

    return False


def is_generated_collection(path: Path) -> bool:
    return (path / MARKER_NAME).is_file()


def sorted_entries(path: Path) -> List[Path]:
    return sorted(path.iterdir(), key=lambda entry: (entry.name.casefold(), entry.name))


def discover_items(
    root: Path, output: Path, exclusions: Sequence[str]
) -> List[Tuple[str, str, Path]]:
    items: List[Tuple[str, str, Path]] = []

    for group in sorted_entries(root):
        if group.is_symlink() or not group.is_dir():
            continue
        if group == output or is_generated_collection(group):
            continue

        for item in sorted_entries(group):
            if item.is_symlink() or not item.is_dir():
                continue
            if item == output or is_generated_collection(item):
                continue
            if matches_exclusion(group.name, item.name, exclusions):
                continue
            items.append((group.name, item.name, item))

    return items


def validate_windows_link_name(name: str) -> None:
    invalid_characters = '<>:"/\\|?*'
    if any(ord(character) < 32 or character in invalid_characters for character in name):
        raise UserError(f"generated link name is invalid on Windows: {name!r}")
    if name.endswith((" ", ".")):
        raise UserError(f"generated link name is invalid on Windows: {name!r}")

    base_name = name.split(".", 1)[0].upper()
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update(f"COM{number}" for number in range(1, 10))
    reserved.update(f"LPT{number}" for number in range(1, 10))
    if base_name in reserved:
        raise UserError(f"generated link name is reserved on Windows: {name!r}")

    utf16_units = len(name.encode("utf-16-le")) // 2
    if utf16_units > 255:
        raise UserError(f"generated link name is too long on Windows: {name!r}")


def validate_posix_link_name(name: str, root: Path) -> None:
    try:
        name_limit = os.pathconf(os.fspath(root), "PC_NAME_MAX")
    except (AttributeError, OSError, ValueError):
        name_limit = 255

    if len(os.fsencode(name)) > name_limit:
        raise UserError(
            f"generated link name exceeds the filesystem limit of {name_limit} bytes: "
            f"{name!r}"
        )


def validate_link_name(name: str, root: Path) -> None:
    if not name or name in {".", ".."} or "/" in name or "\0" in name:
        raise UserError(f"generated link name is invalid: {name!r}")

    if os.name == "nt":
        validate_windows_link_name(name)
    else:
        validate_posix_link_name(name, root)


def collision_key(name: str) -> str:
    if os.name == "nt":
        return name.casefold()
    return name


def build_link_plan(
    root: Path, output: Path, items: Sequence[Tuple[str, str, Path]]
) -> List[LinkPlan]:
    plans: List[LinkPlan] = []
    names = {}

    for group_name, item_name, source in items:
        link_name = f"{group_name} - {item_name}"
        validate_link_name(link_name, root)

        key = collision_key(link_name)
        if key in names:
            raise UserError(
                f"generated link-name collision: {names[key]} and {source} "
                f"both map to {link_name!r}"
            )
        names[key] = source

        try:
            relative_target = os.path.relpath(source, start=output)
        except ValueError as error:
            raise UserError(
                f"cannot create a relative link from {output} to {source}: {error}"
            ) from error

        plans.append(
            LinkPlan(
                group_name=group_name,
                item_name=item_name,
                source=source,
                link=output / link_name,
                relative_target=relative_target,
            )
        )

    return plans


def validate_paths(root: Path, output: Path) -> None:
    if not root.exists():
        raise UserError(f"root does not exist: {root}")
    if not root.is_dir():
        raise UserError(f"root is not a directory: {root}")
    if root == output:
        raise UserError("root and output must be different directories")

    if os.name == "nt" and root.drive.casefold() != output.drive.casefold():
        raise UserError(
            "root and output must be on the same Windows drive for relative links"
        )

    try:
        next(root.iterdir(), None)
    except OSError as error:
        raise UserError(f"root is not readable: {root}: {error}") from error


def print_plan(output: Path, plans: Sequence[LinkPlan]) -> None:
    print(f"Dry run: would create {len(plans)} link(s) in {output}")
    for plan in plans:
        print(f"  {plan.link.name} -> {plan.relative_target}")
    print(f"  {MARKER_NAME} (collection marker)")


def marker_contents(root: Path) -> str:
    marker = {
        "format": MARKER_FORMAT,
        "generator": TOOL_NAME,
        "root": os.fspath(root),
        "version": TOOL_VERSION,
    }
    return json.dumps(marker, indent=2, sort_keys=True) + "\n"


def rollback_output(output: Path, attempted_links: Sequence[Path]) -> Optional[str]:
    errors = []

    for link in reversed(attempted_links):
        try:
            if path_exists(link):
                link.unlink()
        except OSError as error:
            errors.append(f"could not remove {link}: {error}")

    marker = output / MARKER_NAME
    try:
        if path_exists(marker):
            marker.unlink()
    except OSError as error:
        errors.append(f"could not remove {marker}: {error}")

    try:
        if output.exists():
            output.rmdir()
    except OSError as error:
        errors.append(f"could not remove {output}: {error}")

    return "; ".join(errors) if errors else None


def create_collection(root: Path, output: Path, plans: Sequence[LinkPlan]) -> int:
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise UserError(
            f"could not create output parent {output.parent}: {error}"
        ) from error

    attempted_links: List[Path] = []
    output_created = False
    try:
        try:
            output.mkdir()
            output_created = True
        except FileExistsError:
            if output.is_dir():
                print(f"Output directory already exists; nothing was changed: {output}")
                return 0
            raise UserError(f"output path exists and is not a directory: {output}")
        except OSError as error:
            raise UserError(
                f"could not create output directory {output}: {error}"
            ) from error

        for plan in plans:
            attempted_links.append(plan.link)
            os.symlink(
                plan.relative_target,
                plan.link,
                target_is_directory=True,
            )

        (output / MARKER_NAME).write_text(marker_contents(root), encoding="utf-8")
        print(f"Created {len(plans)} link(s) in {output}")
        return 0
    except KeyboardInterrupt:
        if output_created:
            cleanup_error = rollback_output(output, attempted_links)
            if cleanup_error:
                print(f"Cleanup warning: {cleanup_error}", file=sys.stderr)
        raise
    except OSError as error:
        cleanup_error = rollback_output(output, attempted_links) if output_created else None

        message = f"could not create link collection: {error}"
        if cleanup_error:
            message += f"; cleanup was incomplete: {cleanup_error}"
        raise UserError(message) from error


def run(arguments: argparse.Namespace) -> int:
    root = normalize_path(arguments.root)
    output = normalize_path(arguments.output)

    if path_exists(output):
        if output.is_dir():
            print(f"Output directory already exists; nothing was changed: {output}")
            return 0
        raise UserError(f"output path exists and is not a directory: {output}")

    validate_exclusions(arguments.exclude)
    validate_paths(root, output)

    try:
        items = discover_items(root, output, arguments.exclude)
    except OSError as error:
        raise UserError(f"could not scan root hierarchy: {error}") from error

    if not items:
        print("No eligible items were found; the output directory was not created.")
        return 0

    plans = build_link_plan(root, output, items)

    if arguments.dry_run:
        print_plan(output, plans)
        return 0

    return create_collection(root, output, plans)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)

    try:
        return run(arguments)
    except UserError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted; changes from this run were rolled back.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
