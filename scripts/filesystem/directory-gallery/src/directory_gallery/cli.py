"""Command-line entry point."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from typing import Optional, Sequence

from . import __version__
from .errors import UserError
from .output import prepare_output, resolve_paths
from .patterns import ExclusionRules, ExclusionSource, load_exclusion_patterns
from .renderer import build_site


def _inline_exclusion(value: str) -> ExclusionSource:
    return "pattern", value


def _exclusion_file(value: str) -> ExclusionSource:
    return "file", value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="directory-gallery",
        description=(
            "Generate a dark static HTML gallery from a "
            "CREATOR/PROJECT directory tree."
        ),
        epilog=(
            "Exclusions use Gitignore-style patterns relative to INPUT_FOLDER. "
            "Examples: --exclude '_*', --exclude 'Drafts/', "
            "--exclude '/Creator/Archive/', or --exclude-from .galleryignore. "
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
        dest="exclusion_sources",
        default=[],
        type=_inline_exclusion,
        metavar="PATTERN",
        help="Gitignore-style pattern for any input entry; repeat as needed",
    )
    parser.add_argument(
        "--exclude-from",
        action="append",
        dest="exclusion_sources",
        type=_exclusion_file,
        metavar="FILE",
        help="read ordered exclusion patterns from FILE; repeat as needed",
    )
    parser.add_argument(
        "--title",
        metavar="TEXT",
        help="page title; defaults to the input directory name",
    )
    parser.add_argument(
        "--no-creator-grid",
        action="store_false",
        dest="creator_grid",
        help="omit the additional creators.html portrait grid",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress progress reports while generating",
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def run(arguments: argparse.Namespace) -> int:
    patterns = load_exclusion_patterns(arguments.exclusion_sources)
    input_root, output = resolve_paths(arguments.input, arguments.output)
    exclusions = ExclusionRules(input_root, patterns)
    prepare_output(output)
    default_title = input_root.name or str(input_root)
    result = build_site(
        input_root,
        output,
        arguments.title or default_title,
        exclusions,
        creator_grid=arguments.creator_grid,
        quiet=arguments.quiet,
    )

    print(
        f"Generated {result.creator_count} creator(s) and "
        f"{result.project_count} project(s): {result.index}"
    )
    print(
        f"Media: {result.media_count}; previews: "
        f"{result.previews_generated} generated, {result.previews_reused} reused"
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
    except sqlite3.Error as error:
        print(f"directory-gallery: cache database error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("directory-gallery: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
