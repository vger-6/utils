"""Stream catalog discovery into scalable static pages."""

from __future__ import annotations

import hashlib
import html
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from string import Template
from typing import Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.parse import quote

from .collaborations import collaboration_members
from .labels import DisplayLabels
from .models import CatalogWarning, Creator, MediaGroup, MediaItem, Project
from .output import write_text_atomic
from .patterns import ExclusionRules
from .readme import render_readme
from .scanner import (
    creator_paths,
    creator_portrait_candidate,
    project_paths,
    scan_creator,
    scan_project,
)
from .state import CatalogState
from .thumbnails import ThumbnailCache


KIND_LABELS = {
    "image": "Images",
    "pdf": "PDFs",
    "video": "Videos",
    "audio": "Audio",
}
WARNING_SAMPLE_LIMIT = 200


class WarningLog(List[CatalogWarning]):
    """Count all notices while retaining only a bounded diagnostic sample."""

    def __init__(self, sample_limit: int = WARNING_SAMPLE_LIMIT) -> None:
        super().__init__()
        self.sample_limit = sample_limit
        self.total_count = 0

    def append(self, warning: CatalogWarning) -> None:
        self.total_count += 1
        if len(self) < self.sample_limit:
            super().append(warning)


@dataclass(frozen=True)
class ProjectSummary:
    name: str
    path: Path
    page: Path
    cover: Optional[str]
    credit: Optional[str] = None


@dataclass(frozen=True)
class MemberSummary:
    name: str
    page: Optional[Path]
    portrait: Optional[str]


@dataclass(frozen=True)
class BuildResult:
    creator_count: int
    project_count: int
    media_count: int
    warning_count: int
    previews_generated: int
    previews_reused: int
    index: Path


class ProgressReporter:
    def __init__(self, total_creators: int, enabled: bool) -> None:
        self.total_creators = total_creators
        self.enabled = enabled
        self.creators = 0
        self.projects = 0
        self.media = 0
        self.cache: Optional[ThumbnailCache] = None
        self.started = time.monotonic()
        self.last_report = self.started
        self.reported = False

    def attach_cache(self, cache: ThumbnailCache) -> None:
        self.cache = cache

    @staticmethod
    def _duration(seconds: float) -> str:
        rounded = max(0, int(seconds + 0.5))
        minutes, remainder = divmod(rounded, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h {minutes:02d}m"
        if minutes:
            return f"{minutes}m {remainder:02d}s"
        return f"{remainder}s"

    def update(self, force: bool = False) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        interval = 1.0 if sys.stderr.isatty() else 10.0
        if not force and now - self.last_report < interval:
            return
        if not force and self.total_creators < 25:
            return
        generated = self.cache.generated_count if self.cache else 0
        reused = self.cache.reused_count if self.cache else 0
        elapsed = now - self.started
        timing = f"elapsed {self._duration(elapsed)}"
        if self.creators and self.creators < self.total_creators:
            remaining = elapsed * (self.total_creators - self.creators) / self.creators
            timing += f", ETA {self._duration(remaining)}"
        message = (
            f"Processed {self.creators}/{self.total_creators} creators · "
            f"{self.projects} projects · {self.media} media · "
            f"previews {reused} reused, {generated} generated · {timing}"
        )
        if sys.stderr.isatty():
            print(f"\r{message}", end="", file=sys.stderr, flush=True)
        else:
            print(message, file=sys.stderr, flush=True)
        self.last_report = now
        self.reported = True

    def finish(self) -> None:
        if not self.enabled:
            return
        elapsed = time.monotonic() - self.started
        if self.reported or self.total_creators >= 25 or elapsed >= 2:
            self.update(force=True)
            if sys.stderr.isatty():
                print(file=sys.stderr)


def _resource_text(name: str) -> str:
    return (
        resources.files("directory_gallery")
        .joinpath("resources", name)
        .read_text(encoding="utf-8")
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(os.fsencode(path.resolve())).hexdigest()[:16]


def _creator_page(output: Path, creator_path: Path) -> Path:
    return output / "creators" / f"{_digest(creator_path)}.html"


def _project_page(output: Path, project_path: Path) -> Path:
    return output / "projects" / f"{_digest(project_path)}.html"


def _href(target: Path, page: Path) -> str:
    try:
        relative = os.path.relpath(target, start=page.parent)
        return quote(relative.replace(os.sep, "/"), safe="/")
    except ValueError:
        return target.as_uri()


def _asset_href(root_relative: str, output: Path, page: Path) -> str:
    return _href(output / root_relative, page)


def _initial(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        return "#"
    first = stripped[0].upper()
    return first if first.isalnum() else "#"


def _json_data(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def _placeholder(kind: str, name: str) -> str:
    initial = next((character.upper() for character in name if character.isalnum()), "?")
    return (
        f'<span class="image-placeholder {kind}-placeholder" aria-hidden="true">'
        f"<span>{html.escape(initial)}</span></span>"
    )


def _artwork(
    thumbnail: Optional[str],
    kind: str,
    name: str,
    alt: str,
    output: Path,
    page: Path,
) -> str:
    if thumbnail is None:
        return _placeholder(kind, name)
    source = html.escape(_asset_href(thumbnail, output, page), quote=True)
    return (
        f'<img class="{kind}-image" src="{source}" '
        f'alt="{html.escape(alt, quote=True)}" loading="lazy" decoding="async">'
    )


def _navigation(
    output: Path, page: Path, active: str, creator_grid: bool, labels: DisplayLabels
) -> str:
    index_href = html.escape(_href(output / "index.html", page), quote=True)
    projects_class = "current" if active == "projects" else ""
    creators_link = ""
    if creator_grid:
        creators_href = html.escape(_href(output / "creators.html", page), quote=True)
        creators_class = "current" if active == "creators" else ""
        creators_link = (
            f'<a class="{creators_class}" href="{creators_href}">'
            f'{html.escape(labels.creator.heading)}</a>'
        )
    return f"""
<nav class="site-nav" aria-label="Primary navigation">
  <a class="site-brand" href="{index_href}">Directory Gallery</a>
  <div class="site-nav-links">
    <a class="{projects_class}" href="{index_href}">{html.escape(labels.project.heading)}</a>
    {creators_link}
  </div>
</nav>""".strip()


def _lightbox() -> str:
    return """
<div class="lightbox" id="media-lightbox" hidden>
  <div class="lightbox-backdrop" data-lightbox-close></div>
  <section class="lightbox-dialog" role="dialog" aria-modal="true" aria-labelledby="lightbox-title">
    <header class="lightbox-header">
      <h2 id="lightbox-title"></h2>
      <div class="lightbox-actions">
        <a id="lightbox-original" target="_blank" rel="noopener">Open original</a>
        <button class="icon-button" type="button" data-lightbox-close aria-label="Close viewer">×</button>
      </div>
    </header>
    <div class="lightbox-stage">
      <button class="lightbox-step previous" type="button" data-lightbox-previous aria-label="Previous item">‹</button>
      <div class="lightbox-viewer">
        <div class="lightbox-media" id="lightbox-media"></div>
        <div class="audio-playlist" id="audio-playlist" hidden></div>
      </div>
      <button class="lightbox-step next" type="button" data-lightbox-next aria-label="Next item">›</button>
    </div>
  </section>
</div>""".strip()


def _document(
    output: Path,
    page: Path,
    title: str,
    active: str,
    header: str,
    content: str,
    body_class: str,
    creator_grid: bool,
    labels: DisplayLabels,
) -> str:
    labels_data = {
        "creator": {"singular": labels.creator.singular, "plural": labels.creator.plural},
        "project": {"singular": labels.project.singular, "plural": labels.project.plural},
    }
    return Template(_resource_text("index.html")).substitute(
        title_attribute=html.escape(title, quote=True),
        stylesheet=html.escape(
            _asset_href("assets/directory-gallery.css", output, page), quote=True
        ),
        script=html.escape(
            _asset_href("assets/directory-gallery.js", output, page), quote=True
        ),
        body_class=html.escape(body_class, quote=True),
        navigation=_navigation(output, page, active, creator_grid, labels),
        header=header,
        content=content,
        lightbox=_lightbox(),
        labels_data=_json_data(labels_data),
    )


def _count_label(value: int, singular: str) -> str:
    return f"{value} {singular if value == 1 else singular + 's'}"


def _overview_header(title: str, summary: str, search_label: str) -> str:
    return f"""
<header class="page-header overview-header">
  <h1>{html.escape(title)}</h1>
  <p class="summary">{summary}</p>
  <div class="controls" role="search">
    <label class="search-field">
      <span class="visually-hidden">{html.escape(search_label)}</span>
      <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m21 21-4.35-4.35m2.35-5.65a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z"/></svg>
      <input id="catalog-search" type="search" placeholder="{html.escape(search_label, quote=True)}" autocomplete="off">
    </label>
  </div>
</header>""".strip()


def _detail_header(
    eyebrow: str,
    title: str,
    subtitle: str,
    artwork: str,
    artwork_kind: str,
    breadcrumb: str,
    after_summary: str = "",
) -> str:
    return f"""
<header class="page-header detail-header">
  <nav class="breadcrumbs" aria-label="Breadcrumb">{breadcrumb}</nav>
  <div class="detail-hero">
    <span class="detail-artwork {artwork_kind}-frame">{artwork}</span>
    <div class="detail-copy">
      <p class="eyebrow">{html.escape(eyebrow)}</p>
      <h1>{html.escape(title)}</h1>
      <p class="summary">{html.escape(subtitle)}</p>
      {after_summary}
    </div>
  </div>
</header>""".strip()


def _member_markup(
    members: Sequence[MemberSummary], output: Path, page: Path
) -> str:
    if not members:
        return ""
    chips = []
    for member in members:
        artwork = _artwork(
            member.portrait, "portrait", member.name, "", output, page
        )
        content = (
            f'<span class="member-avatar">{artwork}</span>'
            f'<span class="member-name">{html.escape(member.name)}</span>'
        )
        if member.page is None:
            chips.append(f'<span class="member-chip is-unlinked">{content}</span>')
        else:
            href = html.escape(_href(member.page, page), quote=True)
            chips.append(f'<a class="member-chip" href="{href}">{content}</a>')
    return (
        '<section class="collaboration-members" aria-label="Collaboration members">'
        '<h2>Members</h2><div class="member-chips">'
        + "".join(chips)
        + "</div></section>"
    )


def _alphabet_markup(initials: Iterable[str]) -> str:
    values = sorted(set(initials), key=lambda value: (value == "#", value.casefold()))
    if not values:
        return ""
    buttons = ['<button class="current" type="button" data-initial="">All</button>']
    buttons.extend(
        f'<button type="button" data-initial="{html.escape(value, quote=True)}">{html.escape(value)}</button>'
        for value in values
    )
    return '<nav class="alphabet" aria-label="Filter by initial">' + "".join(buttons) + "</nav>"


def _creator_grid_content(
    items: List[Dict[str, object]], labels: DisplayLabels
) -> str:
    initials = (_initial(str(item["title"])) for item in items)
    return (
        _alphabet_markup(initials)
        + '<div class="overview-grid" data-overview-grid></div>'
        + '<nav class="pagination" data-pagination aria-label="Overview pages" hidden>'
        + '<button type="button" data-page-previous>Previous</button>'
        + '<span data-page-status></span>'
        + '<button type="button" data-page-next>Next</button></nav>'
        + f'<p class="empty-state" id="no-results" hidden>No matching {html.escape(labels.creator.plural)}.</p>'
        + f'<script type="application/json" id="overview-data">{_json_data(items)}</script>'
        + '<noscript><p class="empty-state">JavaScript is required to browse this page.</p></noscript>'
    )


def _rail(
    title: str, items: List[Dict[str, object]], kind: str, extra_class: str = ""
) -> str:
    classes = f"content-row {kind}-row"
    if extra_class:
        classes += f" {extra_class}"
    return f"""
<section class="{html.escape(classes, quote=True)}" data-content-kind="{html.escape(kind, quote=True)}">
  <div class="row-heading">
    <h2>{html.escape(title)}</h2>
    <div class="row-actions">
      <button type="button" data-rail-previous aria-label="Scroll {html.escape(title, quote=True)} left">‹</button>
      <button type="button" data-rail-next aria-label="Scroll {html.escape(title, quote=True)} right">›</button>
    </div>
  </div>
  <div class="rail-track" data-rail-track><div class="rail-canvas" data-rail-canvas></div></div>
  <script type="application/json" data-rail-data>{_json_data(items)}</script>
</section>""".strip()


def _project_row_items(
    projects: Sequence[ProjectSummary], output: Path, page: Path
) -> List[Dict[str, object]]:
    return [
        {
            "kind": "project",
            "title": project.name,
            "href": _href(project.page, page),
            "image": _asset_href(project.cover, output, page) if project.cover else None,
            "placeholder": next(
                (character.upper() for character in project.name if character.isalnum()),
                "?",
            ),
            **({"meta": project.credit} if project.credit else {}),
        }
        for project in projects
    ]


def _media_item_data(
    item: MediaItem,
    page: Path,
    output: Path,
    previews: Mapping[Path, Optional[str]],
) -> Dict[str, object]:
    preview = previews.get(item.path)
    return {
        "kind": item.kind,
        "title": item.name,
        "src": _href(item.path, page),
        "image": _asset_href(preview, output, page) if preview else None,
        "poster": (
            _asset_href(preview, output, page)
            if preview and item.kind == "video"
            else None
        ),
        "placeholder": {
            "image": "IMG",
            "pdf": "PDF",
            "video": "▶",
            "audio": "♪",
        }[item.kind],
    }


def _media_rows(
    groups: Sequence[MediaGroup],
    page: Path,
    output: Path,
    previews: Mapping[Path, Optional[str]],
) -> str:
    rows = []
    for group in groups:
        title = KIND_LABELS[group.kind]
        if group.directory is not None:
            title += f" · {group.directory.as_posix()}"
        items = [
            _media_item_data(item, page, output, previews) for item in group.items
        ]
        rows.append(_rail(title, items, group.kind))
    return "\n".join(rows)


def _readme_markup(markup: str) -> str:
    if not markup:
        return ""
    return (
        '<div class="readme-container">'
        '<article class="readme" id="readme-content">'
        f'<div class="readme-body">{markup}</div>'
        '</article>'
        '<button class="readme-toggle" type="button" '
        'aria-controls="readme-content" aria-expanded="false" hidden>'
        'Show more</button>'
        '</div>'
    )


def _warnings_markup(warnings: WarningLog) -> str:
    if not warnings.total_count:
        return ""
    entries = "".join(
        f'<li data-warning-code="{html.escape(warning.code, quote=True)}">{html.escape(warning.message)}</li>'
        for warning in warnings
    )
    omitted = warnings.total_count - len(warnings)
    if omitted:
        entries += (
            '<li data-warning-code="omitted">'
            f"{_count_label(omitted, 'additional notice')} omitted from this report."
            "</li>"
        )
    return (
        '<details class="warnings">'
        f"<summary>{_count_label(warnings.total_count, 'notice')}</summary>"
        f"<ul>{entries}</ul></details>"
    )


def _prepare_media_previews(
    groups: Sequence[MediaGroup], cache: ThumbnailCache
) -> Dict[Path, Optional[str]]:
    previews: Dict[Path, Optional[str]] = {}
    for group in groups:
        for item in group.items:
            if item.kind == "image":
                previews[item.path] = cache.thumbnail_for(item.path)
            elif item.kind == "pdf":
                previews[item.path] = cache.pdf_preview_for(item.path)
            elif item.kind == "video" and item.poster:
                previews[item.path] = cache.thumbnail_for(item.poster)
            else:
                previews[item.path] = None
    return previews


def _media_count(groups: Sequence[MediaGroup]) -> int:
    return sum(len(group.items) for group in groups)


def _write_generated(
    state: CatalogState, output: Path, path: Path, contents: str
) -> None:
    write_text_atomic(path, contents)
    state.record_generated(path.relative_to(output).as_posix())


def _render_project(
    project: Project,
    creator: Creator,
    creator_page: Path,
    page: Path,
    output: Path,
    cover: Optional[str],
    previews: Mapping[Path, Optional[str]],
    warnings: List[CatalogWarning],
    members: Sequence[MemberSummary],
    creator_grid: bool,
    exclusions: ExclusionRules,
    labels: DisplayLabels,
) -> str:
    artwork = _artwork(
        cover, "cover", project.name, f"Cover for {project.name}", output, page
    )
    breadcrumb = (
        f'<a href="{html.escape(_href(output / "index.html", page), quote=True)}">{html.escape(labels.project.heading)}</a>'
        f'<span aria-hidden="true">/</span><a href="{html.escape(_href(creator_page, page), quote=True)}">{html.escape(creator.name)}</a>'
        f'<span aria-hidden="true">/</span><span>{html.escape(project.name)}</span>'
    )
    header = _detail_header(
        labels.project.detail_heading, project.name, creator.name, artwork, "cover", breadcrumb,
        _member_markup(members, output, page),
    )
    readme = render_readme(project.readme, project.path, page, warnings, exclusions)
    rows = _media_rows(project.media, page, output, previews)
    if not rows:
        rows = '<p class="empty-state">No supported media.</p>'
    return _document(
        output,
        page,
        f"{project.name} — {creator.name}",
        "projects",
        header,
        _readme_markup(readme) + rows,
        "detail-page project-page",
        creator_grid,
        labels,
    )


def _render_creator(
    creator: Creator,
    projects: Sequence[ProjectSummary],
    members: Sequence[MemberSummary],
    page: Path,
    output: Path,
    portrait: Optional[str],
    previews: Mapping[Path, Optional[str]],
    warnings: List[CatalogWarning],
    creator_grid: bool,
    exclusions: ExclusionRules,
    labels: DisplayLabels,
) -> str:
    artwork = _artwork(
        portrait,
        "portrait",
        creator.name,
        f"Portrait of {creator.name}",
        output,
        page,
    )
    breadcrumb = (
        f'<a href="{html.escape(_href(output / "index.html", page), quote=True)}">'
        f'{html.escape(labels.project.heading)}</a>'
        f'<span aria-hidden="true">/</span><span>{html.escape(creator.name)}</span>'
    )
    header = _detail_header(
        labels.creator.detail_heading,
        creator.name,
        labels.project.count(len(projects)),
        artwork,
        "portrait",
        breadcrumb,
        _member_markup(members, output, page),
    )
    readme = render_readme(creator.readme, creator.path, page, warnings, exclusions)
    rows = []
    if projects:
        rows.append(
            _rail(
                labels.project.heading,
                _project_row_items(projects, output, page),
                "project",
                "collaboration-row" if any(project.credit for project in projects) else "",
            )
        )
    rows.append(_media_rows(creator.media, page, output, previews))
    row_markup = "\n".join(row for row in rows if row)
    if not row_markup:
        row_markup = (
            '<p class="empty-state">No supported media or '
            f'{html.escape(labels.project.plural)}.</p>'
        )
    return _document(
        output,
        page,
        f"{creator.name} — {labels.creator.heading}",
        "projects",
        header,
        _readme_markup(readme) + row_markup,
        "detail-page creator-page",
        creator_grid,
        labels,
    )


def _member_summaries(
    state: CatalogState, creator_path: Path, output: Path
) -> List[MemberSummary]:
    return [
        MemberSummary(
            name=str(row["member_name"]),
            page=output / str(row["page"]) if row["page"] else None,
            portrait=str(row["portrait"]) if row["portrait"] else None,
        )
        for row in state.members_for_collaboration(creator_path)
    ]


def _project_summaries(
    rows: Iterable[sqlite3.Row], output: Path, *, credit: bool = False
) -> List[ProjectSummary]:
    return [
        ProjectSummary(
            name=str(row["name"]),
            path=Path(str(row["source_path"])),
            page=output / str(row["page"]),
            cover=str(row["cover"]) if row["cover"] else None,
            credit=str(row["collaboration_name"]) if credit else None,
        )
        for row in rows
    ]


def _creator_projects(
    state: CatalogState,
    creator_path: Path,
    output: Path,
    include_collaborations: bool,
) -> List[ProjectSummary]:
    projects = _project_summaries(
        state.projects_for_creator(os.fspath(creator_path.resolve())), output
    )
    if include_collaborations:
        projects.extend(
            _project_summaries(
                state.collaboration_projects_for_member(creator_path),
                output,
                credit=True,
            )
        )
    projects.sort(
        key=lambda project: (
            project.name.casefold(),
            project.name,
            (project.credit or "").casefold(),
            project.credit or "",
        )
    )
    return projects


def _creator_grid_items(
    state: CatalogState, output: Path, page: Path, include_collaborations: bool,
    labels: DisplayLabels,
) -> List[Dict[str, object]]:
    items = []
    for row in state.creators():
        name = str(row["name"])
        portrait = row["portrait"]
        project_count = int(row["project_count"])
        if include_collaborations:
            project_count += state.collaboration_project_count_for_member(
                Path(str(row["source_path"]))
            )
        items.append(
            {
                "title": name,
                "search": name.casefold(),
                "initial": _initial(name),
                "href": _href(output / str(row["page"]), page),
                "image": _asset_href(str(portrait), output, page) if portrait else None,
                "placeholder": next(
                    (character.upper() for character in name if character.isalnum()),
                    "?",
                ),
                "meta": labels.project.count(project_count),
            }
        )
    return items


def _catalog_items(
    state: CatalogState, output: Path, page: Path, include_collaborations: bool
) -> List[Dict[str, object]]:
    items: List[Dict[str, object]] = []
    for creator_row in state.creators():
        creator_name = str(creator_row["name"])
        portrait = creator_row["portrait"]
        projects = []
        for project in _creator_projects(
            state,
            Path(str(creator_row["source_path"])),
            output,
            include_collaborations,
        ):
            project_name = project.name
            credit = project.credit or creator_name
            projects.append(
                {
                    "kind": "project",
                    "title": project_name,
                    "search": f"{project_name} {credit}".casefold(),
                    "initial": _initial(project_name),
                    "href": _href(project.page, page),
                    "image": (
                        _asset_href(project.cover, output, page)
                        if project.cover else None
                    ),
                    "credit": credit,
                    **({"meta": credit} if project.credit else {}),
                    "placeholder": next(
                        (
                            character.upper()
                            for character in project_name
                            if character.isalnum()
                        ),
                        "?",
                    ),
                }
            )
        items.append(
            {
                "title": creator_name,
                "search": creator_name.casefold(),
                "initial": _initial(creator_name),
                "href": _href(output / str(creator_row["page"]), page),
                "image": (
                    _asset_href(str(portrait), output, page) if portrait else None
                ),
                "placeholder": next(
                    (character.upper() for character in creator_name if character.isalnum()),
                    "?",
                ),
                "projects": projects,
            }
        )
    return items


def _catalog_content(
    items: List[Dict[str, object]], labels: DisplayLabels
) -> str:
    initials = [str(item["initial"]) for item in items]
    initials.extend(
        str(project["initial"])
        for item in items
        for project in item["projects"]
    )
    return (
        '<div class="overview-view-switch" role="group" aria-label="Overview layout">'
        f'<button type="button" data-catalog-view="creators" aria-pressed="false">By {html.escape(labels.creator.singular)}</button>'
        f'<button class="current" type="button" data-catalog-view="projects" aria-pressed="true">All {html.escape(labels.project.plural)}</button>'
        '</div>'
        + '<div data-catalog-alphabet>' + _alphabet_markup(initials) + '</div>'
        + '<div class="grouped-list" data-catalog-creator-list hidden></div>'
        + '<div class="overview-grid" data-catalog-project-grid></div>'
        + '<nav class="pagination" data-catalog-pagination '
        + 'aria-label="Overview pages" hidden>'
        + '<button type="button" data-catalog-previous>Previous</button>'
        + '<span data-catalog-status></span>'
        + '<button type="button" data-catalog-next>Next</button></nav>'
        + f'<p class="empty-state" id="no-results" hidden>No matching {html.escape(labels.project.plural)}.</p>'
        + '<script type="application/json" id="catalog-data">'
        + f"{_json_data(items)}</script>"
        + "<noscript><p class=\"empty-state\">"
        + "JavaScript is required to browse this page.</p></noscript>"
    )


def build_site(
    input_root: Path,
    output: Path,
    exclusions: ExclusionRules,
    labels: DisplayLabels,
    creator_grid: bool = True,
    link_collaborations: bool = False,
    quiet: bool = False,
) -> BuildResult:
    warnings = WarningLog()
    creators = creator_paths(input_root, exclusions)
    progress = ProgressReporter(len(creators), enabled=not quiet)
    project_count = 0
    media_count = 0
    index = output / "index.html"

    with CatalogState(output, input_root, warnings) as state:
        cache = ThumbnailCache(output, warnings, state, progress=progress.update)
        progress.attach_cache(cache)
        portrait_index: Dict[Path, Optional[str]] = {}
        member_paths = set()
        deferred_creators = []

        if link_collaborations:
            # Index only direct creator artwork before rendering project pages,
            # so member links can already use cached portraits and page paths.
            for creator_path in creators:
                candidate = creator_portrait_candidate(creator_path, exclusions)
                portrait = cache.thumbnail_for(candidate) if candidate else None
                portrait_index[creator_path] = portrait
                state.record_creator(
                    creator_path,
                    creator_path.name,
                    _creator_page(output, creator_path).relative_to(output).as_posix(),
                    portrait,
                    0,
                )

            creators_by_name = {path.name: path for path in creators}
            for creator_path in creators:
                members = collaboration_members(creator_path.name, creators_by_name)
                for position, (member_name, member_path) in enumerate(members):
                    state.record_collaboration_member(
                        creator_path, position, member_name, member_path
                    )
                    if member_path is not None:
                        member_paths.add(member_path)

        for creator_path in creators:
            creator = scan_creator(creator_path, warnings, exclusions)
            creator_page = _creator_page(output, creator_path)
            portrait = portrait_index[creator_path] if link_collaborations else (
                cache.thumbnail_for(creator.portrait) if creator.portrait else None
            )
            members = (
                _member_summaries(state, creator_path, output)
                if link_collaborations else []
            )
            defer_creator = creator_path in member_paths
            creator_media_count = _media_count(creator.media)
            media_count += creator_media_count
            progress.media = media_count
            creator_previews = (
                {} if defer_creator else _prepare_media_previews(creator.media, cache)
            )
            summaries: List[ProjectSummary] = []

            for project_path in project_paths(creator_path, exclusions):
                project = scan_project(creator.name, project_path, warnings, exclusions)
                page = _project_page(output, project_path)
                cover = cache.thumbnail_for(project.cover) if project.cover else None
                project_media_count = _media_count(project.media)
                media_count += project_media_count
                project_count += 1
                progress.projects = project_count
                progress.media = media_count
                previews = _prepare_media_previews(project.media, cache)
                document = _render_project(
                    project,
                    creator,
                    creator_page,
                    page,
                    output,
                    cover,
                    previews,
                    warnings,
                    members,
                    creator_grid,
                    exclusions,
                    labels,
                )
                _write_generated(state, output, page, document)
                relative_page = page.relative_to(output).as_posix()
                state.record_project(
                    project.path,
                    creator.path,
                    creator.name,
                    project.name,
                    relative_page,
                    cover,
                )
                summaries.append(ProjectSummary(project.name, project.path, page, cover))
                progress.update()

            if defer_creator:
                deferred_creators.append(creator_path)
            else:
                creator_document = _render_creator(
                    creator,
                    summaries,
                    members,
                    creator_page,
                    output,
                    portrait,
                    creator_previews,
                    warnings,
                    creator_grid,
                    exclusions,
                    labels,
                )
                _write_generated(state, output, creator_page, creator_document)
            state.record_creator(
                creator.path,
                creator.name,
                creator_page.relative_to(output).as_posix(),
                portrait,
                len(summaries),
            )
            progress.creators += 1
            progress.update()

        for creator_path in deferred_creators:
            creator = scan_creator(creator_path, [], exclusions)
            creator_page = _creator_page(output, creator_path)
            creator_document = _render_creator(
                creator,
                _creator_projects(state, creator_path, output, True),
                _member_summaries(state, creator_path, output),
                creator_page,
                output,
                portrait_index[creator_path],
                _prepare_media_previews(creator.media, cache),
                warnings,
                creator_grid,
                exclusions,
                labels,
            )
            _write_generated(state, output, creator_page, creator_document)

        creator_count = len(creators)
        catalog_summary = (
            f'<span id="visible-items">{project_count}</span> '
            f'<span id="visible-label">{html.escape(labels.project.noun(project_count))}</span>'
            f'<span data-catalog-extra-summary hidden> · '
            f'<span id="visible-projects">{project_count}</span> '
            f'<span id="visible-project-label">{html.escape(labels.project.noun(project_count))}</span>'
            '</span>'
        )
        catalog_items = _catalog_items(state, output, index, link_collaborations)
        index_content = _catalog_content(catalog_items, labels)
        index_header = _overview_header(
            labels.project.heading,
            catalog_summary,
            f"Search {labels.project.plural} and {labels.creator.plural}",
        )
        index_content += _warnings_markup(warnings)
        _write_generated(
            state,
            output,
            index,
            _document(
                output,
                index,
                labels.project.heading,
                "projects",
                index_header,
                index_content,
                "overview-page catalog-overview",
                creator_grid,
                labels,
            ),
        )

        if creator_grid:
            creators_page = output / "creators.html"
            creator_items = _creator_grid_items(
                state, output, creators_page, link_collaborations, labels
            )
            creators_summary = (
                f'<span id="visible-items">{creator_count}</span> '
                f'<span id="visible-label">'
                f'{html.escape(labels.creator.noun(creator_count))}</span>'
            )
            creators_header = _overview_header(
                labels.creator.heading,
                creators_summary,
                f"Search {labels.creator.plural}",
            )
            _write_generated(
                state,
                output,
                creators_page,
                _document(
                    output,
                    creators_page,
                    labels.creator.heading,
                    "creators",
                    creators_header,
                    _creator_grid_content(creator_items, labels),
                    "overview-page creators-overview",
                    creator_grid,
                    labels,
                ),
            )

        for name in ("gallery.css", "gallery.js"):
            target_name = f"directory-gallery.{name.rsplit('.', 1)[1]}"
            target = output / "assets" / target_name
            _write_generated(state, output, target, _resource_text(name))

        state.finish()
        progress.finish()
        return BuildResult(
            creator_count=creator_count,
            project_count=project_count,
            media_count=media_count,
            warning_count=warnings.total_count,
            previews_generated=cache.generated_count,
            previews_reused=cache.reused_count,
            index=index,
        )
