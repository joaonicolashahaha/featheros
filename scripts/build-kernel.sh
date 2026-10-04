#!/usr/bin/env bash
# Build the linux-featheros package and put it in the local pacman repo
# (repo/x86_64), which the ISO build installs from.
# Runs inside an Arch container; started by ./build.sh (only when the repo
# has no package for the current PKGBUILD) or by hand:
#
#   sudo podman run --rm -v "$PWD":/src:z docker.io/archlinux/archlinux \
#       bash /src/scripts/build-kernel.sh
set -euo pipefail

pacman -Syu --noconfirm --needed base-devel bc cpio pahole python perl \
    libelf openssl xz zstd

# Regenerate the config from Arch's config + module lists + overrides.
bash /src/scripts/kernel-config.sh

# makepkg refuses to run as root.
id builder &>/dev/null || useradd -m builder
build=/tmp/linux-featheros
rm -rf "$build" && cp -r /src/kernel/linux-featheros "$build"
chown -R builder: "$build"
mkdir -p /src/kernel/cache /src/repo/x86_64
chmod 777 /src/kernel/cache

su builder -c "gpg --batch --import $build/keys/pgp/*.asc" 2>/dev/null
su builder -c "cd $build && SRCDEST=/src/kernel/cache PKGDEST=$build/out \
    MAKEFLAGS=-j$(nproc) makepkg --noconfirm --cleanbuild"

# Replace older builds and recreate the repo database from scratch (updating
# it in place fails on SELinux-labelled bind mounts: bsdtar can't restore
# the xattrs).
cd /src/repo/x86_64
find . -maxdepth 1 \( -name 'linux-featheros-*.pkg.tar.zst' -o -name 'featheros.*' \) -delete
cp "$build"/out/*.pkg.tar.zst .
repo-add -q featheros.db.tar.gz ./*.pkg.tar.zst
chown -R "${HOST_UID:-0}:${HOST_GID:-0}" /src/repo /src/kernel/linux-featheros/config
ls -lh /src/repo/x86_64
