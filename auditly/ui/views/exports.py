"""Exports: pick formats and destination (Downloads/Auditly by default, or any folder)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout

from ... import settings as settings_mod
from ...export import FORMATS, export_bundle
from ...paths import open_path
from .. import theme
from ..i18n import t
from ..icons import icon
from ..widgets import Card, button, label, run_worker
from .base import View

FORMAT_ICONS = {"master_csv": "file", "csv": "file", "xlsx": "columns", "json": "file", "html": "globe", "pdf": "file",
                "prompt": "ai"}
FORMAT_DESC = {
    "master_csv": "One row per URL with every metric and its issues — perfect for spreadsheets and AI tools.",
    "csv": "Separate files for pages, links, issues, images, hreflang, sitemap and PageSpeed.",
    "xlsx": "Formatted workbook: summary, issue overview with fixes, all issues, pages and links.",
    "json": "Machine-readable export for scripts and dashboards.",
    "html": "Client-ready report with your branding (white-label in Settings).",
    "pdf": "Printable version of the report.",
    "prompt": "A ready-to-paste prompt + all findings, for Claude or any AI assistant.",
}
DEFAULT_ON = {"master_csv", "xlsx", "html", "prompt"}


class ExportView(View):
    def __init__(self, main):
        super().__init__(main, scroll=True)
        self.header(t("Exports"), "")
        self.body.addWidget(label(t("Choose what to export"), "H2"))
        grid = QGridLayout()
        grid.setSpacing(12)
        self.checks: dict[str, QCheckBox] = {}
        p = theme.palette()
        for i, (key, name) in enumerate(FORMATS.items()):
            c = Card(padding=14, spacing=6, clickable=True)
            top = QHBoxLayout()
            il = label()
            il.setPixmap(icon(FORMAT_ICONS[key], p["primary_text"], 18).pixmap(18, 18))
            top.addWidget(il)
            cb = QCheckBox(name)
            cb.setChecked(key in DEFAULT_ON)
            cb.setStyleSheet("font-weight:600;")
            top.addWidget(cb, 1)
            c.add(top)
            c.add(label(FORMAT_DESC[key], "Muted", wrap=True))
            c.clicked.connect(lambda cb=cb: cb.toggle())
            self.checks[key] = cb
            grid.addWidget(c, i // 2, i % 2)
        self.body.addLayout(grid)

        dest = Card(padding=18, spacing=10)
        dest.add(label(t("Save to"), "H2"))
        dest.add(label(t("Exports are saved here by default. You can change the folder at any time."), "Muted", wrap=True))
        r = QHBoxLayout()
        fi = label()
        fi.setPixmap(icon("folder", p["muted"], 18).pixmap(18, 18))
        r.addWidget(fi)
        self.folder = label("", "H3")
        r.addWidget(self.folder, 1)
        r.addWidget(button(t("Change folder…"), icon_name="folder", on=self.change_folder))
        r.addWidget(button(t("Open folder"), icon_name="external", on=lambda: self._open(self.main.settings.export_root)))
        dest.add(r)
        self.ask = QCheckBox(t("Ask where to save every time"))
        self.ask.toggled.connect(self._ask_toggled)
        dest.add(self.ask)
        lr = QHBoxLayout()
        lr.addWidget(label(t("AI prompt language")))
        self.lang = QComboBox()
        self.lang.addItem("English", "en")
        self.lang.addItem("العربية", "ar")
        lr.addWidget(self.lang)
        lr.addStretch()
        dest.add(lr)
        self.body.addWidget(dest)

        act = QHBoxLayout()
        self.export_btn = button(t("Export now"), "Primary", "export", on=self.export)
        act.addWidget(self.export_btn)
        self.result = label("", "Muted", wrap=True)
        act.addWidget(self.result, 1)
        self.open_result = button(t("Open folder"), icon_name="folder")
        self.open_result.hide()
        act.addWidget(self.open_result)
        self.body.addLayout(act)
        self.body.addStretch()

    def load(self, session):
        super().load(session)
        s = self.main.settings
        self.folder.setText(str(s.export_root))
        self.ask.setChecked(s.ask_export_folder)
        self.lang.setCurrentIndex(1 if s.report_language == "ar" else 0)
        self.export_btn.setEnabled(bool(session))
        self.h_sub.setText(session.start_url if session else "Run or open a crawl to export it.")
        self.h_sub.show()

    def change_folder(self):
        d = QFileDialog.getExistingDirectory(self, t("Change folder…"), str(self.main.settings.export_root))
        if d:
            self.main.settings.export_dir = d
            settings_mod.save(self.main.settings)
            self.folder.setText(d)

    def _ask_toggled(self, on):
        self.main.settings.ask_export_folder = on
        settings_mod.save(self.main.settings)

    def _open(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)
        open_path(path)

    def export(self):
        if not self.session:
            return
        formats = {k for k, cb in self.checks.items() if cb.isChecked()}
        if not formats:
            self.main.toast("Choose at least one format.")
            return
        s = self.main.settings
        folder = None
        if s.ask_export_folder:
            d = QFileDialog.getExistingDirectory(self, t("Save to"), str(s.export_root))
            if not d:
                return
            from ...export import export_dir_for
            folder = export_dir_for(Path(d), self.session.start_url)
        self.export_btn.setEnabled(False)
        self.result.setText("Exporting…")
        run_worker(self, export_bundle, self.session.path, formats, s.export_root, s.brand_name, s.brand_color,
                   s.brand_logo, self.lang.currentData(), folder, on_result=self._done, on_error=self._err)

    def _done(self, res):
        dest, files = res
        self.export_btn.setEnabled(True)
        self.result.setText(f"{t('Exported')} {len(files)} files → {dest}")
        try:
            self.open_result.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.open_result.clicked.connect(lambda: open_path(dest))
        self.open_result.show()
        self.main.toast(f"{t('Exported')} {len(files)} files")

    def _err(self, msg):
        self.export_btn.setEnabled(True)
        self.result.setText(f"Export failed: {msg}")
