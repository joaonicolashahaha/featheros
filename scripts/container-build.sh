#!/usr/bin/env bash
# Runs inside the Arch container started by build.sh.
set -euo pipefail

pacman -Syu --noconfirm --needed archiso

# Rootless containers may not mount devtmpfs, which pacstrap needs. Its
# unshare mode (-N) bind-mounts device nodes instead; mkarchiso only uses it
# for non-root users, so force it here.
if [[ ${ROOTLESS:-0} == 1 ]]; then
    sed -i 's/if (( EUID != 0 )); then/if true; then/' /usr/bin/mkarchiso
    # unshare --map-auto needs a sub-ID range; use what the container has.
    echo 'root:1:65535' > /etc/subuid
    echo 'root:1:65535' > /etc/subgid
fi

work=/tmp/featheros-work
mkarchiso -v -w "$work" -o /src/out /src/archiso
chown "${HOST_UID:-0}:${HOST_GID:-0}" /src/out/*.iso
ls -lh /src/out
