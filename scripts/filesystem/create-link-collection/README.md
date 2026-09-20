# Create link collection

Cross-platform utilities for organizing files and directories.

## `create-link-collection.py`

Creates a flat directory of relative symbolic links from a hierarchy shaped as:

```text
ROOT/
└── GROUP/
    └── ITEM/
```

The terminology is deliberately generic. A group and item can represent an
artist and album, an author and book, a director and movie, or another two-level
collection.

Given this source:

```text
Musicians/
├── Astra Vey/
│   └── Glass Circuit/
└── Nia Solen/
    └── Static Garden/
```

the utility creates links named `GROUP - ITEM`:

```text
_All/
├── Astra Vey - Glass Circuit -> ../Astra Vey/Glass Circuit
└── Nia Solen - Static Garden -> ../Nia Solen/Static Garden
```

Directories below the item level, such as `Glass Circuit/extras`, are ignored.

### Requirements

- Python 3.8 or later
- Linux or Windows
- Permission to create symbolic links

On Windows, symbolic-link creation usually requires Developer Mode or an
elevated terminal. The root and output must be on the same drive because link
targets are relative.

### Usage

From the repository root on Linux:

```bash
python3 scripts/filesystem/create-link-collection/create-link-collection.py \
  --root "/music/Musicians" \
  --output "/music/Musicians/_All"
```

From PowerShell on Windows:

```powershell
py scripts/filesystem/create-link-collection/create-link-collection.py `
  --root "C:\Musicians" `
  --output "C:\Musicians\_All"
```

Paths may be absolute or relative and use the operating system's normal path
syntax. The output may be inside or outside the root.

If the output directory already exists, the utility prints a message and makes
no changes. It never updates or replaces an existing collection.

### Exclusions

Use one repeatable `--exclude PATTERN` option per exclusion:

```bash
python3 scripts/filesystem/create-link-collection/create-link-collection.py \
  --root "/music/Musicians" \
  --output "/music/Musicians/_All" \
  --exclude "_misc" \
  --exclude "Nia Solen/Static Garden"
```

Patterns are matched case-sensitively against the logical `GROUP/ITEM` path.
Always use `/` between group and item in a pattern, including on Windows.
Backslashes in patterns are rejected with an explanatory error.

- A pattern without `/` matches item names only: `_misc`.
- A full path selects one item: `Nia Solen/Static Garden`.
- A wildcard group selects that item name everywhere: `*/ExcludeThis`.
- A wildcard item selects every item in a group: `Nia Solen/*`.
- `*` matches zero or more characters within one component.
- `?` matches one character within one component.
- Character classes such as `[abc]` are supported.
- `**` is not supported because discovery is exactly two levels deep.

### Previewing changes

Use `--dry-run` to perform discovery and validation and print every proposed
link without creating the output directory:

```bash
python3 scripts/filesystem/create-link-collection/create-link-collection.py \
  --root "/music/Musicians" \
  --output "/music/Musicians/_All" \
  --dry-run
```

### Generated collection marker

Each output contains a `.link-collection` JSON marker recording the format,
generator, version, and source root. When a later run scans the same root, any
group or item containing this marker is recognized as a generated collection
and skipped.

This allows multiple outputs to coexist safely inside one root:

```text
Musicians/
├── Astra Vey/
├── _All Albums/
│   └── .link-collection
└── _All/
    └── .link-collection
```

Source symbolic links are also ignored and never followed.

### Safety and exit behavior

Before creating the output, the utility validates the source, patterns, link
names, collisions, and relative targets. If link creation fails, it removes the
links and output directory created during that run.

The utility exits with:

- `0` after successful creation, a dry run, an existing-output no-op, or an
  empty result
- `1` for validation or filesystem errors
- `2` for invalid command-line syntax
- `130` when interrupted

The complete behavioral contract is in
[`create-link-collection.specification.md`](create-link-collection.specification.md).

### Tests

Run the colocated standard-library test suite from the repository root:

```bash
python3 -m unittest discover \
  -s scripts/filesystem/create-link-collection/tests \
  -v
```
