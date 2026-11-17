#!/usr/bin/env python3

import argparse
import sys
import zipfile

from pathlib import Path

VERSION = "0.2.0"
PROJECT = "ando-vm"


def info(message):
    print(f"[{PROJECT}] {message}")


def error(message):
    print(f"[{PROJECT} ERROR] {message}", file=sys.stderr)


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

            if not any(
                name.startswith("classes") and name.endswith(".dex")
                for name in files
            ):
                info("Warning: No DEX bytecode found.")

    except (OSError, zipfile.BadZipFile) as exc:
        error(f"Could not inspect APK: {exc}")
        return False

    info(f"APK validated: {apk.name}")
    info(f"Size: {apk.stat().st_size / 1024 / 1024:.2f} MB")
    return True


def doctor():
    from ando.host import doctor as run_doctor
    run_doctor()


def status():
    print("ando-vm Runtime Status")
    print("----------------------")
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
        description="ando-vm: Android application runtime for Linux",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"ando-vm {VERSION}",
    )

    parser.add_argument("target", nargs="?", help="APK file or command")
    parser.add_argument("args", nargs="*", help="Additional arguments")

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

    if target == "binder":
        if not args:
            parser.error("Usage: ando binder <status|setup>")

        from ando import binder

        if args[0] == "status":
            return binder.status()

        if args[0] == "setup":
            return binder.setup()

        parser.error(f"Unknown Binder command: {args[0]}")

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
