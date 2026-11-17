#!/usr/bin/env python3

import errno
import fcntl
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

BINDERFS = Path("/dev/binderfs")
CONTROL = BINDERFS / "binder-control"
DEVICES = ("binder", "hwbinder", "vndbinder")

# _IOWR('b', 1, struct binderfs_device)
# struct binderfs_device is 256 bytes + two uint32_t values.
BINDER_CTL_ADD = (
    (3 << 30)
    | (264 << 16)
    | (ord("b") << 8)
    | 1
)


def say(message):
    print(f"[ando-vm] {message}")


def fail(message):
    print(f"[ando-vm ERROR] {message}", file=sys.stderr)


def binderfs_mounted():
    try:
        result = subprocess.run(
            ["findmnt", "-n", "-T", str(BINDERFS), "-t", "binder"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return os.path.ismount(BINDERFS)


def device_status():
    for name in DEVICES:
        path = BINDERFS / name
        if path.exists():
            say(f"FOUND: {path}")
        else:
            say(f"MISSING: {path}")


def status():
    print("Binder status")
    print("-------------")

    if binderfs_mounted():
        say(f"BinderFS mounted at {BINDERFS}")
    else:
        say("BinderFS is not mounted")

    if CONTROL.exists():
        say("Binder control device is available")
    else:
        say("Binder control device is missing")

    device_status()

    return 0 if (
        binderfs_mounted()
        and CONTROL.exists()
        and all((BINDERFS / name).exists() for name in DEVICES)
    ) else 1


def mount_binderfs():
    if binderfs_mounted():
        say("BinderFS is already mounted")
        return True

    if os.geteuid() != 0:
        fail("Root privileges are required to mount BinderFS.")
        fail("Run: sudo ando binder setup")
        return False

    BINDERFS.mkdir(parents=True, exist_ok=True)

    if not shutil.which("mount"):
        fail("The mount command was not found.")
        return False

    result = subprocess.run(
        ["mount", "-t", "binder", "binder", str(BINDERFS)],
        check=False,
    )

    if result.returncode != 0:
        fail("Could not mount BinderFS.")
        return False

    say(f"Mounted BinderFS at {BINDERFS}")
    return True


def create_device(name):
    path = BINDERFS / name

    if path.exists():
        say(f"Already exists: {path}")
        return True

    buffer = bytearray(264)
    encoded_name = name.encode("ascii")
    buffer[:len(encoded_name)] = encoded_name

    try:
        with CONTROL.open("rb") as control:
            fcntl.ioctl(control.fileno(), BINDER_CTL_ADD, buffer, True)
    except OSError as exc:
        if exc.errno == errno.EEXIST and path.exists():
            say(f"Already exists: {path}")
            return True

        fail(f"Could not create {name}: {exc}")
        return False

    major, minor = struct.unpack_from("=II", buffer, 256)
    say(f"Created {path} (major={major}, minor={minor})")
    return True


def setup():
    if os.geteuid() != 0:
        fail("Root privileges are required.")
        fail("Run: sudo ando binder setup")
        return 1

    if not mount_binderfs():
        return 1

    if not CONTROL.exists():
        fail(f"Binder control device not found: {CONTROL}")
        return 1

    success = True

    for name in DEVICES:
        if not create_device(name):
            success = False

    if success:
        say("Binder setup completed.")

    return 0 if success else 1
