from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


RESOURCES = Path(__file__).resolve().parents[1] / "src" / "directory_gallery" / "resources"
CHROMIUM = shutil.which("chromium") or shutil.which("chromium-browser")


@unittest.skipUnless(CHROMIUM, "Chromium is needed for the optional layout test")
class FrontendTests(unittest.TestCase):
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

        document = f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="{(RESOURCES / 'gallery.css').as_uri()}">
<body><main class="site-main">{''.join(rows)}
<div class="overview-card" style="width:180px"><span class="overview-title">{html.escape(name)}</span></div>
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
const dialog = document.querySelector("#dialog");
const lightboxTitle = document.querySelector("#lightbox-title");
results.lightbox = {{
  full: lightboxTitle.scrollHeight === lightboxTitle.clientHeight,
  wrapped: lightboxTitle.clientHeight > parseFloat(getComputedStyle(lightboxTitle).lineHeight),
  fixed: Math.round(dialog.getBoundingClientRect().height) === 300,
}};
document.querySelector("#result").textContent = JSON.stringify(results);
</script></body></html>'''

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            fixture = temporary / "layout.html"
            fixture.write_text(document, encoding="utf-8")
            for width in (1280, 500):
                with self.subTest(width=width):
                    try:
                        result = subprocess.run(
                            [
                                CHROMIUM,
                                "--headless",
                                "--no-sandbox",
                                "--disable-gpu",
                                "--disable-dev-shm-usage",
                                f"--user-data-dir={temporary / f'profile-{width}'}",
                                f"--window-size={width},900",
                                "--virtual-time-budget=1000",
                                "--dump-dom",
                                fixture.as_uri(),
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
                    layout = json.loads(html.unescape(match.group(1)))
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
                    self.assertEqual(layout["lightbox"], {
                        "full": True,
                        "wrapped": True,
                        "fixed": True,
                    })
