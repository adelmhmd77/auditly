"""Saved crawls: open, resume (crash recovery) or delete."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QMessageBox, QTableWidget, QTableWidgetItem

from ... import sessions as sessions_mod
from .. import theme
from ..i18n import t
from ..widgets import button
from .base import View


class HistoryView(View):
    def __init__(self, main):
        super().__init__(main)
        self.header(t("Saved crawls"), "Every crawl is saved automatically. Interrupted crawls can be resumed.",
                    [button(t("Open"), "Primary", "folder", on=self.open_selected),
                     button(t("Resume"), icon_name="play", on=self.resume_selected),
                     button(t("Delete"), "Danger", "trash", on=self.delete_selected)])
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([t("Website"), t("Status"), t("Pages"), t("Health score"), t("Issues"), t("Started")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(lambda _: self.open_selected())
        self.body.addWidget(self.table, 1)
        self.rows = []

    def load(self, session):
        super().load(session)
        p = theme.palette()
        self.rows = sessions_mod.list_sessions()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.rows))
        for i, s in enumerate(self.rows):
            vals = [s["url"], t(s["status"]), s["pages"], s["health"] if s["health"] is not None else "", s["issues"],
                    s["started"][:16].replace("T", " ")]
            for c, v in enumerate(vals):
                it = QTableWidgetItem()
                it.setData(Qt.DisplayRole, v)
                it.setData(Qt.UserRole, s["path"])
                if c == 1:
                    it.setForeground(QColor(p["ok"] if s["status"] == "complete" else p["warning"]))
                self.table.setItem(i, c, it)

    def _selected(self):
        r = self.table.currentRow()
        if r < 0:
            return None
        return next((s for s in self.rows if s["path"] == self.table.item(r, 0).data(Qt.UserRole)), None)

    def open_selected(self):
        s = self._selected()
        if s:
            self.main.open_session(s["path"])

    def resume_selected(self):
        s = self._selected()
        if not s:
            return
        if s["status"] == "complete":
            self.main.toast("This crawl already finished.")
            return
        self.main.resume_session(s["path"])

    def delete_selected(self):
        s = self._selected()
        if not s:
            return
        if QMessageBox.question(self, "Auditly", f"Delete the crawl of {s['url']}?") == QMessageBox.Yes:
            if self.main.session and str(self.main.session.path) == s["path"]:
                self.main.set_session(None)
            sessions_mod.delete(s["path"])
            self.load(self.main.session)


__all__ = ["HistoryView", "QHBoxLayout"]
