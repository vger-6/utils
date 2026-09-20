# Directory Gallery

Directory Gallery generates a modern, dark, static media catalog from a
creator/project directory tree. It builds overview grids, dedicated creator and
project pages, cached previews, homogeneous media rows, and local lightbox
viewers without changing the source collection.

```text
INPUT/
└── Creator/
    ├── portrait.jpg
    ├── README.md
    ├── meta/
    │   ├── artist-photo.jpg
    │   └── Interviews/
    │       └── interview.mp4
    └── Project/
        ├── cover.jpg
        ├── README.md
        ├── document.pdf
        ├── recording.m4a
        ├── video.mp4
        ├── video.poster.jpg
        └── Scans/
            └── page-01.png
```

Every visible real directory directly below the input is a creator. Every
visible real child directory of a creator is a project except the exact
lowercase name `meta`, which contains recursive creator-level media. A creator
is included even when it has no projects or supported media.

## Requirements

- Python 3.9 or later
- Pillow for image thumbnails
- PyMuPDF for first-page PDF previews
- markdown-it-py for safe Markdown rendering

Install in a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Usage

```bash
directory-gallery INPUT_FOLDER OUTPUT_FOLDER
```

Large builds report creators, projects, media, preview reuse, elapsed time, and
an estimated completion time on standard error. Suppress those reports when
running from a script:

```bash
directory-gallery INPUT_FOLDER OUTPUT_FOLDER --quiet
```

Use a custom catalog title:

```bash
directory-gallery INPUT_FOLDER OUTPUT_FOLDER --title "My collection"
```

Exclude projects with repeatable, case-sensitive patterns:

```bash
directory-gallery INPUT_FOLDER OUTPUT_FOLDER \
  --exclude Drafts \
  --exclude "Creator A/Archive" \
  --exclude "Creator B/*"
```

A pattern without `/` matches project names. A pattern with `/` matches a
creator/project pair. `*`, `?`, and character classes work within one path
component. `**`, backslashes, and empty components are rejected. The reserved
`meta` directory is never a project and does not need an exclusion.

Open `OUTPUT_FOLDER/index.html` locally in a browser after generation. Media
remains in the source collection, so the catalog is intended for local
`file://` use. Browser support for a particular audio or video file still
depends on the codecs installed in that browser.

## Pages and navigation

- `index.html` is a searchable creator grid using portrait cards.
- `projects.html` is a searchable global project grid using cover cards.
- Overview grids show at most 120 cards per page. Search and initial filters
  still operate over the complete catalog.
- Every creator has a dedicated page with its portrait, exact `README.md`, a
  project row, and allowed creator media.
- Every project has a dedicated page with its cover, exact `README.md`, and
  recursively discovered media.
- Project and media rows scroll horizontally using arrow buttons, touch,
  trackpads, or native horizontal scrolling.
- Horizontal rows render only cards near the visible viewport. Lightbox
  previous/next navigation still covers every item in the row.
- Rows are ordered by media type: images, PDFs, videos, then audio. Root content
  precedes alphabetically ordered subdirectory rows within each type.
- Clicking an image, PDF, video, or audio item opens the shared lightbox. Audio
  rows become playlists and continue automatically to the next track.

No generic filesystem listing is generated. Unsupported files never appear.

## Artwork conventions

Creator portraits are selected directly from the creator directory, in order:

1. `portrait.jpg`
2. `portrait.jpeg`
3. `portrait.png`

Project covers are selected directly from the project directory in the same
JPG, JPEG, PNG order. Only when no direct cover exists are visible real
subdirectories searched recursively. The shallowest directory wins, relative
paths are considered alphabetically, and extension priority applies within a
directory. All cover candidates encountered during a recursive fallback are
reserved and omitted from image rows.

Video posters use the video stem followed by `.poster`:

```text
interview.mp4
interview.poster.jpg
```

JPEG and PNG are fallbacks. A missing poster produces a generic video tile;
project covers are never reused as video posters. Matched poster files and
selected role artwork are not repeated in media rows.

## Allowed media

Ordinary media extensions are matched case-insensitively.

| Type | Extensions |
| --- | --- |
| Images | `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`, `.avif` |
| Documents | `.pdf` |
| Video | `.mp4`, `.m4v`, `.webm`, `.ogv`, `.mov`, `.mkv` |
| Audio | `.mp3`, `.m4a`, `.aac`, `.ogg`, `.oga`, `.opus`, `.wav`, `.flac` |

Animated GIF and WebP originals remain animated in the lightbox. Their cached
card thumbnails may use a static first frame. The generator does not transcode
audio or video.

## Creator media and `meta`

Allowed files directly inside a creator directory appear on the creator page.
The exact immediate child `meta` is scanned recursively and never becomes a
project. Media at the root of `meta` merges with direct creator media; nested
content produces rows such as `Images · Press Photos`.

Only `Creator/README.md` is rendered for a creator. A `README.md` inside `meta`
is not rendered. Unsupported files such as JSON, TXT, archives, and executables
are ignored wherever they occur.

## Markdown

Only the exact, case-sensitive name `README.md` is recognized directly inside
a creator or project. CommonMark is rendered with raw HTML disabled. External
HTTP, HTTPS, and mail links remain active. Relative links are rewritten only
when they stay inside the creator or project and target an allowed media file;
other relative links are disabled.

## Large collections

Generation is streamed one project at a time. Creator and project summaries,
preview metadata, and generated-file ownership are stored in SQLite instead of
being retained in a large in-memory manifest. This keeps generator memory tied
mainly to the largest individual project rather than to the entire collection.

Overview pagination and virtualized horizontal rows bound the number of cards
in the browser DOM. The complete lightweight metadata for the current overview
or row remains embedded in its page, so local search and lightbox navigation do
not require a web server. Catalog notices keep a representative sample of 200
messages while still reporting the complete count.

The first build must still inspect every supported file and create every image
or PDF preview. For very large collections, that work and the resulting disk
usage are inherently proportional to the media count. Later builds reuse
unchanged previews, but they still scan the source tree so additions and
removals are detected.

## Output and cache safety

The output contains the two overview pages, hashed creator/project pages,
shared CSS and JavaScript, cached previews, a small
`.directory-gallery-manifest.json`, and a
`.directory-gallery-cache.sqlite3` state database. Image thumbnails and PDF
previews are updated incrementally using source paths, sizes, and modification
times. Preview files are split across two levels of hash-prefix directories so
no single cache directory becomes excessively large.

Outputs made by version 0.2 are upgraded automatically on the next successful
build. Existing valid previews are moved into the sharded layout and reused;
the source collection is not touched.

The output must be empty or already managed by Directory Gallery. Input and
output trees may not overlap. Stale pages and thumbnails are removed only when
they were recorded by a compatible manifest and match the generator's strict
filename patterns. Unrelated output files and all source files remain untouched.

## Development

Run the tests after installing the project:

```bash
python3 -m unittest discover -s tests -v
```

The complete behavioral contract is in
[`SPECIFICATION.md`](SPECIFICATION.md).
