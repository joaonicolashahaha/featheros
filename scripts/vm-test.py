#!/usr/bin/env python3
"""Boot a FeatherOS ISO headless in QEMU/KVM and print boot/RAM measurements.

The VM imitates the target laptop where it matters: 3 GB RAM, 2 cores and a
Core 2-class CPU model (Penryn: no AVX). The kernel is booted directly so
that a serial console can be added to the command line.

    scripts/vm-test.py out/featheros-*.iso [--keep] [--cmd 'extra command']
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile
import time

import socket

import pexpect

ap = argparse.ArgumentParser()
ap.add_argument("iso")
ap.add_argument("--mem", default="3072")
ap.add_argument("--settle", type=int, default=60,
                help="seconds to wait after login before measuring")
ap.add_argument("--cmd", action="append", default=[],
                help="extra command to run and print (repeatable). Special:"
                     " '@shot FILE.png' takes a screenshot, '@sleep N' waits")
ap.add_argument("--append", default="", help="extra kernel parameters")
ap.add_argument("--machine", default="q35", help="q35 or pc (i440fx)")
ap.add_argument("--cdrom-if", default="virtio",
                help="bus for the ISO: virtio, ide (AHCI on q35) or scsi")
ap.add_argument("--vga", default="none", help="QEMU -vga: none, std, virtio, qxl")
ap.add_argument("--audio", action="store_true",
                help="add an Intel HDA sound card (like the laptop's)")
ap.add_argument("--throttle-mbps", type=int, default=0,
                help="limit the boot medium to N MB/s (e.g. 30 = USB 2 stick)")
ap.add_argument("--disk", help="attach this qcow2 disk image (virtio, /dev/vda)")
ap.add_argument("--boot-disk", action="store_true",
                help="boot the installed system from --disk (no ISO)")
ap.add_argument("--uefi", action="store_true", help="UEFI firmware (OVMF)")
ap.add_argument("--user", default="feather", help="serial console login")
ap.add_argument("--password", default="", help="password for --user")
ap.add_argument("--disk-mbps", type=int, default=0,
                help="limit --disk to N MB/s and 120 IOPS (HDD-like)")
ap.add_argument("--timeout", type=int, default=120,
                help="per-command timeout in seconds")
args = ap.parse_args()

tmp = tempfile.mkdtemp(prefix="featheros-vm-")
kernel = initrd = cmdline = None
if not args.boot_disk:
    subprocess.run(["7z", "x", "-y", f"-o{tmp}", args.iso,
                    "feather/boot/x86_64/*", "-r"], check=True,
                   stdout=subprocess.DEVNULL)
    boot = os.path.join(tmp, "feather/boot/x86_64")
    kernel = os.path.join(boot, "vmlinuz-linux-featheros")
    initrd = os.path.join(boot, "initramfs-linux-featheros.img")
    listing = subprocess.run(["7z", "l", args.iso], capture_output=True,
                             text=True).stdout
    label = next((l.split("=", 1)[1].strip() for l in listing.splitlines()
                  if l.startswith("Comment") or l.startswith("Volume")), None)
    label = label or "FEATHER_" + time.strftime("%Y%m")
    cmdline = (f"archisobasedir=feather archisolabel={label} copytoram=n "
               f"console=ttyS0,115200 {args.append}")
if args.cdrom_if == "scsi":
    cdrom = ["-device", "virtio-scsi-pci,id=scsi0",
             "-drive", f"file={args.iso},media=cdrom,readonly=on,if=none,id=cd0",
             "-device", "scsi-cd,drive=cd0"]
else:
    throttle = ""
    if args.throttle_mbps:
        throttle = (f",throttling.bps-total={args.throttle_mbps * 1024 * 1024}"
                    ",throttling.iops-total=150")
    cdrom = ["-drive", f"file={args.iso},media=cdrom,readonly=on,"
             f"if={args.cdrom_if}{throttle}"]
boot = [] if args.boot_disk else ["-kernel", kernel, "-initrd", initrd,
                                  "-append", cmdline, *cdrom]
qemu = ["qemu-system-x86_64", "-enable-kvm", "-machine", args.machine,
        "-cpu", "Penryn", "-smp", "2", "-m", args.mem, *boot,
        "-nic", "user,model=virtio-net-pci", "-vga", args.vga,
        "-display", "none", "-serial", "stdio", "-no-reboot",
        "-usb", "-device", "usb-tablet",
        "-monitor", f"unix:{tmp}/mon.sock,server,nowait"]
if args.disk:
    t = ""
    if args.disk_mbps:
        t = (f",throttling.bps-total={args.disk_mbps * 1024 * 1024}"
             ",throttling.iops-total=120")
    qemu += ["-drive", f"file={args.disk},if=virtio,format=qcow2{t}"]
if args.uefi:
    vars_ = os.path.splitext(args.disk or os.path.join(tmp, "x"))[0] + ".vars.fd"
    if not os.path.exists(vars_):
        subprocess.run(["cp", "/usr/share/edk2/ovmf/OVMF_VARS.fd", vars_], check=True)
    qemu += ["-drive", "if=pflash,format=raw,readonly=on,"
             "file=/usr/share/edk2/ovmf/OVMF_CODE.fd",
             "-drive", f"if=pflash,format=raw,file={vars_}"]
if args.audio:
    qemu += ["-audiodev", "none,id=snd0", "-device", "intel-hda",
             "-device", "hda-duplex,audiodev=snd0"]

t0 = time.time()
vm = pexpect.spawn(qemu[0], qemu[1:], encoding="utf-8", timeout=300,
                   codec_errors="replace")
vm.logfile_read = open(os.path.join(tmp, "serial.log"), "w")
vm.expect("login:")
t_login = time.time() - t0
vm.sendline(args.user)
if args.password:
    vm.expect(["Password:", "Senha:"])
    vm.sendline(args.password)
vm.expect(r"\$ ")
vm.sendline("export TERM=dumb SYSTEMD_COLORS=0 PS1='$ '; stty cols 200 -echo")
time.sleep(1)
# Strip CSI and OSC escape sequences (systemd's shell integration emits OSC 3008).
ESC = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")


def shot(path):
    s = socket.socket(socket.AF_UNIX)
    s.connect(f"{tmp}/mon.sock")
    s.sendall(f"screendump {os.path.abspath(path)} -f png\n".encode())
    time.sleep(1.5)
    s.close()
    return f"(screenshot: {path})"


def keys(spec):
    """Type with QEMU sendkey: '@keys ret', '@keys type:Ana ret', ..."""
    s = socket.socket(socket.AF_UNIX)
    s.connect(f"{tmp}/mon.sock")
    for tok in spec.split():
        names = []
        if tok.startswith("type:"):
            for ch in tok[5:]:
                names.append(f"shift-{ch.lower()}" if ch.isupper() else ch)
        else:
            names.append(tok)
        for n in names:
            s.sendall(f"sendkey {n}\n".encode())
            time.sleep(0.15)
    s.close()
    return ""


def run(cmd, timeout=None):
    timeout = timeout or args.timeout
    if cmd.startswith("@mouse "):  # relative move: '@mouse 0 500'
        dx, dy = cmd.split()[1:3]
        m = socket.socket(socket.AF_UNIX)
        m.connect(f"{tmp}/mon.sock")
        m.sendall(f"mouse_move {dx} {dy}\n".encode())
        time.sleep(0.5)
        m.close()
        return ""
    if cmd.startswith("@keys "):
        return keys(cmd.split(None, 1)[1])
    if cmd.startswith("@shot "):
        return shot(cmd.split(None, 1)[1])
    if cmd.startswith("@sleep "):
        time.sleep(float(cmd.split()[1]))
        return ""
    # The markers are split in the sent text so the echo can't match them.
    vm.sendline(f"echo __B''EGIN__; {cmd}; echo __E''ND__")
    vm.expect("__BEGIN__", timeout=timeout)
    vm.expect("__END__", timeout=timeout)
    return ESC.sub("", vm.before).replace("\r", "").strip("\n").rstrip()


time.sleep(args.settle)
print(f"== wall clock, QEMU start -> serial login prompt: {t_login:.1f}s")
for cmd in ["uname -r", "systemd-analyze",
            # Kernel start -> top bar running (the desktop is usable).
            "t=$(pgrep -xo tint2) && awk -v e=$(ps -o etimes= -p $t | tr -d \" \") "
            "'{printf \"desktop ready after %.0f s\\n\", $1 - e}' /proc/uptime", "systemd-analyze blame | head -15",
            "free -m",
            # procps-ng 4 reports used = total - available, which also counts
            # the kernel's free-page watermarks. Also show memory really in use.
            "awk '/^(MemTotal|MemFree|Buffers|Cached|SReclaimable):/{m[$1]=$2}"
            " END{printf \"really used: %d MiB\\n\", (m[\"MemTotal:\"]-m[\"MemFree:\"]"
            "-m[\"Buffers:\"]-m[\"Cached:\"]-m[\"SReclaimable:\"])/1024}' /proc/meminfo",
            "swapon --show", "locale | head -1",
            "cat /etc/vconsole.conf", "date",
            "systemctl list-units --type=service --state=running --no-legend",
            "ps -eo rss,comm --sort=-rss | head -15"] + args.cmd:
    print(f"\n$ {cmd}\n{run(cmd)}")
if args.password:
    vm.sendline(f"echo {args.password} | sudo -S poweroff")
else:
    vm.sendline("sudo poweroff")
vm.expect(pexpect.EOF, timeout=180)
print(f"\n(serial log: {tmp}/serial.log)")
