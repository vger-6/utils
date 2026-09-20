"""Validation and matching for repeatable project exclusions."""

from __future__ import annotations

import fnmatch
from typing import Sequence

from .errors import UserError


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

        components = pattern.split("/")
        if len(components) > 2 or any(not component for component in components):
            raise UserError(
                f"invalid exclusion pattern {pattern!r}: "
                "use PROJECT or CREATOR/PROJECT"
            )


def matches_exclusion(
    creator_name: str, project_name: str, patterns: Sequence[str]
) -> bool:
    for pattern in patterns:
        if "/" not in pattern:
            if fnmatch.fnmatchcase(project_name, pattern):
                return True
            continue

        creator_pattern, project_pattern = pattern.split("/", 1)
        if fnmatch.fnmatchcase(
            creator_name, creator_pattern
        ) and fnmatch.fnmatchcase(project_name, project_pattern):
            return True

    return False
