"""Where Auditly keeps its files on Windows, macOS and Linux."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_DIR_NAME = "Auditly"


def downloads_dir() -> Path:
    """The user's Downloads folder (respects relocated folders on Windows and Linux)."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes
            import uuid

            guid = uuid.UUID("{374DE290-123F-4565-9164-39C4925E467B}")  # FOLDERID_Downloads

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]

            g = GUID(guid.fields[0], guid.fields[1], guid.fields[2],
                     (wintypes.BYTE * 8).from_buffer_copy(guid.bytes[8:]))
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) == 0:
                path = Path(out.value)
                ctypes.windll.ole32.CoTaskMemFree(out)
                return path
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        try:
            res = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True, timeout=3)
            p = res.stdout.strip()
            if p and p != str(Path.home()):
                return Path(p)
        except Exception:
            pass
    return Path.home() / "Downloads"


def default_export_root() -> Path:
    return downloads_dir() / APP_DIR_NAME


def data_dir() -> Path:
    """Per-user app data: settings, saved crawl sessions, plugins, profiles."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / APP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def sessions_dir() -> Path:
    d = data_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def profiles_dir() -> Path:
    d = data_dir() / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def plugin_dirs() -> list[Path]:
    d = data_dir() / "plugins"
    d.mkdir(parents=True, exist_ok=True)
    dirs = [d]
    local = Path(__file__).resolve().parent.parent / "plugins"
    if local.is_dir():
        dirs.append(local)
    return dirs


def resource_path(*parts: str) -> Path:
    """Path to a bundled file, working both from source and from a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath(*parts)


def open_path(path: str | Path) -> None:
    path = str(path)
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
