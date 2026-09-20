# utils

A collection of small, focused utility scripts organized by purpose. Utilities
may target different platforms and use different languages; each category keeps
its detailed documentation close to its scripts.

## Repository structure

```text
scripts/
├── filesystem/
│   ├── create-link-collection/    Relative-link collection generator
│   └── directory-gallery/         Static directory gallery generator
└── system/                         System administration utilities
```

## Available utilities

| Utility | Purpose | Platforms |
| --- | --- | --- |
| [`create-link-collection.py`](scripts/filesystem/create-link-collection/README.md) | Build a flat collection of relative links from a `GROUP/ITEM` hierarchy | Linux, Windows |
| [`directory-gallery`](scripts/filesystem/directory-gallery/README.md) | Build a dark, multi-page media catalog from a `CREATOR/PROJECT` hierarchy | Linux, Windows |
| [`update-apt.sh`](scripts/system/README.md) | Update packages on a Debian-based system | Linux |

## Conventions

- Utilities live in a purpose-based directory under `scripts/`.
- Names identify a platform or tool when that dependency matters.
- Category READMEs contain usage and platform-specific guidance.
- Specifications and tests are colocated with utilities that have non-trivial
  behavior.
- Utilities should avoid third-party runtime dependencies unless they provide a
  clear benefit.

## License

This project is licensed under the GNU General Public License v3.0. See
[`LICENSE`](LICENSE) for details.
