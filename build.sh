#!/usr/bin/env bash
# Build the FeatherOS ISO on any Linux host (Ubuntu, Fedora, ...) using an
# Arch Linux container, because mkarchiso only runs on Arch.
#
#   ./build.sh                 # uses: sudo podman (or sudo docker)
#   ENGINE=docker ./build.sh   # force a container engine
#   SUDO= ./build.sh           # rootless podman
#
# Output: out/featheros-YYYY.MM.DD-x86_64.iso
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

SUDO=${SUDO-sudo}
ENGINE=${ENGINE:-$(command -v podman >/dev/null && echo podman || echo docker)}
IMAGE=${IMAGE:-docker.io/archlinux/archlinux:latest}

mkdir -p out
# The pacman cache lives in a named volume so rebuilds don't re-download.
exec $SUDO "$ENGINE" run --rm --privileged \
    -v "$PWD":/src:z \
    -v featheros-pkgcache:/var/cache/pacman/pkg \
    -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    -e ROOTLESS="$([[ -z $SUDO && $(id -u) != 0 ]] && echo 1 || echo 0)" \
    "$IMAGE" bash /src/scripts/container-build.sh
