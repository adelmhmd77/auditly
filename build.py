#!/usr/bin/env python3
"""Build a standalone Auditly app that runs without Python installed.

    python build.py

Output (in ./dist):
    Windows → Auditly.exe        (single file, double-click to run)
    macOS   → Auditly.app        (drag to Applications)
    Linux   → Auditly            (single executable file)

PyInstaller builds for the system it runs on, so run this on Windows to get the .exe
(or use the GitHub Actions workflow in .github/workflows/build.yml to build all three).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)


def make_icon() -> Path:
    """Render the app icon from the built-in SVG logo."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    sys.path.insert(0, str(ROOT))
    from auditly.ui.icons import logo_pixmap
    assets = ROOT / "auditly" / "assets"
    assets.mkdir(exist_ok=True)
    png = assets / "auditly.png"
    logo_pixmap(512).save(str(png))
    if sys.platform.startswith("win"):
        ico = assets / "auditly.ico"
        from PIL import Image
        Image.open(png).save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        return ico
    return png


def main() -> None:
    py = sys.executable
    subprocess.check_call([py, "-m", "pip", "install", "-q", "-r", "requirements.txt", "pyinstaller>=6.5", "pillow"])
    icon = make_icon()
    sep = ";" if sys.platform.startswith("win") else ":"
    args = [
        py, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "Auditly",
        "--icon", str(icon),
        "--add-data", f"{icon}{sep}auditly/assets",
        "--collect-submodules", "auditly",
        "--collect-submodules", "lxml",
        "--collect-data", "certifi",
        "--collect-submodules", "anthropic",
        "--hidden-import", "cssselect",
        "--exclude-module", "tkinter",
        "--exclude-module", "playwright",
    ]
    if sys.platform == "darwin":
        args += ["--onedir", "--osx-bundle-identifier", "io.auditly.app"]
    else:
        args += ["--onefile"]
    args.append("run_auditly.py")
    subprocess.check_call(args)
    out = {"win32": "dist/Auditly.exe", "darwin": "dist/Auditly.app"}.get(sys.platform, "dist/Auditly")
    print(f"\nDone: {ROOT / out}")


if __name__ == "__main__":
    main()
