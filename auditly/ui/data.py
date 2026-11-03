"""In-memory view of a crawl session for the UI, plus the table models."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor

from ..audits import all_audits
from ..crawl import db as dbm
from ..export.exporters import collect
from . import theme
from .i18n import t

PAGE_COLUMNS = [  # key, label, width, visible by default
    ("url", "URL", 380, True), ("status", "Status", 64, True), ("indexability", "Indexability", 170, True),
    ("title", "Title", 260, True), ("title_len", "Title length", 80, False), ("meta_description", "Meta description", 260, False),
    ("meta_description_len", "Meta length", 80, False), ("h1", "H1", 200, True), ("h1_count", "H1 count", 70, False),
    ("word_count", "Words", 70, True), ("response_ms", "Response (ms)", 96, True), ("ttfb_ms", "TTFB (ms)", 80, False),
    ("size", "Size (KB)", 76, False), ("depth", "Depth", 60, True), ("inlinks", "Inlinks", 70, True),
    ("link_score", "Link score", 80, True), ("issue_count", "Issues", 64, True), ("canonical", "Canonical", 260, False),
    ("meta_robots", "Meta robots", 120, False), ("schema_types", "Schema", 160, False), ("lang", "Lang", 56, False),
    ("hreflang_count", "Hreflang", 70, False), ("readability", "Readability", 84, False), ("images", "Images", 64, False),
    ("images_missing_alt", "Missing alt", 84, False), ("internal_links", "Internal links", 96, False),
    ("external_links", "External links", 96, False), ("render_blocking", "Render-blocking", 110, False),
    ("content_type", "Content type", 120, False), ("redirect_to", "Redirect to", 260, False), ("error", "Error", 200, False),
]
NUMERIC = {"status", "title_len", "meta_description_len", "h1_count", "word_count", "response_ms", "ttfb_ms", "size", "depth",
           "inlinks", "link_score", "issue_count", "hreflang_count", "readability", "images", "images_missing_alt",
           "internal_links", "external_links", "render_blocking"}


class SessionData:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.db_path = self.path / "crawl.db"
        self.reload()

    def reload(self) -> None:
        db = dbm.connect(self.db_path, readonly=True)
        try:
            self.meta = {r[0]: r[1] for r in db.execute("SELECT key, value FROM meta")}
            self.start_url = self.meta.get("start_url", "")
            self.summary = collect(db)
            self.issues = self.summary["issues"]
            self.issues_by_url = defaultdict(list)
            for i in self.issues:
                for u, d in i["urls"]:
                    self.issues_by_url[u].append((i, d))
            cfg = self.json_meta("config", {}) or {}
            self.extract_names = [e["name"] for e in cfg.get("extractions", []) if e.get("name")]
            rows = db.execute("SELECT p.*, COALESCE(s.inlinks,0) AS inlinks, s.link_score FROM pages p "
                              "LEFT JOIN scores s ON s.url=p.url WHERE p.internal=1 ORDER BY p.depth, p.url").fetchall()
            self.pages = []
            for r in rows:
                d = dict(r)
                d["issue_count"] = len({i["id"] for i, _ in self.issues_by_url.get(d["url"], [])})
                if d.get("size"):
                    d["size"] = round(d["size"] / 1024, 1)
                if self.extract_names:
                    try:
                        ex = json.loads(d.get("data") or "{}").get("extract", {})
                    except ValueError:
                        ex = {}
                    for n in self.extract_names:
                        d[f"ex:{n}"] = ex.get(n, "")
                d.pop("data", None)
                self.pages.append(d)
            self.by_url = {p["url"]: p for p in self.pages}
            self.depths = [(r[0], r[1]) for r in db.execute(
                "SELECT depth, COUNT(*) FROM pages WHERE internal=1 AND status=200 GROUP BY depth ORDER BY depth")]
        finally:
            db.close()

    def json_meta(self, key, default=None):
        v = self.meta.get(key)
        if v is None:
            return default
        try:
            return json.loads(v)
        except (TypeError, ValueError):
            return v

    def links(self, url: str, direction: str = "in", limit: int = 500) -> list[tuple]:
        db = dbm.connect(self.db_path, readonly=True)
        try:
            if direction == "in":
                q = "SELECT src, anchor, nofollow FROM links WHERE dst=? AND kind='a' AND src<>dst LIMIT ?"
            else:
                q = "SELECT dst, anchor, nofollow FROM links WHERE src=? AND kind IN ('a','redirect') LIMIT ?"
            return [tuple(r) for r in db.execute(q, (url, limit))]
        finally:
            db.close()

    def page_data(self, url: str) -> dict:
        db = dbm.connect(self.db_path, readonly=True)
        try:
            r = db.execute("SELECT data FROM pages WHERE url=?", (url,)).fetchone()
            return json.loads(r[0]) if r and r[0] else {}
        except ValueError:
            return {}
        finally:
            db.close()


def status_color(status) -> str | None:
    p = theme.palette()
    try:
        s = int(status or 0)
    except (TypeError, ValueError):
        return None
    if 200 <= s < 300:
        return p["ok"]
    if 300 <= s < 400:
        return p["warning"]
    if s >= 400 or s == 0:
        return p["critical"]
    return None


class PagesModel(QAbstractTableModel):
    def __init__(self, columns=None):
        super().__init__()
        self.columns = list(columns or PAGE_COLUMNS)
        self.rows: list[dict] = []

    def set_columns(self, columns):
        self.beginResetModel()
        self.columns = list(columns)
        self.endResetModel()

    def set_rows(self, rows: list[dict]):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def append_rows(self, rows: list[dict]):
        if not rows:
            return
        self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows) + len(rows) - 1)
        self.rows.extend(rows)
        self.endInsertRows()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return t(self.columns[section][1])
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key = self.columns[index.column()][0]
        v = row.get(key)
        if role == Qt.DisplayRole:
            if key == "status" and (v == 0 or v is None):
                return "Blocked" if row.get("indexability") == "Blocked by robots.txt" else ("ERR" if row.get("error") else "")
            if v is None:
                return ""
            if isinstance(v, float):
                return f"{v:g}"
            return str(v)
        if role == Qt.UserRole:  # sort key
            if key in NUMERIC:
                try:
                    return float(v or 0)
                except (TypeError, ValueError):
                    return 0.0
            return str(v or "").lower()
        if role == Qt.ForegroundRole:
            if key == "status":
                c = status_color(v)
                return QColor(c) if c else None
            if key == "indexability" and v and v != "Indexable":
                return QColor(theme.palette()["warning"])
            if key == "issue_count" and v:
                return QColor(theme.palette()["critical"])
            if key == "url":
                return QColor(theme.palette()["text"])
        if role == Qt.ToolTipRole and key in ("url", "title", "meta_description", "h1", "canonical", "error", "redirect_to"):
            return str(v or "")
        if role == Qt.TextAlignmentRole and key in NUMERIC:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None


class PagesFilter(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.mode = "All"
        self.setSortRole(Qt.UserRole)

    def set_text(self, s: str):
        self.text = s.strip().lower()
        self.invalidateFilter()

    def set_mode(self, m: str):
        self.mode = m
        self.invalidateFilter()

    def filterAcceptsRow(self, r, parent):
        row = self.sourceModel().rows[r]
        if self.text:
            hay = f"{row.get('url', '')} {row.get('title', '')} {row.get('h1', '')}".lower()
            if self.text not in hay:
                return False
        m = self.mode
        if m == "All":
            return True
        s = row.get("status") or 0
        if m in ("2xx", "3xx", "4xx", "5xx"):
            return str(s).startswith(m[0]) and s != 0
        if m == "Non-indexable":
            return row.get("indexability") not in ("Indexable", None)
        if m == "With issues":
            return bool(row.get("issue_count"))
        return True


def audit_titles() -> dict:
    return {a.id: a for a in all_audits()}
