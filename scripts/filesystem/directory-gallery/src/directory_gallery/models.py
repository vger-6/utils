"""Domain-neutral catalog models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


MEDIA_KINDS = ("image", "pdf", "video", "audio")


@dataclass(frozen=True)
class CatalogWarning:
    code: str
    message: str


@dataclass(frozen=True)
class MediaItem:
    name: str
    path: Path
    kind: str
    poster: Optional[Path] = None


@dataclass(frozen=True)
class MediaGroup:
    kind: str
    directory: Optional[Path]
    items: Tuple[MediaItem, ...]


@dataclass(frozen=True)
class Project:
    name: str
    path: Path
    cover: Optional[Path]
    readme: Optional[Path]
    media: Tuple[MediaGroup, ...]


@dataclass(frozen=True)
class Creator:
    name: str
    path: Path
    portrait: Optional[Path]
    readme: Optional[Path]
    projects: Tuple[Project, ...]
    media: Tuple[MediaGroup, ...]


@dataclass(frozen=True)
class Catalog:
    root: Path
    creators: Tuple[Creator, ...]
    warnings: Tuple[CatalogWarning, ...]

    @property
    def project_count(self) -> int:
        return sum(len(creator.projects) for creator in self.creators)
