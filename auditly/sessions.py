"""Saved crawl sessions (each one is a folder holding crawl.db)."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .crawl import db as dbm
from .crawl.urls import strip_www
from .paths import sessions_dir


def new_session_dir(start_url: str) -> Path:
    host = strip_www(urlsplit(start_url if "://" in start_url else "https://" + start_url).hostname or "site")
    d = sessions_dir() / f"{host}_{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def info(path: Path) -> dict | None:
    dbp = Path(path) / "crawl.db"
    if not dbp.exists():
        return None
    try:
        db = sqlite3.connect(f"file:{dbp.as_posix()}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        pages = db.execute("SELECT COUNT(*) FROM pages WHERE internal=1").fetchone()[0]
        out = {
            "id": Path(path).name, "path": str(path), "url": dbm.get_meta(db, "start_url", ""),
            "status": dbm.get_meta(db, "status", "unknown"), "started": dbm.get_meta(db, "started_at", ""),
            "finished": dbm.get_meta(db, "finished_at", ""), "pages": pages,
            "health": dbm.get_meta(db, "health", None, as_json=True),
            "issues": db.execute("SELECT COUNT(*) FROM issues").fetchone()[0],
        }
        db.close()
        if out["status"] == "running":
            out["status"] = "interrupted"  # the app isn't running it now → it crashed or was killed
        return out
    except sqlite3.Error:
        return None


def list_sessions() -> list[dict]:
    out = []
    for d in sessions_dir().iterdir():
        if d.is_dir():
            i = info(d)
            if i:
                out.append(i)
    out.sort(key=lambda s: s["started"] or "", reverse=True)
    return out


def delete(path: str | Path) -> None:
    p = Path(path)
    if p.is_dir() and p.parent == sessions_dir():
        shutil.rmtree(p)


def host_of_session(path: str | Path) -> str:
    return Path(path).name.rsplit("_", 1)[0]
