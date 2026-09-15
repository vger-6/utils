# System utilities

System administration and maintenance scripts.

## `update-apt.sh`

Updates a Debian-based system using `apt-get`. The script refreshes package
lists, upgrades installed packages, removes packages that are no longer needed,
and cleans the local package cache.

### Requirements

- Bash
- A Debian-based Linux distribution with `apt-get`
- Root privileges

### Usage

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
