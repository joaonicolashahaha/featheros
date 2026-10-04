#!/usr/bin/env bash
# Generate kernel/linux-featheros/config from Arch's linux-lts config.
# Runs inside an Arch container (see scripts/build-kernel.sh), from /src.
#
#   1. Start from Arch's linux-lts config.
#   2. `make localmodconfig` with the union of: the laptop's lsmod
#      (hardware/modules.txt), the VM's lsmod (kernel/modules-vm.txt) and
#      kernel/modules-extra.txt.
#   3. Apply kernel/featheros.config and resolve dependencies.
#   4. Report every override that didn't stick.
set -euo pipefail
cd /src

ver=$(sed -n 's/^pkgver=//p' kernel/linux-featheros/PKGBUILD)
tarball=kernel/cache/linux-$ver.tar.xz
[[ -f $tarball ]] || curl -fsSL -o "$tarball" \
    "https://cdn.kernel.org/pub/linux/kernel/v${ver%%.*}.x/linux-$ver.tar.xz"

tree=/tmp/kconfig/linux-$ver
rm -rf /tmp/kconfig && mkdir -p /tmp/kconfig
tar -xf "$tarball" -C /tmp/kconfig

names() { sed -e 's/#.*//' -e '/^Module /d' -e '/^[[:space:]]*$/d' "$@" | awk '{print $1}'; }
lsmod_all=/tmp/kconfig/lsmod.txt
{
    echo "Module Size Used by"
    names hardware/modules.txt kernel/modules-vm.txt kernel/modules-extra.txt |
        sort -u | grep -vxFf <(names kernel/modules-exclude.txt) |
        awk '{print $1, 0, 0}'
} >"$lsmod_all"

cd "$tree"
cp "/src/kernel/config.arch-linux-lts-$ver" .config
make -s olddefconfig
make -s LSMOD="$lsmod_all" localmodconfig </dev/null >/dev/null
scripts/kconfig/merge_config.sh -m .config /src/kernel/featheros.config >/dev/null
make -s olddefconfig

# Every override must survive dependency resolution.
fail=0
while IFS= read -r line; do
    if [[ $line =~ ^(CONFIG_[A-Z0-9_]+)=(.*)$ ]]; then
        sym=${BASH_REMATCH[1]} want=${BASH_REMATCH[2]}
    elif [[ $line =~ ^#\ (CONFIG_[A-Z0-9_]+)\ is\ not\ set ]]; then
        sym=${BASH_REMATCH[1]} want=n
    else
        continue
    fi
    got=$(scripts/config -s "${sym#CONFIG_}")
    [[ $got == undef ]] && got=n
    if [[ $got != "$want" ]]; then
        echo "override not applied: $sym wanted=$want got=$got"
        fail=1
    fi
done </src/kernel/featheros.config

cp .config /src/kernel/linux-featheros/config
echo "modules: $(grep -c '=m$' .config)  built-in: $(grep -c '=y$' .config)"
echo "(Arch linux-lts: modules: $(grep -c '=m$' "/src/kernel/config.arch-linux-lts-$ver")" \
     " built-in: $(grep -c '=y$' "/src/kernel/config.arch-linux-lts-$ver"))"
exit $fail
