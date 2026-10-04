# FeatherOS

A very light, macOS-inspired Linux distribution built on Arch Linux. It is
made for one old laptop, the **Infoway Note W7410** (Core 2 Duo T6600, 3 GB
DDR2, Intel GMA 4500M, HDD), and it is tested in QEMU/GNOME Boxes.

- **Idle RAM after login: about 160–180 MB** (`free -m` "used", measured in the VM)
- **ISO: 1.2 GB.** It's a live USB and an offline installer in one.
- **Desktop:** X11 + Openbox, a tint2 top bar and dock, Spotlight-style
  search, light and dark modes, and red/yellow/green window buttons.
- **Apps:** Firefox (tuned for 3 GB), mpv + yt-dlp (YouTube in H.264, 720p
  or lower), Geany, Neovim, git, gcc, Python, Node.js.
- **Updates:** your desktop builds signed FeatherOS packages and the laptop
  installs them with `pacman -Syu`, so you never have to reinstall.
- **UI language:** Portuguese (pt_BR). Keyboard layout: ABNT2.

| Light | Dark |
|---|---|
| ![Light desktop](docs/screenshots/desktop-light.jpg) | ![Dark desktop](docs/screenshots/desktop-dark.jpg) |
| ![Feather menu](docs/screenshots/feather-menu.jpg) | ![YouTube in mpv](docs/screenshots/mpv-youtube.jpg) |

## Contents

1. [Build the ISO](#1-build-the-iso)
2. [Test in GNOME Boxes](#2-test-in-gnome-boxes)
3. [Install on the laptop](#3-install-on-the-laptop)
4. [Updating the laptop from your desktop](#4-updating-the-laptop-from-your-desktop)
5. [Using FeatherOS](#5-using-featheros)
6. [Measured RAM and boot time](#6-measured-ram-and-boot-time)
7. [How it is built](#7-how-it-is-built)
8. [Troubleshooting](#8-troubleshooting)

## 1. Build the ISO

You need a Linux host (Ubuntu, Fedora, ...) with **podman** or **docker**,
about 15 GB of free disk space, and an internet connection. The build runs
inside an Arch Linux container, because `mkarchiso` only runs on Arch.

```sh
./build.sh            # uses: sudo podman (or sudo docker)
```

`out/featheros-YYYY.MM.DD-x86_64.iso` is the result. The first build takes
about 15 minutes, 7 of them for the kernel on a 12-thread CPU. Later builds
only rebuild what changed: the kernel only when its `pkgver`/`pkgrel` changes.

Variants:

```sh
SUDO= ./build.sh           # rootless podman (works on Fedora)
ENGINE=docker ./build.sh   # force docker
./build.sh packages        # only build the signed update packages (repo/)
```

The first build also creates the **update-signing key** in `signing/`. It has
no passphrase and is never committed. **Back up `signing/`.** Installed
systems trust only this key, so without it you would have to re-import a new
key on the laptop by hand.

## 2. Test in GNOME Boxes

1. Open GNOME Boxes, click **+**, choose **Install from File**, and select
   the ISO.
2. Set **Memory: 3 GB** so the VM matches the laptop, then create the VM.
3. It boots into the live desktop as the user `feather`. This user has no
   password and passwordless `sudo`.
4. Try the installer on the VM's own disk: feather menu (top-left) →
   **Instalar FeatherOS**.

Headless testing, which was used for all the measurements below:

```sh
python3 scripts/vm-test.py out/featheros-*.iso --vga std --audio
python3 scripts/vm-test.py out/featheros-*.iso --throttle-mbps 30   # USB 2 speed
```

`vm-test.py` boots the ISO in QEMU/KVM (3 GB RAM, 2 cores, Core 2-class CPU
model), logs in over a serial console, and prints boot time and RAM figures.
`--cmd` runs extra commands, `@shot file.png` takes screenshots, and `--disk`
/ `--boot-disk` / `--uefi` test installs.

## 3. Install on the laptop

1. Write the ISO to a USB stick (at least 2 GB). **Everything on the stick
   is erased.**
   ```sh
   lsblk                                     # find the stick, e.g. /dev/sdb
   sudo dd if=out/featheros-*.iso of=/dev/sdX bs=4M status=progress oflag=sync
   ```
   GNOME Disks ("Restore Disk Image") works too.
2. Boot the laptop from the stick (usually F12 or F11 at power-on). The boot
   menu has:
   - **FeatherOS**: the normal live session.
   - **FeatherOS (load to RAM)**: copies the system into RAM first. It starts
     slower, then runs fast, and the stick can be removed.
   - **FeatherOS (kernel Arch LTS)**: the stock Arch kernel, if some
     hardware doesn't work with the FeatherOS kernel.
3. Check Wi-Fi (click the network icon), sound and video before installing.
4. Feather menu → **Instalar FeatherOS**. The installer asks for:
   - the disk. **The whole disk is erased.**
   - your name, user name and password
   - the computer name
   - whether to log in automatically (default: no)
   - the update server: `my-desktop.local`, or your desktop's IP, e.g.
     `192.168.1.10`

   Then it copies the system from the stick, with no internet needed. That
   takes a few minutes on an HDD. BIOS/MBR or UEFI/GPT is detected
   automatically.
5. Remove the stick and reboot. GRUB waits 2 s with a hidden menu. Hold
   **Shift** or **Esc** during that time to choose the backup Arch LTS
   kernel.

What the installer sets up:

- `ext4` with `noatime`, and zram swap (no swap partition)
- an initramfs for both kernels with `autodetect`, so it only contains the
  laptop's own modules
- persistent logs capped at 50 MB
- Arch mirrors: the GeoIP mirror first, then the Brazilian mirrors
- the FeatherOS update repository and signing key

## 4. Updating the laptop from your desktop

All of FeatherOS's own files are pacman packages: the `featheros-desktop`
package (scripts, themes, defaults), the kernel and the themes. Updates
therefore never need a reinstall, and your files and settings stay untouched.

On the desktop (`my-desktop`):

```sh
# change something in packages/featheros-desktop/files/ (or the kernel, ...)
./build.sh packages      # rebuilds and signs only what changed
./serve-updates.sh       # serves repo/ on port 8080 until Ctrl+C
```

On the laptop: feather menu → **Atualizar sistema**. Or, in a terminal:

```sh
sudo pacman -Syu
```

That one command updates Arch packages from the Arch mirrors and FeatherOS
packages from your desktop. A new dependency added to `featheros-desktop` is
installed automatically.

- **Server address.** The laptop finds the desktop as `my-desktop.local`
  (mDNS) or by IP. To change it later:
  `sudo featheros-update-server 192.168.1.10`.
- **Firewall.** The desktop must accept TCP port 8080. Fedora Workstation's
  default zone already allows it. On Ubuntu with ufw enabled, run
  `sudo ufw allow 8080/tcp`.
- **When the desktop is off.** `pacman -Syu` prints an error for the
  `featheros` repository but still updates Arch packages.
- **Your settings.** Files under `/etc` that you edited are kept: the new
  version is saved as `.pacnew`. Per-user settings in `~/.config` are not
  overwritten either. Most of the look comes from system templates in
  `/usr/share/featheros`, so theme fixes still reach existing users.

## 5. Using FeatherOS

| Shortcut | Action |
|---|---|
| Super + Space | Search apps (Spotlight-style) |
| Super + Enter | Terminal |
| Super + E | Files |
| Super + Q | Close window |
| Super + Up / Down | Maximize / minimize |
| Super + Shift + P | Visual effects (shadows, rounded corners) on/off |
| Alt + Tab | Switch windows |
| Volume / brightness keys | Change volume / brightness |

- **Feather menu** (top-left): about this computer, update system (install
  from the live USB), light/dark appearance, effects on/off, log out,
  restart, shut down.
- **Top bar:** click the network icon for the Wi-Fi menu. On the volume
  icon, click to mute and scroll to change the level.
- **YouTube:** search "Reproduzir vídeo da web", or run `featheros-play` with
  a link copied. It plays in mpv at H.264 ≤ 720p, using far less CPU and RAM
  than the browser. In Firefox, YouTube also gets H.264, because
  VP9/AV1 are disabled in its defaults.
- **Measuring:** `sudo featheros-mem` shows the real memory use per program
  (PSS), and `featheros-mem firefox` shows Firefox with all its tabs.
  `featheros-boottime` shows how long the last boot took.
- **Firefox:** WebGL is off to save about 130 MB. If a site needs 3D, set
  `webgl.disabled` to `false` in `about:config`.

## 6. Measured RAM and boot time

**These numbers come from the QEMU test VM** (3 GB RAM, 2 cores, Core
2-class CPU model). They have not yet been measured on the real laptop:
`sudo featheros-mem` and `featheros-boottime` print the same figures there.
The VM's CPU runs at the host's speed, so expect slower boots and higher CPU
use on the T6600. Raw data: [docs/measurements.md](docs/measurements.md).

### Idle desktop after login

| Component | RAM (PSS) | Why it is there |
|---|---|---|
| Xorg | 40 MB | X11: more reliable than Wayland on the GMA 4500M |
| tint2 (top bar + dock) | 21 MB | about 50 MB lighter than Plank as the dock |
| Openbox | 13 MB | window manager (xfwm4: ~30 MB) |
| systemd + user manager | 11 MB | init |
| systemd-udevd | 5.6 MB | devices |
| systemd-networkd + resolved + timesyncd | 7.5 MB | network, DNS/mDNS, clock (NetworkManager + applet: ~40 MB) |
| journald + logind + dbus-broker | 7.4 MB | logs, sessions, IPC |
| bar status scripts | 2.2 MB | volume watcher (event-driven, no polling) |
| picom | 1.9 MB | shadows and rounded corners; off = 0 |
| iwd | 1.6 MB | Wi-Fi (wpa_supplicant + NetworkManager: more) |
| xsettingsd | 0.9 MB | live light/dark switching of open apps |
| PipeWire | 0 MB | socket-activated: starts with the first sound (20 MB then) |
| Display manager | 0 MB | none: tty login, then `startx` |
| **`free -m` "used"** | **158–180 MB** | target < 250, maximum 350 |

### Applications (PSS including child processes)

| App | RAM | Notes |
|---|---|---|
| xfce4-terminal | 59 MB | Alacritty measured 107 MB |
| Geany (1 file) | 57 MB | Lite XL measured 108 MB |
| mpv, YouTube 720p H.264 | 160 MB | |
| Firefox, claude.ai open | 1078 MB | 1196 MB with Arch defaults; 610 MB with an empty tab |

### Boot

| Scenario | `systemd-analyze` | Kernel → desktop ready |
|---|---|---|
| Live ISO, fast disk | 5.8 s | 8 s |
| Live ISO, USB 2 speed (30 MB/s) | 10.7 s | 14 s |
| Installed, HDD-like disk (70 MB/s, 120 IOPS), steady state | 10.9 s | 21 s |
| Installed, same disk, first boot | 18.4 s | 26 s |

Add firmware POST and GRUB's 2 s for the time from power-on. The target is
under 30 s on the HDD.

### Sizes

| | |
|---|---|
| ISO | 1.2 GB (of which the backup Arch LTS kernel is about 160 MB) |
| FeatherOS kernel modules | 17 MB, 136 modules (Arch linux-lts: 6227) |

## 7. How it is built

```
build.sh                 build the ISO (or packages only) in an Arch container
serve-updates.sh         serve repo/ to the laptop
archiso/                 archiso profile: package list, boot menus, live-only files
  airootfs/              live session plumbing + the installer (featheros-install)
packages/
  featheros-desktop/     FeatherOS itself: files/ mirrors /, PKGBUILD lists every
                         app/component as a dependency
  whitesur-*-theme/      WhiteSur GTK/icons/cursors (Apple logos removed)
kernel/
  linux-featheros/       kernel PKGBUILD (from Arch linux-lts) + generated config
  featheros.config       config overrides (each one explained)
  modules-*.txt          module lists for localmodconfig
hardware/                lspci / lsusb / lsmod from the laptop
artwork/                 logo SVGs, wallpaper + Openbox theme generators
scripts/                 build steps, kernel config, VM test harness
docs/                    measurements, screenshots
```

**Kernel.** The kernel is Arch's `linux-lts` (6.18 LTS) config, run through
`make localmodconfig` with the union of three module lists: the laptop's
`lsmod`, the VM's `lsmod`, and `modules-extra.txt` (live boot, filesystems,
iwd crypto, virtio). Modules in `modules-exclude.txt` are dropped, then
`featheros.config` is applied:

- no debug info or tracing
- `NR_CPUS=8` and no NUMA
- transparent hugepages off. THP raised `min_free_kbytes` to about 67 MB.
- the BFQ disk scheduler built in
- every Realtek HDA codec. Since 6.17 the Realtek codec module is split per
  chip.

To change it, edit those files, bump `pkgrel` in
`kernel/linux-featheros/PKGBUILD`, and run `./build.sh packages` to get a
kernel update.

**Packages.** `featheros-desktop` gets a new date-based version whenever
anything under `packages/featheros-desktop/` changes. The themes and kernel
use normal `pkgver`/`pkgrel`.

**Licenses and trademarks.** The FeatherOS logo, wallpapers and Openbox
themes are original. WhiteSur is MIT (GTK) and GPL-3.0 (icons, cursors). In
the WhiteSur build, the Apple logo is replaced by the feather, the
Finder-face file manager icon by a folder, and the Safari and iCloud icons
are removed. No Apple fonts are used: the UI font is Inter.

## 8. Troubleshooting

- **The desktop doesn't start (black screen, or back to a text login).**
  Log in and look at `~/.local/share/xorg/Xorg.0.log`. On the GMA 4500M,
  FeatherOS uses the `intel` X driver (SNA). To try the generic modesetting
  driver instead, run `sudo rm /etc/X11/xorg.conf.d/20-gpu.conf`, then
  `startx`.
- **Windows draw badly or dragging feels slow.** Turn effects off with
  Super + Shift + P. The choice is remembered.
- **Wi-Fi isn't found.** Check `ip link` and `lsmod | grep rtl`. Try the
  **kernel Arch LTS** entry. If it works there, a module is missing from the
  FeatherOS kernel: add it to `kernel/modules-extra.txt` and rebuild.
- **No sound.** Run `alsamixer` (F6 selects the card) and unmute Master and
  Speaker.
- **Updates fail to connect.** On the desktop, make sure
  `./serve-updates.sh` is running. On the laptop, try
  `curl http://my-desktop.local:8080/x86_64/featheros.db -o /dev/null`. If
  the name doesn't resolve, use the IP:
  `sudo featheros-update-server 192.168.1.10`.
- **"signature from FeatherOS updates is unknown trust".** The packages were
  signed with a different key than the one the laptop trusts, for example
  because `signing/` was lost. Re-import the key:
  ```sh
  sudo pacman-key --add /usr/share/featheros/keys/featheros.asc
  sudo pacman-key --lsign-key featheros@localhost
  ```
  Use the new `featheros.asc` from the desktop, copied over.
