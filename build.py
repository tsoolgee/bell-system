# -*- coding: utf-8 -*-
"""אריזת המערכת לקובץ EXE יחיד."""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "BellSystem"


def make_icon():
    """יוצר assets/icon.ico מהפעמון שמצויר בקוד."""
    sys.path.insert(0, ROOT)
    from bells.tray import make_icon as draw
    assets = os.path.join(ROOT, "assets")
    os.makedirs(assets, exist_ok=True)
    path = os.path.join(assets, "icon.ico")
    base = draw("ok").resize((256, 256))
    base.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


def main():
    icon = make_icon()
    for folder in ("build", "dist"):
        shutil.rmtree(os.path.join(ROOT, folder), ignore_errors=True)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", NAME,
        "--icon", icon,
        "--add-data", os.path.join(ROOT, "bells", "web") + os.pathsep + "web",
        "--hidden-import", "pyluach",
        "--hidden-import", "pystray._win32",
        "--collect-submodules", "pyluach",
        "--exclude-module", "tkinter",
        "--exclude-module", "numpy",
        "--exclude-module", "matplotlib",
        os.path.join(ROOT, "run.py"),
    ]
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode:
        return result.returncode
    exe = os.path.join(ROOT, "dist", NAME + ".exe")
    print("\nנבנה: %s (%.1f MB)" % (exe, os.path.getsize(exe) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
