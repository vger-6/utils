"""Output-directory validation and atomic file writes."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Tuple

from .errors import UserError


MANIFEST_NAME = ".directory-gallery-manifest.json"
MANIFEST_FORMAT = 2
LEGACY_MANIFEST_FORMAT = 1
MANIFEST_GENERATOR = "directory-gallery"
DATABASE_NAME = ".directory-gallery-cache.sqlite3"


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_paths(input_value: str, output_value: str) -> Tuple[Path, Path]:
    try:
        input_root = Path(input_value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise UserError(f"input directory does not exist: {input_value}") from error

    if not input_root.is_dir():
        raise UserError(f"input is not a directory: {input_root}")

    output_candidate = Path(output_value).expanduser()
    if os.path.lexists(os.fspath(output_candidate)) and output_candidate.is_symlink():
        raise UserError(f"output must not be a symbolic link: {output_candidate}")
    output = output_candidate.resolve(strict=False)
    if input_root == output or _contains(input_root, output) or _contains(
        output, input_root
    ):
        raise UserError("input and output directory trees must not overlap")

    if os.path.lexists(os.fspath(output)):
        if not output.is_dir():
            raise UserError(f"output exists and is not a directory: {output}")

    return input_root, output


def prepare_output(output: Path) -> None:
    if output.exists():
        try:
            entries = list(output.iterdir())
        except OSError as error:
            raise UserError(f"could not read output directory {output}: {error}") from error

        if entries:
            manifest_path = output / MANIFEST_NAME
            if not manifest_path.is_file():
                raise UserError(
                    "output is not empty and has no Directory Gallery manifest: "
                    f"{output}"
                )
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError) as error:
                raise UserError(
                    f"output has an invalid Directory Gallery manifest: {error}"
                ) from error
            if (
                not isinstance(manifest, dict)
                or manifest.get("format")
                not in {LEGACY_MANIFEST_FORMAT, MANIFEST_FORMAT}
                or manifest.get("generator") != MANIFEST_GENERATOR
            ):
                raise UserError("output has an incompatible Directory Gallery manifest")
            if (
                manifest.get("format") == MANIFEST_FORMAT
                and (
                    not (output / DATABASE_NAME).is_file()
                    or (output / DATABASE_NAME).is_symlink()
                )
            ):
                raise UserError("output is missing its Directory Gallery cache database")
    else:
        try:
            output.mkdir(parents=True)
        except OSError as error:
            raise UserError(f"could not create output directory {output}: {error}") from error


def write_text_atomic(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(contents)
        os.replace(temporary_path, path)
    except BaseException:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise
