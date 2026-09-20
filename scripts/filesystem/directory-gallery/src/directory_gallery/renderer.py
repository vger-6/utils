"""Render a catalog and its cached artwork as a static site."""

from __future__ import annotations

import hashlib
import html
import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from string import Template
from typing import Dict, List, Optional
from urllib.parse import quote

from .models import Catalog, CatalogWarning, Creator, Project
from .output import write_text_atomic
from .thumbnails import ThumbnailCache


@dataclass(frozen=True)
class BuildResult:
    creator_count: int
    project_count: int
    warning_count: int
    index: Path


def _resource_text(name: str) -> str:
    return (
        resources.files("directory_gallery")
        .joinpath("resources", name)
        .read_text(encoding="utf-8")
    )


def _directory_href(path: Path, output: Path) -> str:
    try:
        relative = os.path.relpath(path, start=output)
        href = quote(relative.replace(os.sep, "/"), safe="/")
    except ValueError:
        href = path.as_uri()
    return href if href.endswith("/") else f"{href}/"


def _anchor_id(path: Path) -> str:
    digest = hashlib.sha256(os.fsencode(path)).hexdigest()[:12]
    return f"creator-{digest}"


def _initial(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        return "#"
    first = stripped[0].upper()
    return first if first.isalnum() else "#"


def _placeholder(kind: str, name: str) -> str:
    initial = next((character.upper() for character in name if character.isalnum()), "?")
    return (
        f'<div class="image-placeholder {kind}-placeholder" aria-hidden="true">'
        f"<span>{html.escape(initial)}</span></div>"
    )


def _image_or_placeholder(
    thumbnail: Optional[str], kind: str, name: str, alt: str
) -> str:
    if thumbnail is None:
        return _placeholder(kind, name)
    return (
        f'<img class="{kind}-image" src="{html.escape(thumbnail, quote=True)}" '
        f'alt="{html.escape(alt, quote=True)}" loading="lazy" decoding="async">'
    )


def _project_markup(
    project: Project, output: Path, thumbnail: Optional[str]
) -> str:
    name = html.escape(project.name)
    href = html.escape(_directory_href(project.path, output), quote=True)
    artwork = _image_or_placeholder(
        thumbnail,
        "cover",
        project.name,
        f"Cover for {project.name}",
    )
    return (
        f'<a class="project-card" data-project-name="{html.escape(project.name, quote=True)}" '
        f'href="{href}" title="Open directory: {html.escape(project.name, quote=True)}">'
        f'<span class="cover-frame">{artwork}</span>'
        f'<span class="project-title">{name}</span>'
        "</a>"
    )


def _creator_markup(
    creator: Creator,
    output: Path,
    portrait: Optional[str],
    covers: Dict[Path, Optional[str]],
) -> str:
    creator_name = html.escape(creator.name)
    href = html.escape(_directory_href(creator.path, output), quote=True)
    artwork = _image_or_placeholder(
        portrait,
        "portrait",
        creator.name,
        f"Portrait of {creator.name}",
    )
    projects = "\n".join(
        _project_markup(project, output, covers[project.path])
        for project in creator.projects
    )
    count = len(creator.projects)
    count_label = f"{count} project" if count == 1 else f"{count} projects"
    return f"""
<section class="creator-section" id="{_anchor_id(creator.path)}"
         data-creator-name="{html.escape(creator.name, quote=True)}">
  <header class="creator-header">
    <a class="creator-identity" href="{href}"
       title="Open directory: {html.escape(creator.name, quote=True)}">
      <span class="portrait-frame">{artwork}</span>
      <span class="creator-copy">
        <span class="creator-name">{creator_name}</span>
        <span class="creator-project-count">{count_label}</span>
      </span>
    </a>
  </header>
  <div class="project-grid">{projects}</div>
</section>""".strip()


def _alphabet_markup(creators: Catalog) -> str:
    first_for_initial: Dict[str, Creator] = {}
    for creator in creators.creators:
        first_for_initial.setdefault(_initial(creator.name), creator)

    if not first_for_initial:
        return ""

    links = []
    for initial, creator in sorted(
        first_for_initial.items(), key=lambda item: (item[0] == "#", item[0].casefold())
    ):
        links.append(
            f'<a href="#{_anchor_id(creator.path)}" '
            f'aria-label="Jump to creators beginning with {html.escape(initial, quote=True)}">'
            f"{html.escape(initial)}</a>"
        )
    return '<nav class="alphabet" aria-label="Creator index">' + "".join(links) + "</nav>"


def _warnings_markup(warnings: List[CatalogWarning]) -> str:
    if not warnings:
        return ""
    entries = "".join(
        f'<li data-warning-code="{html.escape(warning.code, quote=True)}">'
        f"{html.escape(warning.message)}</li>"
        for warning in warnings
    )
    count = len(warnings)
    label = f"{count} catalog notice" if count == 1 else f"{count} catalog notices"
    return (
        '<details class="warnings">'
        f"<summary>{label}</summary>"
        f"<ul>{entries}</ul>"
        "</details>"
    )


def build_site(catalog: Catalog, output: Path, title: str) -> BuildResult:
    warnings = list(catalog.warnings)
    cache = ThumbnailCache(output, warnings)
    portraits: Dict[Path, Optional[str]] = {}
    covers: Dict[Path, Optional[str]] = {}

    for creator in catalog.creators:
        portraits[creator.path] = (
            cache.thumbnail_for(creator.portrait) if creator.portrait else None
        )
        for project in creator.projects:
            covers[project.path] = (
                cache.thumbnail_for(project.cover) if project.cover else None
            )

    cache.finish(catalog.root)

    creator_markup = "\n".join(
        _creator_markup(creator, output, portraits[creator.path], covers)
        for creator in catalog.creators
    )
    if not creator_markup:
        creator_markup = (
            '<p class="empty-state">No projects were found in this directory.</p>'
        )

    creator_count = len(catalog.creators)
    project_count = catalog.project_count
    summary = (
        f'<span id="visible-creators">{creator_count}</span> '
        f'<span id="creator-label">'
        f'{"creator" if creator_count == 1 else "creators"}</span> · '
        f'<span id="visible-projects">{project_count}</span> '
        f'<span id="project-label">'
        f'{"project" if project_count == 1 else "projects"}</span>'
    )

    template = Template(_resource_text("index.html"))
    document = template.substitute(
        title=html.escape(title),
        title_attribute=html.escape(title, quote=True),
        summary=summary,
        alphabet=_alphabet_markup(catalog),
        creators=creator_markup,
        warnings=_warnings_markup(warnings),
    )

    write_text_atomic(output / "assets" / "directory-gallery.css", _resource_text("gallery.css"))
    write_text_atomic(output / "assets" / "directory-gallery.js", _resource_text("gallery.js"))
    index = output / "index.html"
    write_text_atomic(index, document)

    return BuildResult(
        creator_count=creator_count,
        project_count=project_count,
        warning_count=len(warnings),
        index=index,
    )
