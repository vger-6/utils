"""Discover creators, projects, and their conventional artwork."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .errors import UserError
from .models import Catalog, CatalogWarning, Creator, Project
from .patterns import matches_exclusion


IMAGE_EXTENSIONS = ("jpg", "jpeg", "png")


def _sort_key(path: Path) -> Tuple[str, str]:
    return path.name.casefold(), path.name


def _directories(path: Path) -> List[Path]:
    try:
        entries = path.iterdir()
        return sorted(
            (
                entry
                for entry in entries
                if not entry.name.startswith(".")
                and not entry.is_symlink()
                and entry.is_dir()
            ),
            key=_sort_key,
        )
    except OSError as error:
        raise UserError(f"could not read directory {path}: {error}") from error


def _select_artwork(
    directory: Path,
    stem: str,
    subject: str,
    warnings: List[CatalogWarning],
) -> Optional[Path]:
    candidates = [
        directory / f"{stem}.{extension}"
        for extension in IMAGE_EXTENSIONS
        if (directory / f"{stem}.{extension}").is_file()
    ]

    if not candidates:
        warnings.append(
            CatalogWarning(
                f"missing-{stem}",
                f"No {stem} image: {subject}",
            )
        )
        return None

    if len(candidates) > 1:
        names = ", ".join(candidate.name for candidate in candidates)
        warnings.append(
            CatalogWarning(
                f"multiple-{stem}s",
                f"Multiple {stem} images for {subject}; using "
                f"{candidates[0].name}: {names}",
            )
        )

    return candidates[0]


def scan_catalog(root: Path, exclusions: Sequence[str]) -> Catalog:
    warnings: List[CatalogWarning] = []
    creators: List[Creator] = []

    for creator_path in _directories(root):
        projects: List[Project] = []
        for project_path in _directories(creator_path):
            if matches_exclusion(creator_path.name, project_path.name, exclusions):
                continue

            subject = f"{creator_path.name} / {project_path.name}"
            cover = _select_artwork(project_path, "cover", subject, warnings)
            projects.append(Project(project_path.name, project_path, cover))

        if not projects:
            continue

        portrait = _select_artwork(
            creator_path, "portrait", creator_path.name, warnings
        )
        creators.append(
            Creator(
                name=creator_path.name,
                path=creator_path,
                portrait=portrait,
                projects=tuple(projects),
            )
        )

    return Catalog(root=root, creators=tuple(creators), warnings=tuple(warnings))
