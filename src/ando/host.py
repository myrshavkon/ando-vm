
#!/usr/bin/env python3

import glob
import os
import platform
from pathlib import Path
import subprocess


def check(name, result, detail=""):
    symbol = "OK" if result else "MISSING"
    print(f"[{symbol:7}] {name}")
    if detail:
        print(f"         {detail}")


def kernel_config(option):
    config_files = [
        Path(f"/usr/lib/modules/{platform.release()}/build/.config"),
        Path(f"/boot/config-{platform.release()}"),
        Path("/proc/config.gz"),
    ]

    for path in config_files:
        if not path.exists():
            continue

        try:
            if str(path).endswith(".gz"):
                result = subprocess.run(
                    ["zcat", str(path)],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                lines = result.stdout.splitlines()
            else:
                lines = path.read_text(errors="ignore").splitlines()

            for line in lines:
                if line.startswith(option + "="):
                    return line.split("=", 1)[1]
                if line == f"# {option} is not set":
                    return "n"

        except (OSError, subprocess.SubprocessError):
            pass

    return "unknown"


def doctor():
    print("\n================================")
    print("       ando-vm HOST CHECK")
    print("================================\n")

    print("SYSTEM")
    print("--------------------------------")
    print("Architecture:", platform.machine())
    print("Kernel:", platform.release())
    print("Distribution: Arch Linux (expected)")
    print("Python:", platform.python_version())

    print("\nMEMORY")
    print("--------------------------------")

    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith(("MemTotal:", "MemAvailable:")):
                print(line)
    except OSError:
        print("Could not read memory information.")

    print("\nANDROID BINDER")
    print("--------------------------------")

    binder_config = kernel_config("CONFIG_ANDROID_BINDER_IPC")
    rust_binder_config = kernel_config("CONFIG_ANDROID_BINDER_IPC_RUST")

    print("CONFIG_ANDROID_BINDER_IPC:", binder_config)
    print("CONFIG_ANDROID_BINDER_IPC_RUST:", rust_binder_config)

    binderfs = Path("/dev/binderfs")
    control = binderfs / "binder-control"

    check("BinderFS mount", os.path.ismount(binderfs), str(binderfs))
    check("Binder control device", control.exists(), str(control))

    for name in ("binder", "hwbinder", "vndbinder"):
        device = binderfs / name
        check(f"Binder device: {name}", device.exists(), str(device))

    print("\nLINUX NAMESPACES")
    print("--------------------------------")

    for namespace in ["user", "pid", "mnt", "net", "ipc", "uts"]:
        path = Path(f"/proc/self/ns/{namespace}")
        check(namespace, path.exists(), str(path))

    print("\nCGROUPS")
    print("--------------------------------")

    controllers = Path("/sys/fs/cgroup/cgroup.controllers")

    check(
        "Cgroup v2",
        controllers.exists(),
        controllers.read_text().strip() if controllers.exists()
        else "Unified cgroup hierarchy not detected."
    )

    print("\nGRAPHICS")
    print("--------------------------------")

    render_nodes = glob.glob("/dev/dri/renderD*")
    card_nodes = glob.glob("/dev/dri/card*")

    check("DRM render nodes", bool(render_nodes),
          ", ".join(render_nodes) or "No render nodes found.")

    check("DRM card nodes", bool(card_nodes),
          ", ".join(card_nodes) or "No card nodes found.")

    try:
        result = subprocess.run(
            ["lspci", "-nnk"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        for line in result.stdout.splitlines():
            if any(word in line.lower() for word in
                   ["vga", "3d controller", "display controller"]):
                print(line)

    except (FileNotFoundError, subprocess.SubprocessError):
        print("Install pciutils for GPU identification.")

    print("\nDESKTOP")
    print("--------------------------------")

    check("Wayland session", bool(os.environ.get("WAYLAND_DISPLAY")),
          os.environ.get("WAYLAND_DISPLAY", "Not detected"))

    check("XDG_RUNTIME_DIR", bool(os.environ.get("XDG_RUNTIME_DIR")),
          os.environ.get("XDG_RUNTIME_DIR", "Not detected"))

    print("\n================================")
    print("Host inspection complete.")
    print("No system configuration was changed.")
    print("================================\n")
