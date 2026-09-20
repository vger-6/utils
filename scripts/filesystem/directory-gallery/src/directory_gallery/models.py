"""Domain-neutral catalog models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


@dataclass(frozen=True)
class CatalogWarning:
    code: str
    message: str


@dataclass(frozen=True)
class Project:
    name: str
    path: Path
    cover: Optional[Path]


@dataclass(frozen=True)
class Creator:
    name: str
    path: Path
    portrait: Optional[Path]
    projects: Tuple[Project, ...]


@dataclass(frozen=True)
class Catalog:
    root: Path
    creators: Tuple[Creator, ...]
    warnings: Tuple[CatalogWarning, ...]

    @property
    def project_count(self) -> int:
        return sum(len(creator.projects) for creator in self.creators)
