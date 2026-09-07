# utils

A collection of small, focused utility scripts organized by purpose.

## Repository structure

```text
scripts/
└── system/    System administration and maintenance utilities
```

New scripts should be placed in a purpose-based directory under `scripts/` and
named after the tool or platform they target when that dependency matters.

## Available scripts

### `scripts/system/update-apt.sh`

Updates a Debian-based system using `apt-get`. The script refreshes package
lists, upgrades installed packages, removes packages that are no longer needed,
and cleans the local package cache.

Requirements:

- Bash
- A Debian-based Linux distribution with `apt-get`
- Root privileges

Run interactively:

```bash
sudo ./scripts/system/update-apt.sh
```

Automatically confirm package upgrades and removals:

```bash
sudo ./scripts/system/update-apt.sh --yes
```

Show command-line help without making system changes:

```bash
./scripts/system/update-apt.sh --help
```

> [!CAUTION]
> This script changes installed system packages. Review pending changes before
> confirming them, and use `--yes` only when unattended confirmation is intended.

The script stops on the first failed command and prints its success message only
after every maintenance step completes.

## License

This project is licensed under the GNU General Public License v3.0. See
[`LICENSE`](LICENSE) for details.
