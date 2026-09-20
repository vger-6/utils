"""Render a multi-page static media catalog."""

from __future__ import annotations

import hashlib
import html
import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from string import Template
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import quote

from .models import Catalog, CatalogWarning, Creator, MediaGroup, MediaItem, Project
from .output import write_text_atomic
from .readme import render_readme
from .thumbnails import ThumbnailCache


KIND_LABELS = {
    "image": "Images",
    "pdf": "PDFs",
    "video": "Videos",
    "audio": "Audio",
}


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


def _digest(path: Path) -> str:
    return hashlib.sha256(os.fsencode(path.resolve())).hexdigest()[:16]


def _creator_page(output: Path, creator: Creator) -> Path:
    return output / "creators" / f"{_digest(creator.path)}.html"


def _project_page(output: Path, project: Project) -> Path:
    return output / "projects" / f"{_digest(project.path)}.html"


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


def _placeholder(kind: str, name: str, label: Optional[str] = None) -> str:
    text = label or next(
        (character.upper() for character in name if character.isalnum()), "?"
    )
    return (
        f'<span class="image-placeholder {kind}-placeholder" aria-hidden="true">'
        f"<span>{html.escape(text)}</span></span>"
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


def _navigation(output: Path, page: Path, active: str) -> str:
    creators_class = " current" if active == "creators" else ""
    projects_class = " current" if active == "projects" else ""
    return f"""
<nav class="site-nav" aria-label="Primary navigation">
  <a class="site-brand" href="{html.escape(_href(output / 'index.html', page), quote=True)}">
    Directory Gallery
  </a>
  <div class="site-nav-links">
    <a class="{creators_class.strip()}" href="{html.escape(_href(output / 'index.html', page), quote=True)}">Creators</a>
    <a class="{projects_class.strip()}" href="{html.escape(_href(output / 'projects.html', page), quote=True)}">Projects</a>
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
      <div class="lightbox-viewer" id="lightbox-viewer"></div>
      <button class="lightbox-step next" type="button" data-lightbox-next aria-label="Next item">›</button>
    </div>
    <div class="audio-playlist" id="audio-playlist" hidden></div>
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
) -> str:
    template = Template(_resource_text("index.html"))
    return template.substitute(
        title_attribute=html.escape(title, quote=True),
        stylesheet=html.escape(
            _asset_href("assets/directory-gallery.css", output, page), quote=True
        ),
        script=html.escape(
            _asset_href("assets/directory-gallery.js", output, page), quote=True
        ),
        body_class=html.escape(body_class, quote=True),
        navigation=_navigation(output, page, active),
        header=header,
        content=content,
        lightbox=_lightbox(),
    )


def _count_label(value: int, singular: str) -> str:
    return f"{value} {singular if value == 1 else singular + 's'}"


def _overview_header(title: str, summary: str, search_label: str) -> str:
    return f"""
<header class="page-header overview-header">
  <p class="eyebrow">Directory gallery</p>
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
    </div>
  </div>
</header>""".strip()


def _alphabet_markup(entries: Sequence[Tuple[str, str]]) -> str:
    first_for_initial: Dict[str, str] = {}
    for name, anchor in entries:
        first_for_initial.setdefault(_initial(name), anchor)
    if not first_for_initial:
        return ""
    links = "".join(
        f'<a href="#{html.escape(anchor, quote=True)}" aria-label="Jump to {html.escape(initial, quote=True)}">{html.escape(initial)}</a>'
        for initial, anchor in sorted(
            first_for_initial.items(),
            key=lambda item: (item[0] == "#", item[0].casefold()),
        )
    )
    return f'<nav class="alphabet" aria-label="Alphabetical index">{links}</nav>'


def _creator_card(
    creator: Creator,
    page: Path,
    target: Path,
    portrait: Optional[str],
    output: Path,
) -> str:
    artwork = _artwork(
        portrait, "portrait", creator.name, f"Portrait of {creator.name}", output, page
    )
    count = _count_label(len(creator.projects), "project")
    anchor = f"item-{_digest(creator.path)}"
    return f"""
<a class="overview-card creator-overview-card" id="{anchor}" data-search-card
   data-search-text="{html.escape(creator.name.casefold(), quote=True)}"
   href="{html.escape(_href(target, page), quote=True)}">
  <span class="overview-artwork portrait-frame">{artwork}</span>
  <span class="overview-copy">
    <span class="overview-title">{html.escape(creator.name)}</span>
    <span class="overview-meta">{count}</span>
  </span>
</a>""".strip()


def _project_card(
    creator: Creator,
    project: Project,
    page: Path,
    target: Path,
    cover: Optional[str],
    output: Path,
    overview: bool = False,
) -> str:
    artwork = _artwork(
        cover, "cover", project.name, f"Cover for {project.name}", output, page
    )
    classes = "overview-card project-overview-card" if overview else "project-card"
    search = (
        f' data-search-card data-search-text="{html.escape((project.name + " " + creator.name).casefold(), quote=True)}"'
        if overview
        else ""
    )
    anchor = f' id="item-{_digest(project.path)}"' if overview else ""
    creator_label = (
        f'<span class="overview-meta">{html.escape(creator.name)}</span>'
        if overview
        else ""
    )
    return f"""
<a class="{classes}"{anchor}{search} href="{html.escape(_href(target, page), quote=True)}">
  <span class="project-artwork cover-frame">{artwork}</span>
  <span class="overview-copy">
    <span class="overview-title">{html.escape(project.name)}</span>
    {creator_label}
  </span>
</a>""".strip()


def _rail(title: str, group_id: str, cards: Iterable[str], kind: str) -> str:
    content = "\n".join(cards)
    return f"""
<section class="content-row" data-content-kind="{html.escape(kind, quote=True)}">
  <div class="row-heading">
    <h2>{html.escape(title)}</h2>
    <div class="row-actions">
      <button type="button" data-rail-previous aria-label="Scroll {html.escape(title, quote=True)} left">‹</button>
      <button type="button" data-rail-next aria-label="Scroll {html.escape(title, quote=True)} right">›</button>
    </div>
  </div>
  <div class="rail-track" data-rail-track data-group-id="{html.escape(group_id, quote=True)}">{content}</div>
</section>""".strip()


def _media_card(
    item: MediaItem,
    group_id: str,
    page: Path,
    output: Path,
    preview: Optional[str],
) -> str:
    source = html.escape(_href(item.path, page), quote=True)
    poster_attribute = ""
    if item.kind in {"image", "pdf", "video"} and preview:
        thumbnail = _asset_href(preview, output, page)
        image = (
            f'<img src="{html.escape(thumbnail, quote=True)}" alt="" '
            f'loading="lazy" decoding="async">'
        )
        if item.kind == "video":
            poster_attribute = f' data-poster="{html.escape(thumbnail, quote=True)}"'
    else:
        glyph = {"image": "IMG", "pdf": "PDF", "video": "▶", "audio": "♪"}[item.kind]
        image = _placeholder("media", item.name, glyph)

    return f"""
<button class="media-card {item.kind}-card" type="button"
        data-media-kind="{item.kind}" data-media-group="{html.escape(group_id, quote=True)}"
        data-media-src="{source}" data-media-title="{html.escape(item.name, quote=True)}"{poster_attribute}>
  <span class="media-artwork">{image}</span>
  <span class="media-title">{html.escape(item.name)}</span>
</button>""".strip()


def _media_rows(
    groups: Sequence[MediaGroup],
    owner: Path,
    page: Path,
    output: Path,
    previews: Mapping[Path, Optional[str]],
) -> str:
    rows = []
    for index, group in enumerate(groups):
        title = KIND_LABELS[group.kind]
        if group.directory is not None:
            title += f" · {group.directory.as_posix()}"
        group_id = f"media-{_digest(owner)}-{group.kind}-{index}"
        cards = (
            _media_card(item, group_id, page, output, previews.get(item.path))
            for item in group.items
        )
        rows.append(_rail(title, group_id, cards, group.kind))
    return "\n".join(rows)


def _readme_markup(markup: str) -> str:
    if not markup:
        return ""
    return f'<article class="readme">{markup}</article>'


def _warnings_markup(warnings: List[CatalogWarning]) -> str:
    if not warnings:
        return ""
    entries = "".join(
        f'<li data-warning-code="{html.escape(warning.code, quote=True)}">{html.escape(warning.message)}</li>'
        for warning in warnings
    )
    label = _count_label(len(warnings), "catalog notice")
    return (
        '<details class="warnings">'
        f"<summary>{label}</summary><ul>{entries}</ul></details>"
    )


def _prepare_previews(
    catalog: Catalog,
    cache: ThumbnailCache,
) -> Tuple[Dict[Path, Optional[str]], Dict[Path, Optional[str]], Dict[Path, Optional[str]]]:
    portraits: Dict[Path, Optional[str]] = {}
    covers: Dict[Path, Optional[str]] = {}
    media: Dict[Path, Optional[str]] = {}

    for creator in catalog.creators:
        portraits[creator.path] = (
            cache.thumbnail_for(creator.portrait) if creator.portrait else None
        )
        for group in creator.media:
            for item in group.items:
                if item.kind == "image":
                    media[item.path] = cache.thumbnail_for(item.path)
                elif item.kind == "pdf":
                    media[item.path] = cache.pdf_preview_for(item.path)
                elif item.kind == "video" and item.poster:
                    media[item.path] = cache.thumbnail_for(item.poster)
                else:
                    media[item.path] = None

        for project in creator.projects:
            covers[project.path] = (
                cache.thumbnail_for(project.cover) if project.cover else None
            )
            for group in project.media:
                for item in group.items:
                    if item.kind == "image":
                        media[item.path] = cache.thumbnail_for(item.path)
                    elif item.kind == "pdf":
                        media[item.path] = cache.pdf_preview_for(item.path)
                    elif item.kind == "video" and item.poster:
                        media[item.path] = cache.thumbnail_for(item.poster)
                    else:
                        media[item.path] = None

    return portraits, covers, media


def build_site(catalog: Catalog, output: Path, title: str) -> BuildResult:
    warnings = list(catalog.warnings)
    cache = ThumbnailCache(output, warnings)
    portraits, covers, previews = _prepare_previews(catalog, cache)
    creator_pages = {
        creator.path: _creator_page(output, creator) for creator in catalog.creators
    }
    project_pages = {
        project.path: _project_page(output, project)
        for creator in catalog.creators
        for project in creator.projects
    }
    all_projects = sorted(
        (
            (creator, project)
            for creator in catalog.creators
            for project in creator.projects
        ),
        key=lambda item: (
            item[1].name.casefold(),
            item[1].name,
            item[0].name.casefold(),
            item[0].name,
        ),
    )
    generated = {
        "index.html",
        "projects.html",
        "assets/directory-gallery.css",
        "assets/directory-gallery.js",
    }

    for creator in catalog.creators:
        page = creator_pages[creator.path]
        generated.add(page.relative_to(output).as_posix())
        portrait = _artwork(
            portraits[creator.path],
            "portrait",
            creator.name,
            f"Portrait of {creator.name}",
            output,
            page,
        )
        breadcrumb = (
            f'<a href="{html.escape(_href(output / "index.html", page), quote=True)}">Creators</a>'
            f"<span aria-hidden=\"true\">/</span><span>{html.escape(creator.name)}</span>"
        )
        header = _detail_header(
            "Creator",
            creator.name,
            _count_label(len(creator.projects), "project"),
            portrait,
            "portrait",
            breadcrumb,
        )
        readme = render_readme(creator.readme, creator.path, page, warnings)
        rows = []
        if creator.projects:
            cards = (
                _project_card(
                    creator,
                    project,
                    page,
                    project_pages[project.path],
                    covers[project.path],
                    output,
                )
                for project in creator.projects
            )
            rows.append(_rail("Projects", f"projects-{_digest(creator.path)}", cards, "project"))
        rows.append(_media_rows(creator.media, creator.path, page, output, previews))
        row_markup = "\n".join(row for row in rows if row)
        if not row_markup:
            row_markup = '<p class="empty-state">No supported media or projects.</p>'
        document = _document(
            output,
            page,
            f"{creator.name} — {title}",
            "creators",
            header,
            _readme_markup(readme) + row_markup,
            "detail-page creator-page",
        )
        write_text_atomic(page, document)

        for project in creator.projects:
            project_page = project_pages[project.path]
            generated.add(project_page.relative_to(output).as_posix())
            cover = _artwork(
                covers[project.path],
                "cover",
                project.name,
                f"Cover for {project.name}",
                output,
                project_page,
            )
            breadcrumb = (
                f'<a href="{html.escape(_href(output / "projects.html", project_page), quote=True)}">Projects</a>'
                f'<span aria-hidden="true">/</span><a href="{html.escape(_href(page, project_page), quote=True)}">{html.escape(creator.name)}</a>'
                f'<span aria-hidden="true">/</span><span>{html.escape(project.name)}</span>'
            )
            project_header = _detail_header(
                "Project",
                project.name,
                creator.name,
                cover,
                "cover",
                breadcrumb,
            )
            project_readme = render_readme(
                project.readme, project.path, project_page, warnings
            )
            rows = _media_rows(
                project.media, project.path, project_page, output, previews
            )
            if not rows:
                rows = '<p class="empty-state">No supported media.</p>'
            project_document = _document(
                output,
                project_page,
                f"{project.name} — {creator.name}",
                "projects",
                project_header,
                _readme_markup(project_readme) + rows,
                "detail-page project-page",
            )
            write_text_atomic(project_page, project_document)

    projects_page = output / "projects.html"
    project_entries = [
        (project.name, f"item-{_digest(project.path)}")
        for creator, project in all_projects
    ]
    project_cards = "\n".join(
        _project_card(
            creator,
            project,
            projects_page,
            project_pages[project.path],
            covers[project.path],
            output,
            overview=True,
        )
        for creator, project in all_projects
    )
    if not project_cards:
        project_cards = '<p class="empty-state">No projects found.</p>'
    project_count = catalog.project_count
    project_summary = (
        f'<span id="visible-items">{project_count}</span> '
        f'<span id="visible-label">{"project" if project_count == 1 else "projects"}</span>'
    )
    projects_header = _overview_header("Projects", project_summary, "Search projects and creators")
    projects_content = (
        _alphabet_markup(project_entries)
        + f'<div class="overview-grid" data-overview-grid>{project_cards}</div>'
        + '<p class="empty-state" id="no-results" hidden>No matching projects.</p>'
    )
    write_text_atomic(
        projects_page,
        _document(
            output,
            projects_page,
            f"Projects — {title}",
            "projects",
            projects_header,
            projects_content,
            "overview-page projects-overview",
        ),
    )

    index = output / "index.html"
    creator_entries = [
        (creator.name, f"item-{_digest(creator.path)}") for creator in catalog.creators
    ]
    creator_cards = "\n".join(
        _creator_card(
            creator,
            index,
            creator_pages[creator.path],
            portraits[creator.path],
            output,
        )
        for creator in catalog.creators
    )
    if not creator_cards:
        creator_cards = '<p class="empty-state">No creators found.</p>'
    creator_count = len(catalog.creators)
    creator_summary = (
        f'<span id="visible-items">{creator_count}</span> '
        f'<span id="visible-label">{"creator" if creator_count == 1 else "creators"}</span> · '
        f'{_count_label(project_count, "project")}'
    )
    index_header = _overview_header(title, creator_summary, "Search creators")
    index_content = (
        _alphabet_markup(creator_entries)
        + f'<div class="overview-grid" data-overview-grid>{creator_cards}</div>'
        + '<p class="empty-state" id="no-results" hidden>No matching creators.</p>'
        + _warnings_markup(warnings)
    )
    write_text_atomic(
        index,
        _document(
            output,
            index,
            title,
            "creators",
            index_header,
            index_content,
            "overview-page creators-overview",
        ),
    )

    write_text_atomic(
        output / "assets" / "directory-gallery.css",
        _resource_text("gallery.css"),
    )
    write_text_atomic(
        output / "assets" / "directory-gallery.js",
        _resource_text("gallery.js"),
    )
    cache.finish(catalog.root, generated)

    return BuildResult(
        creator_count=creator_count,
        project_count=project_count,
        warning_count=len(warnings),
        index=index,
    )
