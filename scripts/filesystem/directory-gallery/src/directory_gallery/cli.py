"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from . import __version__
from .errors import UserError
from .output import prepare_output, resolve_paths
from .patterns import validate_exclusions
from .renderer import build_site
from .scanner import scan_catalog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="directory-gallery",
        description=(
            "Generate a dark static HTML gallery from a "
            "CREATOR/PROJECT directory tree."
        ),
        epilog=(
            "--exclude is repeatable. Patterns use '/' between creator and "
            "project on every platform; examples: --exclude Drafts, "
            "--exclude 'Creator/Archive', --exclude 'Creator/*'. "
            "The exact creator child directory 'meta' is reserved and is "
            "never treated as a project."
        ),
        allow_abbrev=False,
    )
    parser.add_argument("input", metavar="INPUT_FOLDER")
    parser.add_argument("output", metavar="OUTPUT_FOLDER")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="exclude a PROJECT or CREATOR/PROJECT pattern; repeat as needed",
    )
    parser.add_argument(
        "--title",
        metavar="TEXT",
        help="page title; defaults to the input directory name",
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def run(arguments: argparse.Namespace) -> int:
    validate_exclusions(arguments.exclude)
    input_root, output = resolve_paths(arguments.input, arguments.output)
    catalog = scan_catalog(input_root, arguments.exclude)
    prepare_output(output)
    default_title = input_root.name or str(input_root)
    result = build_site(catalog, output, arguments.title or default_title)

    print(
        f"Generated {result.creator_count} creator(s) and "
        f"{result.project_count} project(s): {result.index}"
    )
    if result.warning_count:
        print(f"Catalog notices: {result.warning_count}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    try:
        return run(parser.parse_args(argv))
    except UserError as error:
        print(f"directory-gallery: error: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"directory-gallery: filesystem error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("directory-gallery: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
