"""Site structure: URL tree, click-depth distribution and strongest pages by internal link score."""
from __future__ import annotations

import webbrowser
from urllib.parse import urlsplit

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QHeaderView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from .. import theme
from ..data import status_color
from ..i18n import t
from ..widgets import BarList, Card, label
from .base import View


class StructureView(View):
    def __init__(self, main):
        super().__init__(main)
        self.header(t("Site structure"), "")
        row = QHBoxLayout()
        row.setSpacing(14)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([t("Path"), t("Pages"), t("Issues"), t("Status")])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            self.tree.header().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemDoubleClicked.connect(lambda it, _: it.data(0, Qt.UserRole) and webbrowser.open(it.data(0, Qt.UserRole)))
        row.addWidget(self.tree, 3)
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(12)
        c1 = Card()
        c1.add(label(t("Pages by click depth"), "H2"))
        self.depth = BarList()
        self.depth.clicked.connect(lambda _: self.main.goto("pages"))
        c1.add(self.depth)
        sl.addWidget(c1)
        c2 = Card()
        c2.add(label("Strongest pages (link score)", "H2"))
        self.top = BarList(row_h=26)
        c2.add(self.top)
        sl.addWidget(c2)
        sl.addStretch()
        row.addWidget(side, 2)
        self.body.addLayout(row, 1)

    def load(self, session):
        super().load(session)
        self.tree.clear()
        if not session:
            self.depth.set_rows([])
            self.top.set_rows([])
            return
        p = theme.palette()
        self.h_sub.setText(session.start_url)
        self.h_sub.show()
        root: dict = {}
        for pg in session.pages:
            s = urlsplit(pg["url"])
            parts = [s.netloc] + [x for x in s.path.split("/") if x]
            if s.query:
                parts.append("?" + s.query[:60])
            node = root
            for part in parts:
                node = node.setdefault(part, {"_c": {}, "_n": 0, "_i": 0, "_bad": 0, "_url": None})
                node["_n"] += 1
                node["_i"] += pg.get("issue_count") or 0
                if (pg.get("status") or 0) >= 400 or pg.get("status") == 0:
                    node["_bad"] += 1
                node = node["_c"]
            # mark exact page
        self._add(self.tree.invisibleRootItem(), root, session, "", p)
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setExpanded(True)
        self.depth.set_rows([(f"{t('Depth')} {d}", n, p["primary"] if d <= 3 else p["warning"]) for d, n in session.depths])
        best = sorted((pg for pg in session.pages if pg.get("link_score") is not None), key=lambda x: -x["link_score"])[:12]
        self.top.set_rows([(urlsplit(pg["url"]).path or "/", pg["link_score"], p["accent"]) for pg in best])

    def _add(self, parent, nodes: dict, session, prefix: str, p):
        for name in sorted(nodes, key=lambda k: -nodes[k]["_n"]):
            n = nodes[name]
            path = f"{prefix}/{name}" if prefix else name
            it = QTreeWidgetItem([name if prefix else name, f"{n['_n']:,}", f"{n['_i']:,}" if n["_i"] else "",
                                  f"{n['_bad']} errors" if n["_bad"] else "OK"])
            it.setForeground(3, QColor(p["critical"] if n["_bad"] else p["ok"]))
            for scheme in ("https://", "http://"):
                if scheme + path in session.by_url or scheme + path + "/" in session.by_url:
                    url = scheme + path if scheme + path in session.by_url else scheme + path + "/"
                    it.setData(0, Qt.UserRole, url)
                    col = status_color(session.by_url[url].get("status"))
                    if col and col != p["ok"]:
                        it.setForeground(0, QColor(col))
                    break
            parent.addChild(it)
            if n["_c"]:
                self._add(it, n["_c"], session, path, p)
