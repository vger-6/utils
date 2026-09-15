# Create Link Collection specification

Status: accepted for version 1.0

This document is the authoritative behavioral contract for
`create-link-collection.py`. The category README and command-line help summarize
this specification.

## Terminology and source model

- The utility is domain-neutral.
- The source hierarchy is `ROOT/GROUP/ITEM`.
- Artist/album, author/book, and director/movie are examples of group/item
  relationships, not special modes.
- Only real directories exactly two levels below the root are items.
- Files and directories below an item are ignored.
- Symbolic links encountered at the group or item level are ignored and never
  followed.
- The source hierarchy is not modified except when the user explicitly places
  the requested output within it.

## Command-line interface

- `--root PATH` is required and identifies the source root.
- `--output PATH` is required and identifies the new output directory.
- `--exclude PATTERN` is optional and repeatable; each occurrence accepts one
  pattern.
- `--dry-run` performs discovery and validation without creating anything.
- `--help` describes every argument and provides exclusion examples.
- Options may not be abbreviated.
- Root and output paths may be absolute or relative.
- Paths use the host operating system's native syntax.
- The output may be inside or outside the root.
- Missing parents of a new output are created automatically.

## Output existence

- Output existence is checked immediately after argument parsing and path
  normalization, before source validation or discovery.
- If the output is an existing directory, the utility prints an explanatory
  message, changes nothing, and exits with status `0`.
- The existing directory is not inspected, updated, or required to contain a
  collection marker.
- If the output path exists but is not a directory, the utility changes nothing
  and exits with status `1`.

## Discovery and exclusions

- Candidates are discovered only as `ROOT/GROUP/ITEM`.
- Discovery and reporting use deterministic, case-insensitive name ordering
  with the original case as a tie-breaker.
- Exclusion matching itself is case-sensitive on every operating system.
- Patterns are evaluated against the logical `GROUP/ITEM` path.
- `/` is the pattern separator on Linux and Windows.
- Backslashes in patterns are rejected to keep pattern syntax platform-neutral.
- A pattern without `/` matches the item component only.
- A pattern with `/` contains exactly one group pattern and one item pattern.
- `*` matches zero or more characters within one component.
- `?` matches exactly one character within one component.
- Character classes supported by Python's `fnmatch` syntax are supported.
- Wildcards never cross the `/` between group and item.
- `**`, empty patterns, empty components, and patterns with more than two
  components are rejected with status `1`.
- If any pattern matches a candidate, that candidate is excluded.
- `--include` is not supported.

Examples:

- `--exclude "_misc"` excludes every item named `_misc`.
- `--exclude "*/ExcludeThis"` excludes that item name under every group.
- `--exclude "Nia Solen/Static Garden"` excludes one specific item.
- `--exclude "Nia Solen/*"` excludes all items in that group.

## Link planning

- One directory symbolic link is planned for every eligible item.
- Each link is named `GROUP - ITEM`.
- Each target is relative to the output directory.
- Absolute link targets, Windows shortcuts, and directory junctions are not
  used.
- All plans are computed before the output directory is created.
- Generated link components are checked against host filesystem naming limits
  where those limits are available.
- Generated link-name collisions are detected before output creation.
- Windows collision detection is case-insensitive; Linux collision detection is
  case-sensitive.
- A collision report identifies both source items and the generated name.
- A collision or invalid relative target exits with status `1` and creates
  nothing.

## Empty results and dry runs

- If no eligible items remain, the utility prints an explanatory message, does
  not create the output, and exits with status `0`.
- A dry run prints the output location, every generated link name and relative
  target, and the collection marker.
- A dry run creates no directories, files, or links and exits with status `0`.

## Collection marker

- A successful output contains a `.link-collection` JSON file.
- The marker records the format version, generator name, utility version, and
  normalized source root.
- A candidate group or item containing `.link-collection` is treated as a
  previously generated output and skipped completely.
- The current output path is also excluded from discovery as a safeguard.
- The marker permits differently named generated outputs to coexist beneath one
  root without being rediscovered.

## Creation and rollback

- The output is created only after discovery, exclusions, and preflight
  validation succeed.
- Links are created as directory symbolic links.
- The marker is written only after every link succeeds.
- Successful completion reports the number of links created and exits with
  status `0`.
- If link or marker creation fails, the utility attempts to remove every link,
  marker, and output directory created during that run.
- Rollback never recursively deletes the output; it removes only entries the
  utility attempted to create and then removes the empty output directory.
- Pre-existing paths and source items are never removed.
- A filesystem or validation failure exits with status `1`.
- An interruption rolls back the current output and exits with status `130`.
- A rollback problem is included in the error message.

## Platform requirements

- The implementation uses Python 3.8 or later and only the standard library.
- Linux and Windows are supported.
- On Windows, root and output must be on the same drive because the targets are
  relative.
- Windows must permit symbolic-link creation, normally through Developer Mode or
  an elevated process.
- Failure to obtain symbolic-link permission triggers normal rollback.
- Relative links may become invalid if the source or output is moved
  independently after creation.

## Exit statuses

- `0`: collection created, dry run completed, output already existed as a
  directory, or no eligible items were found
- `1`: validation or filesystem failure
- `2`: command-line parsing failure
- `130`: user interruption

## Non-goals for version 1.0

- Recursive item discovery beyond `ROOT/GROUP/ITEM`
- Include rules or ordered include/exclude filters
- Updating, merging, cleaning, or replacing an existing output
- Absolute symbolic links
- Copying source data
- Creating Windows shortcuts or junctions
- Installing a global command or publishing a Python package

## Acceptance coverage

The colocated test suite verifies:

- generic group/item discovery and `GROUP - ITEM` naming
- relative target calculation
- nested-directory exclusion by structural depth
- item-name and group/item exclusion patterns
- case-sensitive pattern behavior
- rejection of unsupported patterns
- existing output no-op behavior
- non-directory output errors
- empty-result behavior
- dry-run behavior
- generated collection marker creation and rediscovery prevention
- generated-name collision handling
- rollback after link failure
- source symbolic-link avoidance when the host permits symlink setup
