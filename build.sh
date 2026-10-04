#!/usr/bin/env bash
# Build the FeatherOS ISO on any Linux host (Ubuntu, Fedora, ...) using an
# Arch Linux container, because mkarchiso only runs on Arch.
#
#   ./build.sh                 # uses: sudo podman (or sudo docker)
#   ENGINE=docker ./build.sh   # force a container engine
#   SUDO= ./build.sh           # rootless podman
#   ./build.sh packages        # only (re)build the signed update packages
#                              # (repo/), e.g. before ./serve-updates.sh
#
# Output: out/featheros-YYYY.MM.DD-x86_64.iso and repo/x86_64/
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

SUDO=${SUDO-sudo}
ENGINE=${ENGINE:-$(command -v podman >/dev/null && echo podman || echo docker)}
IMAGE=${IMAGE:-docker.io/archlinux/archlinux:latest}

mkdir -p out
# Inside a rootless container the host user is uid 0; with sudo it keeps its uid.
if [[ -z $SUDO && $(id -u) != 0 ]]; then rootless=1 owner=(0 0); else rootless=0 owner=("$(id -u)" "$(id -g)"); fi
# The pacman cache lives in a named volume so rebuilds don't re-download.
exec $SUDO "$ENGINE" run --rm --privileged \
    -v "$PWD":/src:z \
    -v featheros-pkgcache:/var/cache/pacman/pkg \
    -e HOST_UID="${owner[0]}" -e HOST_GID="${owner[1]}" -e ROOTLESS="$rootless" \
    "$IMAGE" bash /src/scripts/container-build.sh "$@"
