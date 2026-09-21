"""Gitignore-style exclusions relative to the input collection."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from pathspec import GitIgnoreSpec

from .errors import UserError


ExclusionSource = Tuple[str, str]


def load_exclusion_patterns(sources: Sequence[ExclusionSource]) -> List[str]:
    """Expand inline patterns and pattern files in command-line order."""

    patterns: List[str] = []
    for kind, value in sources:
        if kind == "pattern":
            if not value or "\n" in value or "\r" in value:
                raise UserError("--exclude requires one nonempty pattern")
            patterns.append(value)
        elif kind == "file":
            file = Path(value).expanduser()
            try:
                contents = file.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as error:
                raise UserError(
                    f"could not read exclusion file {file}: {error}"
                ) from error
            patterns.extend(contents.splitlines())
        else:
            raise ValueError(f"unknown exclusion source: {kind}")
    return patterns


class ExclusionRules:
    """Match input-relative paths while allowing traversal to prune directories."""

    def __init__(self, root: Path, patterns: Sequence[str]) -> None:
        self.root = root
        try:
            self._spec: Optional[GitIgnoreSpec] = (
                GitIgnoreSpec.from_lines(patterns) if patterns else None
            )
        except ValueError as error:
            raise UserError(f"invalid exclusion pattern: {error}") from error

    def excludes(self, path: Path, *, directory: bool) -> bool:
        if self._spec is None:
            return False
        relative = path.relative_to(self.root)
        if relative == Path("."):
            return False
        name = relative.as_posix() + ("/" if directory else "")
        return self._spec.match_file(name)

    def excludes_file_or_parent(self, path: Path) -> bool:
        """Prevent README links from reviving files below excluded directories."""

        if self._spec is None:
            return False
        relative = path.relative_to(self.root)
        current = self.root
        for part in relative.parts[:-1]:
            current /= part
            if self.excludes(current, directory=True):
                return True
        return self.excludes(path, directory=False)
