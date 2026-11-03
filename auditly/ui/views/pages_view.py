"""Pages: every crawled URL in a filterable, sortable table with a detail panel."""
from __future__ import annotations

import csv
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView,
                               QLineEdit, QMenu, QScrollArea, QSplitter, QTableView, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from .. import theme
from ..data import PAGE_COLUMNS, PagesFilter, PagesModel, status_color
from ..i18n import t
from ..icons import icon
from ..widgets import Card, button, label, pill, status_pill
from .base import View

FILTERS = ["All", "2xx", "3xx", "4xx", "5xx", "Non-indexable", "With issues"]


class PagesView(View):
    def __init__(self, main):
        super().__init__(main)
        self.header(t("Pages"), "")
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText(t("Search URLs, titles, H1…"))
        self.search.addAction(icon("search", theme.palette()["faint"], 16), QLineEdit.LeadingPosition)
        self.search.setMinimumWidth(300)
        bar.addWidget(self.search)
        self.chips = QButtonGroup(self)
        for i, f in enumerate(FILTERS):
            b = button(t(f), "Chip")
            b.setCheckable(True)
            b.setChecked(i == 0)
            self.chips.addButton(b, i)
            bar.addWidget(b)
        bar.addStretch()
        self.cols_btn = button(t("Columns"), icon_name="columns")
        bar.addWidget(self.cols_btn)
        bar.addWidget(button(t("Export view"), icon_name="export", on=self.export_view))
        self.body.addLayout(bar)

        split = QSplitter(Qt.Horizontal)
        self.model = PagesModel()
        self.proxy = PagesFilter()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setSectionsMovable(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.doubleClicked.connect(lambda _: self._open_selected())
        self.table.selectionModel().currentRowChanged.connect(lambda cur, _: self.show_detail(cur))
        split.addWidget(self.table)

        self.detail_area = QScrollArea()
        self.detail_area.setWidgetResizable(True)
        self.detail_area.setMinimumWidth(340)
        self.detail_area.setFrameShape(QScrollArea.NoFrame)
        self.detail_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.detail = QWidget()
        self.detail_area.setWidget(self.detail)
        self.detail_lay = QVBoxLayout(self.detail)
        self.detail_lay.setContentsMargins(14, 0, 0, 0)
        self.detail_lay.addWidget(label(t("Select a page to see details."), "Muted"))
        self.detail_lay.addStretch()
        split.addWidget(self.detail_area)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([900, 380])
        self.body.addWidget(split, 1)
        self.count = label("", "Faint")
        self.body.addWidget(self.count)

        self.search.textChanged.connect(self._filter_text)
        self.chips.idClicked.connect(lambda i: (self.proxy.set_mode(FILTERS[i]), self._update_count()))
        self.visible = {k for k, _, _, v in PAGE_COLUMNS if v}
        self._build_cols_menu()
        self._apply_columns()

    # ------------------------------------------------------------------ columns
    def _all_columns(self):
        cols = list(PAGE_COLUMNS)
        if self.session:
            cols += [(f"ex:{n}", n, 160, True) for n in self.session.extract_names]
        return cols

    def _build_cols_menu(self):
        m = QMenu(self)
        for key, lab, _, _ in self._all_columns():
            a = QAction(t(lab), m, checkable=True)
            a.setChecked(key in self.visible or key.startswith("ex:"))
            a.toggled.connect(lambda on, k=key: self._toggle_col(k, on))
            m.addAction(a)
        self.cols_btn.setMenu(m)

    def _toggle_col(self, key, on):
        (self.visible.add if on else self.visible.discard)(key)
        self._apply_columns()

    def _apply_columns(self):
        cols = [c for c in self._all_columns() if c[0] in self.visible or (c[0].startswith("ex:") and c[0] not in self.hidden_ex)]
        self.model.set_columns(cols)
        for i, (_, _, w, _) in enumerate(cols):
            self.table.setColumnWidth(i, w)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

    hidden_ex: set = set()

    # ------------------------------------------------------------------ data
    def load(self, session):
        super().load(session)
        self._build_cols_menu()
        self._apply_columns()
        self.model.set_rows(session.pages if session else [])
        self.h_sub.setText(session.start_url if session else "")
        self.h_sub.setVisible(bool(session))
        self._update_count()
        self._clear_detail()

    def live_reset(self):
        self.session = None
        self.model.set_rows([])
        self._clear_detail()
        self._update_count()

    def live_append(self, rows):
        self.model.append_rows([r for r in rows if r.get("internal")])
        self._update_count()

    def set_filter(self, mode: str):
        if mode in FILTERS:
            self.chips.button(FILTERS.index(mode)).setChecked(True)
            self.proxy.set_mode(mode)
            self._update_count()

    def _filter_text(self, s):
        self.proxy.set_text(s)
        self._update_count()

    def _update_count(self):
        self.count.setText(f"{self.proxy.rowCount():,} / {self.model.rowCount():,}")

    def _row(self, proxy_index):
        if not proxy_index.isValid():
            return None
        return self.model.rows[self.proxy.mapToSource(proxy_index).row()]

    # ------------------------------------------------------------------ detail
    def _clear_detail(self):
        self.clear_layout(self.detail_lay)
        self.detail_lay.addWidget(label(t("Select a page to see details."), "Muted"))
        self.detail_lay.addStretch()

    def show_detail(self, idx):
        row = self._row(idx)
        if not row:
            return
        self.clear_layout(self.detail_lay)
        p = theme.palette()
        card = Card(padding=16, spacing=8)
        u = label(row["url"], "H3", wrap=True)
        u.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card.add(u)
        top = QHBoxLayout()
        st = row.get("status") or 0
        sp = status_pill(200 <= st < 300 if st else False, str(st or row.get("error") or "—")[:40])
        top.addWidget(sp)
        top.addWidget(label(row.get("indexability") or "", "Muted"))
        top.addStretch()
        card.add(top)
        acts = QHBoxLayout()
        acts.addWidget(button(t("Open in browser"), icon_name="external", on=lambda: webbrowser.open(row["url"])))
        acts.addWidget(button(t("Copy URL"), icon_name="copy", on=lambda: self._copy(row["url"])))
        acts.addStretch()
        card.add(acts)
        g = QGridLayout()
        g.setVerticalSpacing(6)
        g.setHorizontalSpacing(12)
        fields = [("Title", row.get("title")), ("Meta description", row.get("meta_description")), ("H1", row.get("h1")),
                  ("Canonical", row.get("canonical")), ("Words", row.get("word_count")), ("Response (ms)", row.get("response_ms")),
                  ("Depth", row.get("depth")), ("Inlinks", row.get("inlinks")), ("Link score", row.get("link_score")),
                  ("Schema", row.get("schema_types")), ("Lang", row.get("lang")), ("Redirect to", row.get("redirect_to")),
                  ("Error", row.get("error"))]
        r = 0
        for k, v in fields:
            if v in (None, ""):
                continue
            g.addWidget(label(t(k), "Faint"), r, 0, Qt.AlignTop)
            vl = label(str(v), wrap=True)
            vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            g.addWidget(vl, r, 1)
            r += 1
        g.setColumnStretch(1, 1)
        card.add(g)
        self.detail_lay.addWidget(card)

        if self.session:
            found = self.session.issues_by_url.get(row["url"], [])
            if found:
                ic = Card(padding=16, spacing=6)
                ic.add(label(f"{t('Issues')} · {len(found)}", "H3"))
                for issue, detail in sorted(found, key=lambda x: ("critical", "warning", "opportunity").index(x[0]["severity"])):
                    rr = QHBoxLayout()
                    rr.addWidget(pill(issue["severity"]), 0, Qt.AlignTop)
                    col = QVBoxLayout()
                    col.setSpacing(0)
                    tl = label(issue["title"], wrap=True)
                    tl.setCursor(Qt.PointingHandCursor)
                    tl.setStyleSheet(f"color:{p['accent']};")
                    tl.mouseReleaseEvent = lambda e, iid=issue["id"]: self.main.goto("issues", issue=iid)
                    col.addWidget(tl)
                    if detail:
                        col.addWidget(label(detail[:200], "Faint", wrap=True))
                    rr.addLayout(col, 1)
                    ic.add(rr)
                self.detail_lay.addWidget(ic)
            tabs = QTabWidget()
            for direction, name in (("in", "Inlinks"), ("out", "Outlinks")):
                links = self.session.links(row["url"], direction)
                tw = QTableWidget(len(links), 2)
                tw.setHorizontalHeaderLabels([t("URL"), "Anchor"])
                tw.verticalHeader().hide()
                tw.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
                tw.setEditTriggers(QAbstractItemView.NoEditTriggers)
                tw.setShowGrid(False)
                for i, (u2, anchor, nf) in enumerate(links):
                    tw.setItem(i, 0, QTableWidgetItem(u2))
                    tw.setItem(i, 1, QTableWidgetItem((anchor or "") + ("  [nofollow]" if nf else "")))
                tw.setMinimumHeight(220)
                tw.cellDoubleClicked.connect(lambda r_, c_, w=tw: webbrowser.open(w.item(r_, 0).text()))
                tabs.addTab(tw, f"{t(name)} ({len(links)})")
            self.detail_lay.addWidget(tabs)
        self.detail_lay.addStretch()

    # ------------------------------------------------------------------ actions
    def _copy(self, text):
        QGuiApplication.clipboard().setText(text)
        self.main.toast(t("Copy") + " ✓")

    def _open_selected(self):
        row = self._row(self.table.currentIndex())
        if row:
            webbrowser.open(row["url"])

    def _menu(self, pos):
        row = self._row(self.table.indexAt(pos))
        if not row:
            return
        m = QMenu(self)
        m.addAction(t("Open in browser"), lambda: webbrowser.open(row["url"]))
        m.addAction(t("Copy URL"), lambda: self._copy(row["url"]))
        m.addAction("Analyse content with AI", lambda: self.main.goto("ai", task="quality", url=row["url"]))
        m.exec(self.table.viewport().mapToGlobal(pos))

    def export_view(self):
        if not self.model.rowCount():
            return
        dest = self.main.export_destination(f"pages_{self.proxy.mode.lower().replace(' ', '_')}.csv")
        if not dest:
            return
        cols = self.model.columns
        with open(dest, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([c[1] for c in cols])
            for r in range(self.proxy.rowCount()):
                row = self._row(self.proxy.index(r, 0))
                w.writerow([row.get(c[0], "") for c in cols])
        self.main.toast(f"{t('Exported')}: {dest}")


__all__ = ["PagesView", "status_color", "QFileDialog"]
