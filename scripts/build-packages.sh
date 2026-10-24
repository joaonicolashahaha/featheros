#!/usr/bin/env bash
# Build FeatherOS's own packages into the signed local pacman repo
# (repo/x86_64). The ISO installs from it, and installed systems update from
# it (./serve-updates.sh). Only packages that changed are rebuilt:
#
#   kernel/linux-featheros   pkgver/pkgrel in its PKGBUILD (config regenerated
#                            by scripts/kernel-config.sh)
#   packages/*               themes: pkgver/pkgrel in the PKGBUILD;
#                            "featheros: auto-version" packages get a new
#                            date-based pkgver whenever their files change
#
# Packages and the database are signed with the FeatherOS key in signing/
# (created on first run, no passphrase, never committed: back it up!).
#
# Runs inside an Arch container; started by scripts/container-build.sh.
# Pass package directory names to force a rebuild, e.g.
#   bash /src/scripts/build-packages.sh linux-featheros
set -euo pipefail

repo=/src/repo/x86_64
mkdir -p "$repo" /src/kernel/cache
id builder &>/dev/null || useradd -m builder
chmod 777 /src/kernel/cache

# --- Signing key -------------------------------------------------------------
export GNUPGHOME=/src/signing/gnupg
pubkey=/src/packages/featheros-desktop/files/usr/share/featheros/keys/featheros.asc
if ! gpg --list-secret-keys featheros@localhost &>/dev/null; then
    echo "==> Creating the FeatherOS signing key (signing/gnupg)"
    mkdir -p "$GNUPGHOME" && chmod 700 "$GNUPGHOME"
    gpg --batch --passphrase '' --quick-gen-key \
        "FeatherOS updates <featheros@localhost>" ed25519 sign never
fi
keyid=$(gpg --list-secret-keys --with-colons featheros@localhost | awk -F: '/^fpr/ { print $10; exit }')
mkdir -p "$(dirname "$pubkey")"
gpg --armor --export "$keyid" >"$pubkey.new"
if cmp -s "$pubkey.new" "$pubkey"; then rm "$pubkey.new"; else mv "$pubkey.new" "$pubkey"; fi

# --- Remote-access SSH key (featheros-remote) ---------------------------------
# The private key stays here; installed systems only accept its public half.
sshkey=/src/signing/ssh/featheros_remote
authkeys=/src/packages/featheros-desktop/files/usr/share/featheros/remote/authorized_keys
if [[ ! -f $sshkey ]]; then
    echo "==> Creating the remote-access SSH key (signing/ssh)"
    pacman -S --noconfirm --needed openssh >/dev/null
    mkdir -p "$(dirname "$sshkey")" && chmod 700 "$(dirname "$sshkey")"
    ssh-keygen -q -t ed25519 -N '' -C "featheros-remote" -f "$sshkey"
fi
mkdir -p "$(dirname "$authkeys")"
if ! cmp -s "$sshkey.pub" "$authkeys"; then cp "$sshkey.pub" "$authkeys"; fi

# --- Helpers -----------------------------------------------------------------
# Files in $repo that belong to package $1 (exact pkgname match).
pkg_files() {
    local f base
    for f in "$repo/$1"-*.pkg.tar.zst; do
        [[ -e $f ]] || continue
        base=$(basename "$f" .pkg.tar.zst)
        [[ ${base%-*-*-*} == "$1" ]] && echo "$f"
    done
    return 0
}

content_hash() {
    tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C "$1" . |
        sha256sum | cut -d' ' -f1
}

build_one() {
    local dir=$1 name ver rel arch auto=no
    read -r name ver rel arch < <(bash -c "source '$dir/PKGBUILD' >/dev/null
        echo \"\${pkgname[0]} \$pkgver \$pkgrel \${arch[0]}\"")
    grep -q '^# featheros: auto-version' "$dir/PKGBUILD" && auto=yes
    local force=no
    [[ " ${FORCE[*]} " == *" $(basename "$dir") "* ]] && force=yes

    if [[ $auto == yes ]]; then
        local hash; hash=$(content_hash "$dir")
        if [[ $force == no && -n $(pkg_files "$name") &&
              $(cat "$repo/.$name.hash" 2>/dev/null) == "$hash" ]]; then
            echo "==> $name unchanged"
            return
        fi
        ver=$(date -u +%Y.%m.%d.%H%M)
    elif [[ $force == no && -e "$repo/$name-$ver-$rel-$arch.pkg.tar.zst" ]]; then
        echo "==> $name $ver-$rel already built"
        return
    fi

    echo "==> Building $name $ver-$rel"
    if [[ $name == linux-featheros ]]; then
        pacman -S --noconfirm --needed bc cpio pahole python perl libelf openssl
        bash /src/scripts/kernel-config.sh
        # GNUPGHOME (the FeatherOS signing keyring) must not leak into the
        # build user: it verifies the kernel sources with its own keyring.
        su builder -c "unset GNUPGHOME; gpg --batch --import $dir/keys/pgp/*.asc" 2>/dev/null
    fi
    local build=/tmp/build/$name
    rm -rf "$build" && mkdir -p /tmp/build && cp -rL "$dir" "$build"
    [[ $auto == yes ]] && sed -i "s/^pkgver=.*/pkgver=$ver/" "$build/PKGBUILD"
    chown -R builder: "$build"
    # Auto-versioned packages only copy files: don't install their runtime
    # dependencies (Firefox, Xorg, ...) into the build container.
    local deps=--syncdeps
    if [[ $auto == yes ]]; then
        deps=--nodeps
        # Still needs what it compiles with.
        local mk; mk=$(bash -c "source '$dir/PKGBUILD' >/dev/null; echo \${makedepends[*]}")
        [[ -n $mk ]] && pacman -S --noconfirm --needed $mk >/dev/null
    fi
    su builder -c "unset GNUPGHOME; cd $build && SRCDEST=/src/kernel/cache PKGDEST=$build/out \
        MAKEFLAGS=-j$(nproc) makepkg --noconfirm --cleanbuild $deps" </dev/null
    # Replace older builds of every package this PKGBUILD produces.
    local out n
    for out in "$build"/out/*.pkg.tar.zst; do
        n=$(basename "$out" .pkg.tar.zst); n=${n%-*-*-*}
        pkg_files "$n" | while read -r f; do rm -f "$f" "$f.sig"; done
        cp "$out" "$repo/"
    done
    [[ $auto == yes ]] && echo "$hash" >"$repo/.$name.hash"
    return 0
}

# makepkg --syncdeps runs pacman through sudo as the build user.
pacman -S --noconfirm --needed base-devel
echo 'builder ALL=(ALL) NOPASSWD: /usr/bin/pacman' >/etc/sudoers.d/builder

FORCE=("$@")
for dir in /src/kernel/linux-featheros /src/packages/*/; do
    build_one "${dir%/}"
done

# --- Sign and index ----------------------------------------------------------
cd "$repo"
for f in ./*.pkg.tar.zst; do
    [[ -e $f.sig ]] || gpg --batch --yes --detach-sign --local-user "$keyid" "$f"
done
# Recreate the database from scratch (updating it in place fails on
# SELinux-labelled bind mounts: bsdtar can't restore the xattrs).
rm -f featheros.db* featheros.files*
repo-add -q --sign --key "$keyid" featheros.db.tar.gz ./*.pkg.tar.zst
chown -R "${HOST_UID:-0}:${HOST_GID:-0}" /src/repo /src/signing \
    /src/kernel/linux-featheros/config "$pubkey"
ls -lh "$repo"
