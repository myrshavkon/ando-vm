
#!/usr/bin/env python3

import argparse
import os
import platform
import shutil
import sys
import zipfile

from pathlib import Path


VERSION = "0.1.0"
PROJECT = "ANDO"


def info(message):
    print(f"[ANDO] {message}")


def error(message):
    print(f"[ANDO ERROR] {message}", file=sys.stderr)


def inspect_apk(path):
    apk = Path(path).expanduser().resolve()

    if not apk.exists():
        error(f"APK not found: {apk}")
        return False

    if not apk.is_file():
        error("The supplied path is not a file.")
        return False

    if apk.suffix.lower() != ".apk":
        error("Expected an .apk file.")
        return False

    if not zipfile.is_zipfile(apk):
        error("Invalid APK: APK is not a valid ZIP archive.")
        return False

    try:
        with zipfile.ZipFile(apk) as archive:
            files = archive.namelist()

            if "AndroidManifest.xml" not in files:
                error("Invalid APK: AndroidManifest.xml is missing.")
                return False

            if not any(name.startswith("classes") and
                       name.endswith(".dex") for name in files):
                error("Warning: No DEX bytecode found.")

    except (OSError, zipfile.BadZipFile) as exc:
        error(f"Could not inspect APK: {exc}")
        return False

    info(f"APK validated: {apk.name}")
    info(f"Size: {apk.stat().st_size / 1024 / 1024:.2f} MB")

    return True


def doctor():
    print("\nANDO SYSTEM DIAGNOSTICS")
    print("=" * 40)

    print(f"Architecture: {platform.machine()}")
    print(f"Operating system: {platform.system()}")
    print(f"Kernel: {platform.release()}")

    print(f"Wayland: {'Available' if os.environ.get('WAYLAND_DISPLAY') else 'Not detected'}")

    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    print(f"RAM: {line.split(':')[1].strip()}")
                    break
    except OSError:
        print("RAM: Unknown")

    disk = shutil.disk_usage(Path.home())
    print(f"Free home disk space: {disk.free / (1024**3):.2f} GB")

    print("\nANDROID KERNEL SUPPORT")
    print("-" * 40)

    binder_paths = [
        Path("/dev/binder"),
        Path("/dev/binderfs/binder-control"),
        Path("/dev/hwbinder"),
        Path("/dev/vndbinder"),
    ]

    found = False

    for path in binder_paths:
        if path.exists():
            print(f"FOUND: {path}")
            found = True

    if not found:
        print("Binder devices not detected.")

    config_path = Path(f"/boot/config-{platform.release()}")

    if config_path.exists():
        config = config_path.read_text(errors="ignore")

        for option in [
            "CONFIG_ANDROID_BINDER_IPC",
            "CONFIG_ANDROID_BINDERFS",
        ]:
            for line in config.splitlines():
                if line.startswith(option + "=") or line.startswith("# " + option):
                    print(line)
                    break
    else:
        print("Kernel configuration file not found.")

    print("\nRUNTIME STATUS")
    print("-" * 40)
    print("Android 15 userspace: Not installed")
    print("APK execution: Not available yet")

    print("\nDiagnostics complete.\n")


def status():
    print("ANDO Runtime Status")
    print("-------------------")
    print("CLI version:", VERSION)
    print("Android runtime: Not installed")
    print("Running Android applications: 0")


def runtime_missing():
    error("The Android runtime has not been implemented yet.")
    info("This development build can inspect APK files only.")
    return 1


def main():
    parser = argparse.ArgumentParser(
        prog="ando",
        description="ANDO: Android application runtime for Linux"
    )

    parser.add_argument("--version", action="version",
                        version=f"ANDO {VERSION}")

    parser.add_argument("target", nargs="?",
                        help="APK file or command")

    parser.add_argument("args", nargs="*",
                        help="Additional command arguments")

    parsed = parser.parse_args()

    target = parsed.target
    args = parsed.args

    if not target:
        parser.print_help()
        return 0

    if target == "doctor":
        doctor()
        return 0

    if target == "status":
        status()
        return 0

    if target == "list":
        return runtime_missing()

    if target in ("install", "launch", "uninstall"):
        if not args:
            error(f"Usage: ando {target} <APK or package name>")
            return 1

        if target == "install" and not inspect_apk(args[0]):
            return 1

        return runtime_missing()

    if target == "stop":
        return runtime_missing()

    if target.endswith(".apk"):
        if not inspect_apk(target):
            return 1

        return runtime_missing()

    error(f"Unknown command: {target}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
