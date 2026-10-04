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

import pexpect

ap = argparse.ArgumentParser()
ap.add_argument("iso")
ap.add_argument("--mem", default="3072")
ap.add_argument("--settle", type=int, default=60,
                help="seconds to wait after login before measuring")
ap.add_argument("--cmd", action="append", default=[],
                help="extra command to run and print (repeatable)")
ap.add_argument("--append", default="", help="extra kernel parameters")
args = ap.parse_args()

tmp = tempfile.mkdtemp(prefix="featheros-vm-")
subprocess.run(["7z", "x", "-y", f"-o{tmp}", args.iso,
                "feather/boot/x86_64/*", "-r"], check=True,
               stdout=subprocess.DEVNULL)
boot = os.path.join(tmp, "feather/boot/x86_64")
kernel = glob.glob(os.path.join(boot, "vmlinuz-*"))[0]
initrd = glob.glob(os.path.join(boot, "initramfs-*.img"))[0]
label = subprocess.run(["7z", "l", args.iso], capture_output=True,
                       text=True).stdout
label = next((l.split("=", 1)[1].strip() for l in label.splitlines()
              if l.startswith("Comment") or l.startswith("Volume")), None)
if not label:
    label = "FEATHER_" + time.strftime("%Y%m")

cmdline = (f"archisobasedir=feather archisolabel={label} copytoram=n "
           f"console=ttyS0,115200 "
           f"{args.append}")
qemu = ["qemu-system-x86_64", "-enable-kvm", "-machine", "q35",
        "-cpu", "Penryn", "-smp", "2", "-m", args.mem,
        "-kernel", kernel, "-initrd", initrd, "-append", cmdline,
        "-drive", f"file={args.iso},media=cdrom,readonly=on,if=virtio",
        "-nic", "user,model=virtio-net-pci",
        "-display", "none", "-serial", "stdio", "-no-reboot"]

t0 = time.time()
vm = pexpect.spawn(qemu[0], qemu[1:], encoding="utf-8", timeout=300,
                   codec_errors="replace")
vm.logfile_read = open(os.path.join(tmp, "serial.log"), "w")
vm.expect("login:")
t_login = time.time() - t0
vm.sendline("feather")
vm.expect(r"\$ ")
vm.sendline("export TERM=dumb SYSTEMD_COLORS=0 PS1='$ '; stty cols 200 -echo")
time.sleep(1)
# Strip CSI and OSC escape sequences (systemd's shell integration emits OSC 3008).
ESC = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")


def run(cmd, timeout=120):
    # The markers are split in the sent text so the echo can't match them.
    vm.sendline(f"echo __B''EGIN__; {cmd}; echo __E''ND__")
    vm.expect("__BEGIN__", timeout=timeout)
    vm.expect("__END__", timeout=timeout)
    return ESC.sub("", vm.before).replace("\r", "").strip("\n").rstrip()


time.sleep(args.settle)
print(f"== wall clock, QEMU start -> serial login prompt: {t_login:.1f}s")
for cmd in ["uname -r", "systemd-analyze", "systemd-analyze blame | head -15",
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
vm.sendline("sudo poweroff")
vm.expect(pexpect.EOF, timeout=60)
print(f"\n(serial log: {tmp}/serial.log)")
