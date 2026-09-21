from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from directory_gallery.cli import main


RESOURCES = Path(__file__).resolve().parents[1] / "src" / "directory_gallery" / "resources"
CHROMIUM = shutil.which("chromium") or shutil.which("chromium-browser")


@unittest.skipUnless(CHROMIUM, "Chromium is needed for the optional layout test")
class FrontendTests(unittest.TestCase):
    def browser_result(self, fixture: Path, profile: Path, width: int, fragment: str = ""):
        try:
            result = subprocess.run(
                [
                    CHROMIUM,
                    "--headless",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    f"--user-data-dir={profile}",
                    f"--window-size={width},900",
                    "--virtual-time-budget=1000",
                    "--dump-dom",
                    fixture.as_uri() + fragment,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            if error.returncode < 0:
                self.skipTest("Chromium cannot start in this environment")
            raise
        match = re.search(r'<pre id="result">([^<]+)</pre>', result.stdout)
        self.assertIsNotNone(match, result.stdout[-1000:])
        return json.loads(html.unescape(match.group(1)))

    def test_rail_labels_tooltip_and_full_lightbox_title(self):
        name = "An exceptionally long project or media filename that should span far more than three lines in a narrow card " * 3
        rows = []
        for kind in ("project", "image", "pdf", "video", "audio"):
            item = {"kind": kind, "title": name, "placeholder": "A"}
            if kind == "project":
                item["href"] = "#project"
            else:
                item["src"] = "#media"
            rows.append(
                f'<section class="content-row {kind}-row">'
                '<button data-rail-previous></button><button data-rail-next></button>'
                '<div class="rail-track" data-rail-track>'
                '<div class="rail-canvas" data-rail-canvas></div></div>'
                f'<script type="application/json" data-rail-data>{json.dumps([item])}</script>'
                '</section>'
            )

        credit = "A collaboration with an unusually long creator credit " * 2
        rows.append(
            '<section class="content-row project-row collaboration-row">'
            '<button data-rail-previous></button><button data-rail-next></button>'
            '<div class="rail-track" data-rail-track>'
            '<div class="rail-canvas" data-rail-canvas></div></div>'
            f'<script type="application/json" data-rail-data>{json.dumps([{"kind": "project", "title": name, "href": "#collaboration", "placeholder": "A", "meta": credit}])}</script>'
            '</section>'
        )

        catalog_creators = [
            {"title": "Alice", "search": "alice", "initial": "A", "href": "#alice", "image": "#portrait", "placeholder": "A", "projects": []},
            {"title": "Bob", "search": "bob", "initial": "B", "href": "#bob", "image": None, "placeholder": "B", "projects": []},
        ]

        document = f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="{(RESOURCES / 'gallery.css').as_uri()}">
<body><main class="site-main">{''.join(rows)}
<div class="overview-card" style="width:180px"><span class="overview-title">{html.escape(name)}</span></div>
<input id="catalog-search" type="search">
<div data-catalog-creator-list></div>
<div data-catalog-project-grid hidden></div>
<nav data-catalog-pagination hidden><button data-catalog-previous></button><button data-catalog-next></button><span data-catalog-status></span></nav>
<script type="application/json" id="catalog-data">{json.dumps(catalog_creators)}</script>
</main>
<div class="lightbox-dialog" id="dialog" style="width:320px;height:300px">
  <div class="lightbox-header"><h2 id="lightbox-title">{html.escape(name[:110])}</h2>
  <div class="lightbox-actions"><button>Close</button></div></div>
  <div class="lightbox-stage"></div>
</div>
<pre id="result"></pre>
<script src="{(RESOURCES / 'gallery.js').as_uri()}"></script>
<script>
const results = {{}};
for (const kind of ["project", "image", "pdf", "video", "audio"]) {{
  const row = document.querySelector(`.${{kind}}-row`);
  const track = row.querySelector(".rail-track");
  const label = row.querySelector(".overview-title, .media-title");
  const style = getComputedStyle(label);
  results[kind] = {{
    verticalOverflow: track.scrollHeight > track.clientHeight,
    overflowY: getComputedStyle(track).overflowY,
    lines: Math.round(label.clientHeight / parseFloat(style.lineHeight)),
    clamped: label.scrollHeight > label.clientHeight,
  }};
}}
const projectCard = document.querySelector(".project-card");
projectCard.dispatchEvent(new PointerEvent("pointerenter", {{pointerType: "mouse"}}));
const tooltip = document.querySelector(".rail-tooltip");
results.tooltip = {{visible: !!tooltip && !tooltip.hidden, full: tooltip?.textContent === {json.dumps(name)} }};
projectCard.dispatchEvent(new PointerEvent("pointerleave", {{pointerType: "mouse"}}));
results.tooltip.hiddenAfterLeave = tooltip.hidden;
projectCard.focus();
results.tooltip.visibleOnKeyboardFocus = !tooltip.hidden;
window.dispatchEvent(new Event("scroll"));
results.tooltip.visibleAfterKeyboardScroll = !tooltip.hidden;
projectCard.blur();
projectCard.dispatchEvent(new PointerEvent("pointerenter", {{pointerType: "touch"}}));
results.tooltip.hiddenOnTouch = tooltip.hidden;
const overviewLabel = document.querySelector(".overview-card .overview-title");
results.overview = {{clamp: getComputedStyle(overviewLabel).webkitLineClamp}};
const collaborationRow = document.querySelector(".collaboration-row");
const collaborationTrack = collaborationRow.querySelector(".rail-track");
const collaborationCredit = collaborationRow.querySelector(".overview-meta");
results.collaboration = {{
  verticalOverflow: collaborationTrack.scrollHeight > collaborationTrack.clientHeight,
  fullCredit: collaborationCredit.textContent === {json.dumps(credit)} && collaborationCredit.title === {json.dumps(credit)},
  ellipsized: collaborationCredit.scrollWidth > collaborationCredit.clientWidth,
}};
const dialog = document.querySelector("#dialog");
const lightboxTitle = document.querySelector("#lightbox-title");
results.lightbox = {{
  full: lightboxTitle.scrollHeight === lightboxTitle.clientHeight,
  wrapped: lightboxTitle.clientHeight > parseFloat(getComputedStyle(lightboxTitle).lineHeight),
  fixed: Math.round(dialog.getBoundingClientRect().height) === 300,
}};
const badges = document.querySelectorAll(".grouped-portrait-artwork");
results.grouped = {{
  count: badges.length,
  portrait: !!badges[0]?.querySelector("img"),
  initial: badges[1]?.querySelector(".image-placeholder span")?.textContent,
  circular: [...badges].every((badge) => {{
    const bounds = badge.getBoundingClientRect();
    return getComputedStyle(badge).borderRadius === "50%" && Math.abs(bounds.width - bounds.height) < 1;
  }}),
}};
document.querySelector("#result").textContent = JSON.stringify(results);
</script></body></html>'''

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            fixture = temporary / "layout.html"
            fixture.write_text(document, encoding="utf-8")
            for width in (1280, 500):
                with self.subTest(width=width):
                    layout = self.browser_result(
                        fixture, temporary / f"profile-{width}", width, "#view-creators"
                    )
                    for kind in ("project", "image", "pdf", "video", "audio"):
                        self.assertFalse(layout[kind]["verticalOverflow"], (width, kind, layout[kind]))
                        self.assertEqual(layout[kind]["overflowY"], "hidden")
                        self.assertEqual(layout[kind]["lines"], 3)
                        self.assertTrue(layout[kind]["clamped"])
                    self.assertEqual(layout["tooltip"], {
                        "visible": True,
                        "full": True,
                        "hiddenAfterLeave": True,
                        "visibleOnKeyboardFocus": True,
                        "visibleAfterKeyboardScroll": True,
                        "hiddenOnTouch": True,
                    })
                    self.assertEqual(layout["overview"]["clamp"], "none")
                    self.assertEqual(layout["collaboration"], {
                        "verticalOverflow": False,
                        "fullCredit": True,
                        "ellipsized": True,
                    })
                    self.assertEqual(layout["lightbox"], {
                        "full": True,
                        "wrapped": True,
                        "fixed": True,
                    })
                    self.assertEqual(layout["grouped"], {
                        "count": 2,
                        "portrait": True,
                        "initial": "B",
                        "circular": True,
                    })

    def test_catalog_defaults_to_projects_and_switches_views(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "source"
            for index in range(121):
                (source / "Creator A" / f"Book {index:03d}").mkdir(parents=True)
            (source / "Creator B" / "Alpha").mkdir(parents=True)
            (source / "Creator C").mkdir()
            output = temporary / "site"
            self.assertEqual(
                main([str(source), str(output), "--quiet"]),
                0,
            )
            index = output / "index.html"
            probe = '''<pre id="result"></pre><script>
window.addEventListener("DOMContentLoaded", () => {
  const list = document.querySelector("[data-catalog-creator-list]");
  const grid = document.querySelector("[data-catalog-project-grid]");
  const projectsButton = document.querySelector('[data-catalog-view="projects"]');
  const creatorsButton = document.querySelector('[data-catalog-view="creators"]');
  const letter = (value) => document.querySelector(`[data-catalog-alphabet] [data-initial="${value}"]`);
  const cards = () => [...grid.querySelectorAll(".project-overview-card")];
  const names = () => [...list.querySelectorAll(".grouped-creator-copy h2")].map((title) => title.textContent);
  const result = {};
  if (window.location.hash === "#view-creators") {
    result.deepLink = {
      creatorView: creatorsButton.getAttribute("aria-pressed") === "true",
      creators: names(),
      projectsHidden: grid.hidden,
    };
  } else {
    result.initial = {
      projectView: projectsButton.getAttribute("aria-pressed") === "true",
      count: cards().length,
      creatorsHidden: list.hidden,
      summary: document.querySelector(".overview-header .summary").innerText.trim(),
      creatorLetterHidden: letter("C").hidden,
      projectLetterVisible: !letter("A").hidden,
    };
    creatorsButton.click();
    result.creators = {
      hash: window.location.hash,
      creators: names(),
      projectsHidden: grid.hidden,
      creatorLetterVisible: !letter("C").hidden,
      projectLetterHidden: letter("A").hidden,
    };
    projectsButton.click();
    result.projects = {
      hash: window.location.hash,
      count: cards().length,
      firstTitle: cards()[0].querySelector(".overview-title").textContent,
      firstCreator: cards()[0].querySelector(".overview-meta").textContent,
      creatorRowsRemoved: list.hidden && list.children.length === 0,
      projectCount: document.querySelector("#visible-items").textContent,
      extraSummaryHidden: document.querySelector("[data-catalog-extra-summary]").hidden,
      status: document.querySelector("[data-catalog-status]").textContent,
      creatorLetterHidden: letter("C").hidden,
      projectLetterVisible: !letter("A").hidden,
    };
    document.querySelector("[data-catalog-next]").click();
    result.nextPage = {
      count: cards().length,
      status: document.querySelector("[data-catalog-status]").textContent,
    };
    letter("A").click();
    result.letterFilter = {
      count: cards().length,
      title: cards()[0].querySelector(".overview-title").textContent,
      paginationHidden: document.querySelector("[data-catalog-pagination]").hidden,
    };
    const search = document.querySelector("#catalog-search");
    search.value = "Creator B";
    search.dispatchEvent(new Event("input", {bubbles: true}));
    window.setTimeout(() => {
      result.search = {
        count: cards().length,
        title: cards()[0].querySelector(".overview-title").textContent,
      };
      creatorsButton.click();
      result.backToCreators = {
        hash: window.location.hash,
        search: search.value,
        creators: names(),
        projectGridHidden: grid.hidden && grid.children.length === 0,
        allLetterSelected: letter("").classList.contains("current"),
        creatorLetterVisible: !letter("C").hidden,
        projectLetterHidden: letter("A").hidden,
        summary: document.querySelector(".overview-header .summary").textContent.trim(),
      };
      document.querySelector("#result").textContent = JSON.stringify(result);
    }, 180);
    return;
  }
  document.querySelector("#result").textContent = JSON.stringify(result);
});
</script>'''
            index.write_text(
                index.read_text(encoding="utf-8").replace("</body>", probe + "</body>"),
                encoding="utf-8",
            )

            result = self.browser_result(index, temporary / "profile-switch", 1280)
            self.assertEqual(result["initial"], {
                "projectView": True,
                "count": 120,
                "creatorsHidden": True,
                "summary": "122 projects",
                "creatorLetterHidden": True,
                "projectLetterVisible": True,
            })
            self.assertEqual(result["creators"], {
                "hash": "#view-creators",
                "creators": ["Creator A", "Creator B", "Creator C"],
                "projectsHidden": True,
                "creatorLetterVisible": True,
                "projectLetterHidden": True,
            })
            self.assertEqual(result["projects"], {
                "hash": "#view-projects",
                "count": 120,
                "firstTitle": "Alpha",
                "firstCreator": "Creator B",
                "creatorRowsRemoved": True,
                "projectCount": "122",
                "extraSummaryHidden": True,
                "status": "Page 1 of 2",
                "creatorLetterHidden": True,
                "projectLetterVisible": True,
            })
            self.assertEqual(result["nextPage"], {
                "count": 2,
                "status": "Page 2 of 2",
            })
            self.assertEqual(result["letterFilter"], {
                "count": 1,
                "title": "Alpha",
                "paginationHidden": True,
            })
            self.assertEqual(result["search"], {"count": 1, "title": "Alpha"})
            self.assertEqual(result["backToCreators"], {
                "hash": "#view-creators",
                "search": "Creator B",
                "creators": ["Creator B"],
                "projectGridHidden": True,
                "allLetterSelected": True,
                "creatorLetterVisible": True,
                "projectLetterHidden": True,
                "summary": "1 creator · 1 project",
            })
            deep_link = self.browser_result(
                index, temporary / "profile-deep-link", 1280, "#view-creators"
            )
            self.assertEqual(deep_link["deepLink"], {
                "creatorView": True,
                "creators": ["Creator A", "Creator B", "Creator C"],
                "projectsHidden": True,
            })

    def test_shared_project_is_listed_per_creator_but_once_globally(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "source"
            (source / "Artist A").mkdir(parents=True)
            (source / "Artist B").mkdir()
            (source / "Artist A & Artist B" / "Shared Album").mkdir(parents=True)
            output = temporary / "site"
            self.assertEqual(
                main([str(source), str(output), "--link-collaborations", "--quiet"]),
                0,
            )
            index = output / "index.html"
            probe = '''<pre id="result"></pre><script>
window.addEventListener("DOMContentLoaded", () => {
  const grid = document.querySelector("[data-catalog-project-grid]");
  const list = document.querySelector("[data-catalog-creator-list]");
  const summary = () => document.querySelector(".overview-header .summary").innerText.trim();
  const cards = [...grid.querySelectorAll(".project-overview-card")];
  const result = {
    allProjects: {
      count: cards.length,
      credit: cards[0].querySelector(".overview-meta").textContent,
      summary: summary(),
    },
  };
  document.querySelector('[data-catalog-view="creators"]').click();
  result.byCreator = {
    summary: summary(),
    sections: [...list.querySelectorAll(".grouped-creator")].map((section) => {
      const row = section.querySelector(".project-row");
      return {
        name: section.querySelector("h2").textContent,
        count: row._railData.length,
        title: row._railData[0].title,
        credit: row._railData[0].meta || null,
        renderedCredit: row.querySelector(".project-card .overview-meta")?.textContent || null,
        expandedTrack: row.classList.contains("collaboration-row"),
      };
    }),
  };
  document.querySelector("#result").textContent = JSON.stringify(result);
});
</script>'''
            index.write_text(
                index.read_text(encoding="utf-8").replace("</body>", probe + "</body>"),
                encoding="utf-8",
            )

            result = self.browser_result(index, temporary / "profile-shared", 1280)
            self.assertEqual(result["allProjects"], {
                "count": 1,
                "credit": "Artist A & Artist B",
                "summary": "1 project",
            })
            self.assertEqual(result["byCreator"], {
                "summary": "3 creators · 1 project",
                "sections": [
                    {"name": "Artist A", "count": 1, "title": "Shared Album", "credit": "Artist A & Artist B", "renderedCredit": "Artist A & Artist B", "expandedTrack": True},
                    {"name": "Artist A & Artist B", "count": 1, "title": "Shared Album", "credit": None, "renderedCredit": None, "expandedTrack": False},
                    {"name": "Artist B", "count": 1, "title": "Shared Album", "credit": "Artist A & Artist B", "renderedCredit": "Artist A & Artist B", "expandedTrack": True},
                ],
            })
