"""Issues: issue list → why it matters / how to fix → affected URLs."""
from __future__ import annotations

import csv
import webbrowser

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QHBoxLayout, QHeaderView, QLineEdit,
                               QSplitter, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ...audits import CATEGORIES
from .. import theme
from ..i18n import t
from ..icons import icon
from ..widgets import Card, button, empty_state, label, pill
from .base import View

SEVS = ["all", "critical", "warning", "opportunity"]


def dot(color: str, size: int = 10) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, size * 2 - 4, size * 2 - 4)
    p.end()
    return QIcon(pm)


class IssuesView(View):
    def __init__(self, main):
        super().__init__(main)
        self.header(t("Issues"), "")
        split = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        ll.setSpacing(10)
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText(t("Search issues…"))
        self.search.addAction(icon("search", theme.palette()["faint"], 16), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self._fill)
        ll.addWidget(self.search)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.sev_group = QButtonGroup(self)
        for i, s in enumerate(SEVS):
            b = button(t("All") if s == "all" else t(s.capitalize()), "Chip")
            b.setCheckable(True)
            b.setChecked(i == 0)
            self.sev_group.addButton(b, i)
            chips.addWidget(b)
        chips.addStretch()
        self.sev_group.idClicked.connect(lambda _: self._fill())
        ll.addLayout(chips)
        self.cat = QComboBox()
        self.cat.addItem(t("All categories"), "")
        for c in CATEGORIES:
            self.cat.addItem(t(c), c)
        self.cat.currentIndexChanged.connect(self._fill)
        ll.addWidget(self.cat)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.setIndentation(12)
        self.tree.setRootIsDecorated(False)
        self.tree.setIconSize(QSize(10, 10))
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.currentItemChanged.connect(lambda cur, _: self._select(cur))
        ll.addWidget(self.tree, 1)
        split.addWidget(left)

        self.right = QWidget()
        self.rl = QVBoxLayout(self.right)
        self.rl.setContentsMargins(8, 0, 0, 0)
        split.addWidget(self.right)
        split.setSizes([400, 900])
        split.setStretchFactor(1, 1)
        self.body.addWidget(split, 1)
        self.current = None
        self._placeholder()

    def _placeholder(self):
        self.clear_layout(self.rl)
        self.rl.addWidget(empty_state("issues", t("Issues"), t("Select an issue to see the affected URLs and how to fix it.")))

    def load(self, session):
        super().load(session)
        self.h_sub.setText(f"{len(session.issues)} issue types · {sum(i['count'] for i in session.issues):,} findings"
                           if session else "")
        self.h_sub.setVisible(bool(session))
        self._fill()
        self._placeholder()

    def focus(self, issue: str | None = None, severity: str | None = None, category: str | None = None):
        if severity in SEVS:
            self.sev_group.button(SEVS.index(severity)).setChecked(True)
        elif issue:
            self.sev_group.button(0).setChecked(True)
        if category is not None:
            self.cat.setCurrentIndex(max(0, self.cat.findData(category)))
        elif issue:
            self.cat.setCurrentIndex(0)
        self._fill()
        if issue:
            for i in range(self.tree.topLevelItemCount()):
                top = self.tree.topLevelItem(i)
                for j in range(top.childCount()):
                    if top.child(j).data(0, Qt.UserRole) == issue:
                        self.tree.setCurrentItem(top.child(j))
                        return

    def _fill(self):
        self.tree.clear()
        if not self.session:
            return
        p = theme.palette()
        q = self.search.text().strip().lower()
        sev = SEVS[self.sev_group.checkedId()] if self.sev_group.checkedId() >= 0 else "all"
        cat = self.cat.currentData()
        by_cat: dict = {}
        for i in self.session.issues:
            if sev != "all" and i["severity"] != sev:
                continue
            if cat and i["category"] != cat:
                continue
            if q and q not in i["title"].lower() and q not in i["category"].lower():
                continue
            by_cat.setdefault(i["category"], []).append(i)
        bold = self.tree.font()
        bold.setBold(True)
        for c in CATEGORIES:
            if c not in by_cat:
                continue
            top = QTreeWidgetItem([t(c), f"{sum(i['count'] for i in by_cat[c]):,}"])
            top.setFont(0, bold)
            top.setForeground(0, QColor(p["muted"]))
            top.setForeground(1, QColor(p["faint"]))
            top.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(top)
            for i in by_cat[c]:
                it = QTreeWidgetItem([i["title"], f"{i['count']:,}"])
                it.setIcon(0, dot(p[i["severity"]]))
                it.setData(0, Qt.UserRole, i["id"])
                it.setToolTip(0, i["why"])
                it.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
                top.addChild(it)
            top.setExpanded(True)
        if not by_cat:
            self.tree.addTopLevelItem(QTreeWidgetItem([t("No issues found"), ""]))

    def _select(self, item):
        if not item or not self.session:
            return
        iid = item.data(0, Qt.UserRole)
        issue = next((i for i in self.session.issues if i["id"] == iid), None)
        if not issue:
            return
        self.current = issue
        self.clear_layout(self.rl)
        head = Card(padding=18, spacing=8)
        r = QHBoxLayout()
        r.addWidget(pill(issue["severity"]))
        r.addWidget(label(t(issue["category"]), "Muted"))
        r.addStretch()
        r.addWidget(label(f"{issue['count']:,} {t('URLs affected')}", "Muted"))
        head.add(r)
        head.add(label(issue["title"], "H1"))
        grid = QHBoxLayout()
        grid.setSpacing(12)
        for title, text, ic in ((t("Why it matters"), issue["why"], "issues"), (t("How to fix"), issue["fix"], "check")):
            c = Card(name="SoftCard", padding=14, spacing=6)
            hr = QHBoxLayout()
            il = label()
            il.setPixmap(icon(ic, theme.palette()["muted"], 16).pixmap(16, 16))
            hr.addWidget(il)
            hr.addWidget(label(title, "H3"))
            hr.addStretch()
            c.add(hr)
            c.add(label(text, wrap=True))
            grid.addWidget(c, 1)
        head.add(grid)
        self.rl.addWidget(head)

        bar = QHBoxLayout()
        bar.addWidget(label(t("Affected URLs"), "H2"))
        bar.addStretch()
        bar.addWidget(button(t("Copy URLs"), icon_name="copy", on=self._copy_urls))
        bar.addWidget(button(t("Export CSV"), icon_name="export", on=self._export))
        bar.addWidget(button(t("Ask AI how to fix"), icon_name="ai", on=lambda: self.main.goto("ai", task="plan")))
        self.rl.addLayout(bar)
        tbl = QTableWidget(len(issue["urls"]), 2)
        tbl.setHorizontalHeaderLabels([t("URL"), t("Detail")])
        tbl.verticalHeader().hide()
        tbl.verticalHeader().setDefaultSectionSize(30)
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setColumnWidth(0, 460)
        tbl.setShowGrid(False)
        tbl.setAlternatingRowColors(True)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setSortingEnabled(False)
        for n, (u, d) in enumerate(issue["urls"]):
            tbl.setItem(n, 0, QTableWidgetItem(u))
            di = QTableWidgetItem(d)
            di.setToolTip(d)
            tbl.setItem(n, 1, di)
        tbl.setSortingEnabled(True)
        tbl.cellDoubleClicked.connect(lambda r_, c_: webbrowser.open(tbl.item(r_, 0).text()))
        self.rl.addWidget(tbl, 1)

    def _copy_urls(self):
        if self.current:
            QGuiApplication.clipboard().setText("\n".join(u for u, _ in self.current["urls"]))
            self.main.toast(f"{len(self.current['urls']):,} URLs copied")

    def _export(self):
        if not self.current:
            return
        dest = self.main.export_destination(f"issue_{self.current['id']}.csv")
        if not dest:
            return
        with open(dest, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["issue", "severity", "url", "detail", "how_to_fix"])
            for u, d in self.current["urls"]:
                w.writerow([self.current["title"], self.current["severity"], u, d, self.current["fix"]])
        self.main.toast(f"{t('Exported')}: {dest}")
