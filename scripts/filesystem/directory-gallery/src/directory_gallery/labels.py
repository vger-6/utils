"""Display terminology for generated pages."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntityLabels:
    singular: str
    plural: str

    @property
    def heading(self) -> str:
        return self.plural[:1].upper() + self.plural[1:]

    @property
    def detail_heading(self) -> str:
        return self.singular[:1].upper() + self.singular[1:]

    def noun(self, value: int) -> str:
        return self.singular if value == 1 else self.plural

    def count(self, value: int) -> str:
        return f"{value} {self.noun(value)}"


@dataclass(frozen=True)
class DisplayLabels:
    creator: EntityLabels
    project: EntityLabels


DEFAULT_DOMAIN = "generic"
DOMAIN_PRESETS = {
    "generic": DisplayLabels(
        creator=EntityLabels("creator", "creators"),
        project=EntityLabels("project", "projects"),
    ),
    "book": DisplayLabels(
        creator=EntityLabels("author", "authors"),
        project=EntityLabels("book", "books"),
    ),
    "film": DisplayLabels(
        creator=EntityLabels("director", "directors"),
        project=EntityLabels("movie", "movies"),
    ),
    "music": DisplayLabels(
        creator=EntityLabels("artist", "artists"),
        project=EntityLabels("album", "albums"),
    ),
    "model": DisplayLabels(
        creator=EntityLabels("model", "models"),
        project=EntityLabels("scene", "scenes"),
    ),
}
