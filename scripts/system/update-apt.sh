#!/usr/bin/env bash

set -Eeuo pipefail

usage() {
    printf '%s\n' \
        "Usage: ${0##*/} [--yes]" \
        "" \
        "Refresh package lists, upgrade installed packages, remove unused packages," \
        "and clean the package cache on a Debian-based system." \
        "" \
        "Options:" \
        "  -y, --yes  Automatically confirm upgrade and removal prompts" \
        "  -h, --help  Show this help message"
}

log() {
    printf '\n==> %s\n' "$1"
}

assume_yes=false

while (($# > 0)); do
    case "$1" in
        -y|--yes)
            assume_yes=true
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Error: unknown option: %s\n\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

if ((EUID != 0)); then
    printf 'Error: run this script as root, for example:\n  sudo %s\n' "$0" >&2
    exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
    printf 'Error: apt-get was not found. This script supports Debian-based systems only.\n' >&2
    exit 1
fi

trap 'printf "Error: system update failed near line %s.\n" "$LINENO" >&2' ERR

apt_options=()
if [[ "$assume_yes" == true ]]; then
    apt_options+=(--yes)
fi

log "Refreshing package lists"
apt-get update

log "Upgrading installed packages"
apt-get upgrade "${apt_options[@]}"

log "Removing unused packages"
apt-get autoremove "${apt_options[@]}"

log "Cleaning the package cache"
apt-get clean

log "System update completed successfully"
