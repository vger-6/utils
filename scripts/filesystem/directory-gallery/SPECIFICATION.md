# Directory Gallery specification

Status: implemented for version 0.1.0

## Source model

- The tool is domain-neutral.
- The input hierarchy is exactly `INPUT/CREATOR/PROJECT`.
- Only real, visible directories at the creator and project levels are scanned.
- Symbolic-link and dot-prefixed directories are ignored and never followed.
- Files and directories beneath a project do not affect discovery.
- Creator and project display names are their directory names.
- A creator with no eligible projects is omitted.
- The source hierarchy is never modified.

## Artwork

- Creator artwork is selected directly from the creator directory.
- Project artwork is selected directly from the project directory.
- Accepted creator names, in priority order, are `portrait.jpg`,
  `portrait.jpeg`, and `portrait.png`.
- Accepted project names, in priority order, are `cover.jpg`, `cover.jpeg`, and
  `cover.png`.
- Matching is exact and case-sensitive.
- When multiple accepted files exist, the highest-priority file is used and a
  notice is included in the generated catalog.
- Missing or unreadable images use an HTML/CSS placeholder.
- Image dimensions are not validated. Thumbnails preserve aspect ratio and fit
  within a 512 by 512 pixel boundary.
- Thumbnails are JPEG files generated with Pillow.

## Command line

- `INPUT_FOLDER` and `OUTPUT_FOLDER` are required positional arguments.
- `--exclude PATTERN` is optional and repeatable.
- `--title TEXT` overrides the input-directory name in the page heading.
- `--version` reports the program version.
- Options may not be abbreviated.
- Invalid command syntax exits with status `2`.
- User and filesystem errors exit with status `1`.
- An interruption exits with status `130`.

## Exclusions

- Patterns are case-sensitive on every platform.
- A pattern without `/` matches project names only.
- A pattern with `/` contains one creator pattern and one project pattern.
- `*`, `?`, and Python `fnmatch` character classes are supported inside each
  component.
- Wildcards never cross the `/` separator.
- Backslashes, `**`, empty patterns, empty components, and patterns with more
  than two components are rejected.
- A project matching any supplied pattern is excluded.

## Output safety

- Input and output are resolved before generation.
- Input and output must be disjoint directory trees.
- The output must not be a symbolic link.
- A missing output and its parents are created.
- An empty output is accepted.
- A non-empty output is accepted only when it contains a valid, compatible
  `.directory-gallery-manifest.json` as a regular file.
- The generator writes `index.html`, files under `assets/`, thumbnails under
  `thumbnails/`, and its manifest.
- Text files and the manifest are replaced atomically.
- Only stale thumbnail filenames recorded by a previous valid manifest and
  matching the generator's strict hashed-name format are removed.
- Unrelated output files are never removed.

## Cache

- A source image maps to a stable filename derived from its resolved path.
- The manifest records the source size and nanosecond modification time.
- A thumbnail is reused when its record and generated file are unchanged.
- Changed images are regenerated.
- Removed or superseded artwork causes its previously recorded thumbnail to be
  pruned on the next successful run.
- An invalid or incompatible manifest causes generation to stop before the
  existing output is modified.

## Static interface

- The generated interface has a dark theme only.
- Creators are stacked vertically.
- Projects are displayed horizontally and wrap responsively.
- Creator names and portraits link to creator directories.
- Project titles and covers link to project directories.
- No source document or media file is linked directly.
- Links are relative when the host platform permits and otherwise use absolute
  file URIs.
- The interface provides creator/project search, alphabetical navigation,
  visible counts, placeholders, notices, and lazy-loaded images.
- The output uses plain HTML, CSS, and JavaScript with no runtime server or
  external network resources.
