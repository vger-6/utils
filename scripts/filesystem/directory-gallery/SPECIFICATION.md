# Directory Gallery specification

Status: implemented for version 0.8.0

## Source model

- The input hierarchy is `INPUT/CREATOR/PROJECT`.
- Every visible, real immediate child directory of the input is a creator.
- A creator is included even when it has no projects, artwork, README, or
  supported media.
- Every visible, real immediate child directory of a creator is a project except
  the exact lowercase reserved name `meta`.
- Symbolic-link and dot-prefixed directories are ignored and never followed.
- Creator and project display names are their directory names.
- The source hierarchy is never modified.

## Reserved creator content

- `CREATOR/meta` is never a project and never appears in the catalog project grid.
- Allowed files directly in a creator are scanned without entering projects.
- `meta` is scanned recursively without a depth limit.
- Media directly in `meta` merges with direct creator media of the same type.
- A directory below `meta` creates a separate row identified by its path
  relative to `meta`.
- `meta/README.md` is not rendered.

## Role artwork

- Creator artwork is selected only directly from the creator directory.
- Accepted portrait names, in priority order, are `portrait.jpg`,
  `portrait.jpeg`, and `portrait.png`.
- Project artwork is first selected directly from the project directory using
  `cover.jpg`, `cover.jpeg`, and `cover.png` in that order.
- When a direct cover exists, nested directories are not searched for covers.
- When no direct cover exists, visible real project subdirectories are searched
  breadth-first: shallowest depth first, alphabetical relative path within a
  depth, then JPG, JPEG, PNG within each directory.
- During recursive fallback, the first candidate wins and every discovered
  cover candidate is reserved from media rows.
- Multiple candidates considered by a selection produce a catalog notice.
- Missing or unreadable role artwork uses an HTML/CSS placeholder.
- Role matching is exact and case-sensitive.

## Media discovery

- Project media is scanned recursively without a depth limit.
- Hidden files, hidden directories, symbolic-link files, and symbolic-link
  directories are ignored.
- Extension classification is case-insensitive.
- Allowed images are JPG, JPEG, PNG, WebP, GIF, and AVIF.
- The only allowed document format is PDF.
- Allowed video formats are MP4, M4V, WebM, OGV, MOV, and MKV.
- Allowed audio formats are MP3, M4A, AAC, OGG, OGA, Opus, WAV, and FLAC.
- Unsupported files are absent from generated pages.
- Media is grouped into homogeneous rows; types are never mixed in a row.
- Rows are ordered images, PDFs, videos, and audio. Within a type, root media
  comes first and subdirectory rows follow in alphabetical path order.
- Items within a row are ordered alphabetically by filename.
- Animated image originals remain animated in the lightbox; generated JPEG
  thumbnails may contain only the first frame.

## Video posters

- A video poster is an adjacent file using the video stem and one of
  `.poster.jpg`, `.poster.jpeg`, or `.poster.png`, in that order.
- A matched poster is omitted from image rows.
- A video without a poster uses a generic tile.
- Project covers are never used as video posters.
- Audio and video are not transcoded; playback depends on browser codec support.

## README rendering

- Only exact, direct `README.md` files on creators and projects are rendered.
- Markdown uses CommonMark with raw HTML disabled.
- HTTP, HTTPS, and mail links remain active.
- Relative links are enabled only when they remain within the creator/project
  boundary, resolve to a regular file, and target an allowed media extension.
- Relative images additionally must target an allowed image extension.
- Invalid or disallowed relative links are disabled.
- README text is embedded at generation time and does not require browser-side
  filesystem access.
- Detail pages show short rendered READMEs in full. READMEs taller than the
  roughly 350px preview start collapsed behind a fade with an accessible
  Show more/Show less control. The rendered height, including images, determines
  whether the control appears. Without JavaScript, all README content remains
  visible.

## Generated interface

- The interface has a dark theme only and no external runtime dependencies.
- `index.html` is always the catalog. Its default All projects view shows a
  cover, title, and creator grid. The By creator switch stacks creators
  vertically, with each creator's projects in a horizontal row.
- A separate portrait-based creator grid is generated as `creators.html` by
  default. `--no-creator-grid` omits it; no `projects.html` is generated.
- Catalog view selection is reflected in the URL hash (`#view-creators` or
  `#view-projects`) for bookmarking and browser history. Switching retains the
  search query, resets the alphabet filter and page number, and changes the
  alphabet to the active view's initials.
- By creator headings contain a circular portrait and name. If no portrait
  is available, the circle shows the creator's first alphanumeric initial.
- Creator and project detail pages are always generated. Catalog navigation and
  detail-page breadcrumbs return to `index.html`; the creator grid is linked
  only when generated.
- Overview ordering is deterministic and alphabetical; there are no sorting
  controls.
- Overview search and initial filters operate over the full embedded data set.
- Catalog search matches creator and project names. In By creator view, when
  only project names match, the creator remains visible with only its matching
  projects. In All projects view, matching a creator shows that creator's
  projects.
- The creator grid paginates 120 cards at a time. The catalog paginates 40
  creators or 120 projects at a time and renders only the active view.
  Horizontal rows are initialized only for creators on the current page.
- Creator cards contain portrait, name, and project count.
- In the creator grid, portrait frames use a 2:3 ratio and crop toward the
  upper part of the image. Catalog badges stay circular; creator detail
  portrait shapes are unchanged.
- Project cards contain cover, project title, and creator name.
- Creator detail pages contain portrait, name, README, projects, and creator
  media. Projects are always the first content row when present.
- Project detail pages contain cover, title, creator, README, and project media.
- Content rows scroll horizontally, expose left/right controls only when they
  overflow, and retain native touch and trackpad scrolling.
- Content rows virtualize their cards and retain only a small viewport-adjacent
  window in the DOM. The complete row metadata remains available for scrolling
  and lightbox navigation.
- Project and media card labels in horizontal rows clamp to three lines without
  vertical scrolling. Truncated names have a full-text tooltip on pointer hover
  and keyboard focus. Touch users can open the card to see the full title.
  Other page titles remain unclamped.
- Images, PDFs, videos, and audio open in a shared accessible lightbox.
- The lightbox has a stable responsive outer size for all media types. Audio
  playlists occupy space inside the viewer rather than resizing the dialog.
  Lightbox titles wrap in full, reducing media space when needed.
- Image navigation stays within the selected row and loads the original file.
  The currently displayed image remains visible until the next one is decoded;
  immediate neighbors are preloaded with a bounded in-memory cache.
- PDFs use cached first-page thumbnails and an embedded browser PDF viewer.
- Videos use an HTML video player and stop when the lightbox closes.
- Audio uses one HTML audio player plus a playlist for the selected row and
  automatically advances to the next track.
- Every lightbox supplies an `Open original` fallback.
- No directory tree, generic file listing, or direct directory link is shown.

## Command line and exclusions

- `INPUT_FOLDER` and `OUTPUT_FOLDER` are required positional arguments.
- `--exclude PATTERN` and `--exclude-from FILE` are optional and repeatable.
- Pattern files are UTF-8, one Gitignore-style pattern per line. Blank lines
  and `#` comments are ignored. A UTF-8 BOM is accepted. They are read only
  when explicitly named; relative file paths resolve from the working directory.
- Patterns from both options are expanded in command-line order. The last
  matching pattern wins, with `!` negating a previous exclusion. A child of an
  excluded directory cannot be re-included unless its parent is re-included.
- Matching is case-sensitive and relative to `INPUT_FOLDER`. A pattern without
  `/` matches a basename at any depth; leading `/` anchors to the input root;
  trailing `/` matches directories only. `*`, `?`, character classes, and `**`
  use Gitignore-style matching.
- Exclusions apply before traversing creator and project directories, and to
  nested directories, allowed media, role artwork, video posters, and READMEs.
  Local README links to excluded media are disabled. Hidden entries and
  symbolic links remain excluded independently of patterns.
- The reserved creator child `meta` is not a project and can be excluded.
- Empty inline patterns are rejected. No `.gitignore` or `.galleryignore`
  is read automatically.
- `--title TEXT` overrides the catalog title.
- `--no-creator-grid` omits the separate `creators.html` portrait grid.
- `--quiet` suppresses progress reports.
- `--version` reports the program version.
- Argument syntax errors exit with status 2, user/filesystem errors with status
  1, and interruption with status 130.

## Preview cache

- Image thumbnails and video-poster thumbnails are JPEG files bounded by 512
  by 512 pixels while preserving source aspect ratio.
- PDF previews render the first page and use the same bound.
- A cache record includes the resolved source path, preview type, size, and
  nanosecond modification time.
- An unchanged record with an existing generated file is reused.
- Preview files use `thumbnails/HH/HH/HASH.jpg`, with the first four hash
  characters split across two directory levels.
- Cache records are held in the output SQLite database and updated in bounded
  transactions.
- Changed sources are regenerated; stale database-owned previews are pruned.

## Scale behavior

- The generator scans and renders one project at a time; only the current
  project's media and one creator's project summaries are retained in memory.
- Creator/project overview records, preview records, and generated-file
  ownership are stored in SQLite and selected in deterministic order.
- Overview metadata is materialized only while its corresponding overview page
  is rendered. At expected scales of roughly 1,000 creators and 10,000
  projects, this remains modest compared with media metadata.
- Catalog project lookups use an indexed creator path and retain only
  40 creator sections in the live DOM at once.
- Catalog notices retain at most 200 detailed messages in memory and HTML while
  preserving the complete notice count.
- Progress includes creator, project, and media counts, generated/reused
  previews, elapsed time, and a creator-based ETA when one can be calculated.
- Time and disk cost remain linear in the files scanned and previews generated;
  the initial build cannot avoid reading every supported file that needs a
  preview.

## Output safety

- During active development, older output formats receive no migrations or
  compatibility shims; rebuild them in a new empty output directory.
- Input and output are resolved before generation and must be disjoint trees.
- The output must not be a symbolic link.
- A missing output and its parents are created; an empty output is accepted.
- A non-empty output requires a valid compatible manifest.
- Generated text files are replaced atomically.
- A small format-2 manifest identifies the generator, input, and SQLite state
  database. The database records overview pages, hashed creator/project pages,
  assets, and previews.
- Older manifest formats are rejected without modifying the existing output.
- Stale generated pages are removed only when recorded by the state database
  and matching a strict generator-owned path pattern.
- Stale previews are removed only when recorded by the state database and
  matching the strict sharded hashed JPEG pattern.
- Unrelated output files are never removed.
