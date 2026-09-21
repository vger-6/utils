"""Discover creators, projects, conventional artwork, and allowed media."""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import DefaultDict, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .errors import UserError
from .models import Catalog, CatalogWarning, Creator, MediaGroup, MediaItem, Project
from .patterns import ExclusionRules


ARTWORK_EXTENSIONS = ("jpg", "jpeg", "png")
CREATOR_CONTENT_DIRECTORY = "meta"
README_NAME = "README.md"
MEDIA_EXTENSIONS: Dict[str, Set[str]] = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"},
    "pdf": {".pdf"},
    "video": {".mp4", ".m4v", ".webm", ".ogv", ".mov", ".mkv"},
    "audio": {
        ".mp3",
        ".m4a",
        ".aac",
        ".ogg",
        ".oga",
        ".opus",
        ".wav",
        ".flac",
    },
}
MEDIA_KIND_ORDER = {kind: index for index, kind in enumerate(MEDIA_EXTENSIONS)}


def _name_key(path: Path) -> Tuple[str, str]:
    return path.name.casefold(), path.name


def _relative_key(path: Path) -> Tuple[Tuple[str, str], ...]:
    return tuple((part.casefold(), part) for part in path.parts)


def _visible_real_directory(path: Path) -> bool:
    try:
        return (
            not path.name.startswith(".")
            and not path.is_symlink()
            and path.is_dir()
        )
    except OSError:
        return False


def _visible_real_file(path: Path) -> bool:
    try:
        return (
            not path.name.startswith(".")
            and not path.is_symlink()
            and path.is_file()
        )
    except OSError:
        return False


def _entries(path: Path) -> List[Path]:
    try:
        return sorted(path.iterdir(), key=_name_key)
    except OSError as error:
        raise UserError(f"could not read directory {path}: {error}") from error


def _directories(path: Path, exclusions: ExclusionRules) -> List[Path]:
    return [
        entry
        for entry in _entries(path)
        if _visible_real_directory(entry)
        and not exclusions.excludes(entry, directory=True)
    ]


def _walk_directories(root: Path, exclusions: ExclusionRules) -> List[Path]:
    """Return visible real directories breadth-first, including ``root``."""

    discovered = [root]
    pending = deque([root])
    while pending:
        directory = pending.popleft()
        children = _directories(directory, exclusions)
        discovered.extend(children)
        pending.extend(children)
    return discovered


def _role_candidates(
    directory: Path, stem: str, exclusions: ExclusionRules
) -> List[Path]:
    return [
        directory / f"{stem}.{extension}"
        for extension in ARTWORK_EXTENSIONS
        if _visible_real_file(directory / f"{stem}.{extension}")
        and not exclusions.excludes(
            directory / f"{stem}.{extension}", directory=False
        )
    ]


def _select_direct_artwork(
    directory: Path,
    stem: str,
    subject: str,
    warnings: List[CatalogWarning],
    exclusions: ExclusionRules,
) -> Optional[Path]:
    candidates = _role_candidates(directory, stem, exclusions)
    if not candidates:
        warnings.append(
            CatalogWarning(f"missing-{stem}", f"No {stem} image: {subject}")
        )
        return None

    if len(candidates) > 1:
        warnings.append(
            CatalogWarning(
                f"multiple-{stem}s",
                f"Multiple {stem} images for {subject}; using "
                f"{candidates[0].name} ({len(candidates) - 1} alternative(s))",
            )
        )
    return candidates[0]


def _select_project_cover(
    project: Path,
    subject: str,
    warnings: List[CatalogWarning],
    exclusions: ExclusionRules,
) -> Tuple[Optional[Path], Set[Path]]:
    direct = _role_candidates(project, "cover", exclusions)
    if direct:
        candidates = direct
    else:
        candidates = []
        for directory in _walk_directories(project, exclusions)[1:]:
            candidates.extend(_role_candidates(directory, "cover", exclusions))

    reserved = set(candidates)
    if not candidates:
        warnings.append(CatalogWarning("missing-cover", f"No cover image: {subject}"))
        return None, reserved

    chosen = candidates[0]
    if len(candidates) > 1:
        chosen_relative = chosen.relative_to(project)
        warnings.append(
            CatalogWarning(
                "multiple-covers",
                f"Multiple cover images for {subject}; using {chosen_relative} "
                f"({len(candidates) - 1} alternative(s))",
            )
        )
    return chosen, reserved


def _media_kind(path: Path) -> Optional[str]:
    extension = path.suffix.casefold()
    for kind, extensions in MEDIA_EXTENSIONS.items():
        if extension in extensions:
            return kind
    return None


def _poster_for(video: Path, exclusions: ExclusionRules) -> Optional[Path]:
    for extension in ARTWORK_EXTENSIONS:
        candidate = video.with_name(f"{video.stem}.poster.{extension}")
        if _visible_real_file(candidate) and not exclusions.excludes(
            candidate, directory=False
        ):
            return candidate
    return None


def _iter_media_files(
    root: Path, recursive: bool, exclusions: ExclusionRules
) -> Iterable[Tuple[Path, Path]]:
    directories = _walk_directories(root, exclusions) if recursive else [root]
    for directory in directories:
        relative = directory.relative_to(root)
        for entry in _entries(directory):
            if _visible_real_file(entry) and not exclusions.excludes(
                entry, directory=False
            ):
                yield relative, entry


def _group_media(
    sources: Iterable[Tuple[Optional[Path], Path]],
    reserved: Set[Path],
    exclusions: ExclusionRules,
) -> Tuple[MediaGroup, ...]:
    discovered = list(sources)
    posters = {
        poster
        for _, path in discovered
        if _media_kind(path) == "video"
        for poster in [_poster_for(path, exclusions)]
        if poster is not None
    }
    grouped: DefaultDict[Tuple[str, Optional[Path]], List[MediaItem]] = defaultdict(list)

    for relative_directory, path in discovered:
        if path in reserved or path in posters:
            continue
        kind = _media_kind(path)
        if kind is None:
            continue
        grouped[(kind, relative_directory)].append(
            MediaItem(
                name=path.name,
                path=path,
                kind=kind,
                poster=_poster_for(path, exclusions) if kind == "video" else None,
            )
        )

    def group_key(item: Tuple[str, Optional[Path]]) -> Tuple[object, ...]:
        kind, directory = item
        directory_key: Tuple[object, ...]
        if directory is None or directory == Path("."):
            directory_key = (0,)
        else:
            directory_key = (1, _relative_key(directory))
        return MEDIA_KIND_ORDER[kind], *directory_key

    groups = []
    for kind, directory in sorted(grouped, key=group_key):
        normalized_directory = None if directory in {None, Path(".")} else directory
        items = tuple(
            sorted(grouped[(kind, directory)], key=lambda item: _name_key(item.path))
        )
        groups.append(MediaGroup(kind, normalized_directory, items))
    return tuple(groups)


def _creator_media(
    creator: Path, portrait_files: Set[Path], exclusions: ExclusionRules
) -> Tuple[MediaGroup, ...]:
    sources: List[Tuple[Optional[Path], Path]] = []
    for _, path in _iter_media_files(creator, recursive=False, exclusions=exclusions):
        sources.append((None, path))

    meta = creator / CREATOR_CONTENT_DIRECTORY
    if _visible_real_directory(meta) and not exclusions.excludes(
        meta, directory=True
    ):
        for relative, path in _iter_media_files(
            meta, recursive=True, exclusions=exclusions
        ):
            sources.append((None if relative == Path(".") else relative, path))

    return _group_media(sources, portrait_files, exclusions)


def _project_media(
    project: Path, cover_files: Set[Path], exclusions: ExclusionRules
) -> Tuple[MediaGroup, ...]:
    sources = (
        (None if relative == Path(".") else relative, path)
        for relative, path in _iter_media_files(
            project, recursive=True, exclusions=exclusions
        )
    )
    return _group_media(sources, cover_files, exclusions)


def _readme(directory: Path, exclusions: ExclusionRules) -> Optional[Path]:
    candidate = directory / README_NAME
    return (
        candidate
        if _visible_real_file(candidate)
        and not exclusions.excludes(candidate, directory=False)
        else None
    )


def creator_paths(root: Path, exclusions: ExclusionRules) -> List[Path]:
    """Return eligible creator directories in deterministic order."""

    return _directories(root, exclusions)


def project_paths(creator: Path, exclusions: ExclusionRules) -> List[Path]:
    """Return eligible project directories for one creator."""

    return [
        path
        for path in _directories(creator, exclusions)
        if path.name != CREATOR_CONTENT_DIRECTORY
    ]


def scan_project(
    creator_name: str,
    project_path: Path,
    warnings: List[CatalogWarning],
    exclusions: ExclusionRules,
) -> Project:
    """Scan one project and keep only that project's media in memory."""

    subject = f"{creator_name} / {project_path.name}"
    cover, cover_files = _select_project_cover(
        project_path, subject, warnings, exclusions
    )
    return Project(
        name=project_path.name,
        path=project_path,
        cover=cover,
        readme=_readme(project_path, exclusions),
        media=_project_media(project_path, cover_files, exclusions),
    )


def scan_creator(
    creator_path: Path,
    warnings: List[CatalogWarning],
    exclusions: ExclusionRules,
    projects: Sequence[Project] = (),
) -> Creator:
    """Scan creator-level metadata and media without entering projects."""

    portrait_files = set(_role_candidates(creator_path, "portrait", exclusions))
    portrait = _select_direct_artwork(
        creator_path, "portrait", creator_path.name, warnings, exclusions
    )
    return Creator(
        name=creator_path.name,
        path=creator_path,
        portrait=portrait,
        readme=_readme(creator_path, exclusions),
        projects=tuple(projects),
        media=_creator_media(creator_path, portrait_files, exclusions),
    )


def scan_catalog(root: Path, patterns: Sequence[str]) -> Catalog:
    """Build an in-memory catalog for small callers and focused tests."""

    warnings: List[CatalogWarning] = []
    creators: List[Creator] = []
    exclusions = ExclusionRules(root, patterns)
    for creator_path in creator_paths(root, exclusions):
        projects = [
            scan_project(creator_path.name, project_path, warnings, exclusions)
            for project_path in project_paths(creator_path, exclusions)
        ]
        creators.append(scan_creator(creator_path, warnings, exclusions, projects))

    return Catalog(root=root, creators=tuple(creators), warnings=tuple(warnings))
