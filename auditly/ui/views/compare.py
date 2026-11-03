"""Compare two crawls (before → after)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QTableWidget, QTableWidgetItem

from ... import sessions as sessions_mod
from ...compare import compare
from .. import theme
from ..i18n import t
from ..widgets import KpiCard, button, empty_state, label, run_worker
from .base import View


class CompareView(View):
    def __init__(self, main):
        super().__init__(main)
        self.header(t("Compare crawls"), "Track fixes and regressions between two audits of the same site.")
        row = QHBoxLayout()
        row.addWidget(label(t("Before")))
        self.before = QComboBox()
        row.addWidget(self.before, 1)
        row.addWidget(label(t("After")))
        self.after = QComboBox()
        row.addWidget(self.after, 1)
        row.addWidget(button(t("Compare"), "Primary", "compare", on=self.run))
        self.body.addLayout(row)
        self.kpis = QHBoxLayout()
        self.kpis.setSpacing(12)
        self.body.addLayout(self.kpis)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([t("Issues"), t("Type"), t("Before"), t("After"), t("Fixed"), t("New")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.body.addWidget(self.table, 1)
        self.empty = empty_state("compare", t("Compare crawls"), "Run the same site twice (e.g. before and after fixes), then pick both crawls above.")
        self.body.addWidget(self.empty, 1)
        self.table.hide()

    def load(self, session):
        super().load(session)
        sess = sessions_mod.list_sessions()
        for combo in (self.before, self.after):
            combo.clear()
            for s in sess:
                combo.addItem(f"{s['url'].split('://')[-1]} · {s['started'][:16].replace('T', ' ')} · {s['pages']:,} pages", s["path"])
        if session:
            same = [i for i, s in enumerate(sess) if s["url"] == session.start_url]
            cur = next((i for i, s in enumerate(sess) if s["path"] == str(session.path)), 0)
            self.after.setCurrentIndex(cur)
            older = [i for i in same if i > cur]
            if older:
                self.before.setCurrentIndex(older[0])

    def run(self):
        a, b = self.before.currentData(), self.after.currentData()
        if not a or not b or a == b:
            self.main.toast("Pick two different crawls.")
            return
        run_worker(self, compare, a, b, on_result=self._show, on_error=self.main.toast)

    def _show(self, r):
        p = theme.palette()
        self.clear_layout(self.kpis)
        hb, ha = r["before"]["health"], r["after"]["health"]
        self.kpis.addWidget(KpiCard(t("Health score"), f"{hb} → {ha}", "", p["ok"] if (ha or 0) >= (hb or 0) else p["critical"]))
        self.kpis.addWidget(KpiCard(t("Fixed"), f"{r['fixed_total']:,}", "findings resolved", p["ok"]))
        self.kpis.addWidget(KpiCard(t("New"), f"{r['new_total']:,}", "new findings", p["critical"]))
        self.kpis.addWidget(KpiCard(t("New URLs"), f"{len(r['added']):,}"))
        self.kpis.addWidget(KpiCard(t("Removed URLs"), f"{len(r['removed']):,}"))
        self.kpis.addWidget(KpiCard("Status changes", f"{len(r['status_changes']):,}"))
        rows = [x for x in r["issues"] if x["before"] or x["after"]]
        self.table.setRowCount(len(rows))
        for i, x in enumerate(rows):
            vals = [x["title"], t(x["severity"].capitalize()), x["before"], x["after"], len(x["fixed"]), len(x["new"])]
            for c, v in enumerate(vals):
                it = QTableWidgetItem()
                it.setData(Qt.DisplayRole, v)
                if c == 4 and v:
                    it.setForeground(QColor(p["ok"]))
                if c == 5 and v:
                    it.setForeground(QColor(p["critical"]))
                self.table.setItem(i, c, it)
        self.table.setSortingEnabled(True)
        self.empty.hide()
        self.table.show()
