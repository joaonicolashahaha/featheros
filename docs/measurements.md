# FeatherOS measurements

All numbers are from the QEMU/KVM test VM (`scripts/vm-test.py`): 3 GB RAM,
2 cores, Core 2-class CPU model, Intel HDA audio, std VGA, live ISO.
RAM per component is PSS (shared libraries split fairly), measured with
`featheros-mem` (shipped in the ISO, so the same can be run on the laptop).

**Not yet measured on the real laptop** (Core 2 Duo T6600, GMA 4500M, HDD).
The VM's CPU runs at the speed of the host, so CPU percentages and boot times
there are lower bounds.

## Idle desktop (60 s after login, live ISO, 2026-10-04)

| Metric | Value |
|---|---|
| `free -m` "used" | 180 MB |
| Total PSS of all processes | 138 MB |
| `systemd-analyze` (fast disk) | 1.6 s kernel + 4.2 s userspace = 5.8 s |
| Kernel start -> desktop ready (fast disk) | 8 s |
| Same, boot medium throttled to 30 MB/s (USB 2 stick) | 10.7 s / desktop ready after 14 s |

| Component | PSS |
|---|---|
| Xorg (modesetting, no glamor in VM) | 40.0 MB |
| tint2 (top bar + dock) | 21.4 MB |
| Openbox | 13.0 MB |
| systemd (PID 1 + user manager) | 11.1 MB |
| systemd-udevd | 5.6 MB |
| systemd-networkd | 3.6 MB |
| systemd-resolved | 2.6 MB |
| systemd-journald | 2.6 MB |
| dbus-broker (+ launcher) | 3.4 MB |
| picom (effects on) | 1.9 MB |
| iwd | 1.6 MB |
| systemd-timesyncd | 1.3 MB |
| bar status scripts (volume watcher) | 2.2 MB |
| xsettingsd | 0.9 MB |
| PipeWire | 0 (not running until something plays) |

## Applications (PSS including child processes)

| Application | PSS | Notes |
|---|---|---|
| xfce4-terminal | 59 MB | incl. shell; Alacritty measured 107 MB (dropped) |
| Geany (one file open) | 57 MB | Lite XL measured 108 MB (dropped) |
| PipeWire + WirePlumber + pipewire-pulse | 20 MB | only while audio is used |
| mpv playing YouTube 720p H.264 | 160 MB | 12 % of one host core in the VM |
| Firefox, claude.ai login page | 1078 MB | 1196 MB before tuning |

### Firefox tuning (claude.ai open, total PSS)

| Variant | PSS |
|---|---|
| Arch defaults + FeatherOS policies | 1196-1203 MB |
| + no pre-launched content process | 1184 MB |
| + Fission (site isolation) off | 1136 MB (not adopted: security) |
| + software WebRender + WebGL off | 1059-1078 MB (adopted) |
| Firefox with only about:blank | 610 MB |
