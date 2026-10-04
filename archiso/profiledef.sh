#!/usr/bin/env bash
# shellcheck disable=SC2034

iso_name="featheros"
iso_label="FEATHER_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="FeatherOS"
iso_application="FeatherOS Live/Install"
iso_version="$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y.%m.%d)"
install_dir="feather"
bootmodes=('bios.syslinux'
           'uefi.systemd-boot')
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
# zstd instead of releng's xz: a bit bigger, but much faster to decompress on a Core 2 Duo.
airootfs_image_tool_options=('-comp' 'zstd' '-Xcompression-level' '19' '-b' '1M')
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/etc/gshadow"]="0:0:400"
  ["/etc/sudoers.d"]="0:0:750"
  ["/etc/sudoers.d/10-wheel"]="0:0:440"
  ["/etc/sudoers.d/99-live"]="0:0:440"
  ["/usr/local/bin/"]="0:0:755"
  ["/usr/lib/featheros/autostart"]="0:0:755"
  ["/etc/skel/.xinitrc"]="0:0:755"
)
