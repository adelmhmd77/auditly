"""Settings: appearance, exports, AI, integrations, white-label."""
from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit

from ... import settings as settings_mod
from ...paths import data_dir, open_path, plugin_dirs
from ..i18n import t
from ..widgets import Card, button, label
from .base import View


def _section(title: str, desc: str = "") -> tuple[Card, QFormLayout]:
    c = Card(padding=20, spacing=10)
    c.add(label(title, "H2"))
    if desc:
        c.add(label(desc, "Muted", wrap=True))
    f = QFormLayout()
    f.setVerticalSpacing(10)
    f.setHorizontalSpacing(18)
    c.add(f)
    return c, f


class SettingsView(View):
    def __init__(self, main):
        super().__init__(main, scroll=True)
        self.header(t("Settings"), "")
        s = main.settings

        c, f = _section(t("Appearance"))
        self.theme = QComboBox()
        self.theme.addItem(t("Light"), "light")
        self.theme.addItem(t("Dark"), "dark")
        f.addRow(t("Theme"), self.theme)
        self.lang = QComboBox()
        self.lang.addItem("English", "en")
        self.lang.addItem("العربية (RTL)", "ar")
        f.addRow(t("Language"), self.lang)
        self.body.addWidget(c)

        c, f = _section(t("Exports"), "By default everything is saved in your Downloads folder, under Auditly.")
        row = QHBoxLayout()
        self.export_dir = QLineEdit()
        self.export_dir.setPlaceholderText(str(settings_mod.default_export_root()))
        row.addWidget(self.export_dir, 1)
        row.addWidget(button(t("Choose…"), icon_name="folder", on=self._pick_dir))
        f.addRow(t("Save to"), row)
        self.ask = QCheckBox(t("Ask where to save every time"))
        f.addRow(self.ask)
        self.body.addWidget(c)

        c, f = _section(t("AI (Claude)"), "Used for the AI assistant. Get a key at console.anthropic.com. "
                                          "The key is stored only on this computer.")
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("sk-ant-…  (or set ANTHROPIC_API_KEY)")
        f.addRow(t("Anthropic API key"), self.api_key)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1"])
        f.addRow(t("Model"), self.model)
        self.report_lang = QComboBox()
        self.report_lang.addItem("English", "en")
        self.report_lang.addItem("العربية", "ar")
        f.addRow(t("AI output language"), self.report_lang)
        self.body.addWidget(c)

        c, f = _section(t("Integrations"))
        self.psi_key = QLineEdit()
        self.psi_key.setEchoMode(QLineEdit.Password)
        f.addRow(t("PageSpeed Insights API key (optional)"), self.psi_key)
        self.indexnow = QLineEdit()
        f.addRow(t("IndexNow key"), self.indexnow)
        self.body.addWidget(c)

        c, f = _section(t("White-label reports"), "Your name, colour and logo on HTML/PDF reports for clients.")
        self.brand = QLineEdit()
        self.brand.setPlaceholderText("Your agency")
        f.addRow(t("Brand name"), self.brand)
        crow = QHBoxLayout()
        self.color = QLineEdit()
        self.color.setMaximumWidth(120)
        crow.addWidget(self.color)
        crow.addWidget(button(t("Choose…"), on=self._pick_color))
        crow.addStretch()
        f.addRow(t("Brand colour"), crow)
        lrow = QHBoxLayout()
        self.logo = QLineEdit()
        lrow.addWidget(self.logo, 1)
        lrow.addWidget(button(t("Choose…"), icon_name="folder", on=self._pick_logo))
        f.addRow(t("Logo file"), lrow)
        self.body.addWidget(c)

        c, f = _section("Plugins & data", "Drop .py audit plugins into the plugins folder; they load on the next crawl.")
        prow = QHBoxLayout()
        prow.addWidget(button("Open plugins folder", icon_name="plug", on=lambda: open_path(plugin_dirs()[0])))
        prow.addWidget(button("Open app data folder", icon_name="folder", on=lambda: open_path(data_dir())))
        prow.addStretch()
        f.addRow(prow)
        self.body.addWidget(c)

        act = QHBoxLayout()
        act.addWidget(button(t("Save settings"), "Primary", "save", on=self.save))
        act.addStretch()
        self.body.addLayout(act)
        self.body.addStretch()
        self._fill(s)

    def _fill(self, s):
        self.theme.setCurrentIndex(1 if s.theme == "dark" else 0)
        self.lang.setCurrentIndex(1 if s.language == "ar" else 0)
        self.export_dir.setText(s.export_dir)
        self.ask.setChecked(s.ask_export_folder)
        self.api_key.setText(s.anthropic_api_key)
        self.model.setCurrentText(s.claude_model)
        self.report_lang.setCurrentIndex(1 if s.report_language == "ar" else 0)
        self.psi_key.setText(s.pagespeed_api_key)
        self.indexnow.setText(s.indexnow_key)
        self.brand.setText(s.brand_name)
        self.color.setText(s.brand_color)
        self.logo.setText(s.brand_logo)

    def load(self, session):
        super().load(session)
        self._fill(self.main.settings)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, t("Save to"), self.export_dir.text() or str(settings_mod.default_export_root()))
        if d:
            self.export_dir.setText(d)

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self.color.text() or "#00E676"), self)
        if c.isValid():
            self.color.setText(c.name().upper())

    def _pick_logo(self):
        f, _ = QFileDialog.getOpenFileName(self, t("Logo file"), "", "Images (*.png *.jpg *.jpeg *.svg)")
        if f:
            self.logo.setText(f)

    def save(self):
        s = self.main.settings
        old = (s.theme, s.language)
        s.theme = self.theme.currentData()
        s.language = self.lang.currentData()
        s.export_dir = self.export_dir.text().strip()
        s.ask_export_folder = self.ask.isChecked()
        s.anthropic_api_key = self.api_key.text().strip()
        s.claude_model = self.model.currentText().strip() or "claude-opus-5-5"
        s.report_language = self.report_lang.currentData()
        s.pagespeed_api_key = self.psi_key.text().strip()
        s.indexnow_key = self.indexnow.text().strip()
        s.brand_name = self.brand.text().strip()
        s.brand_color = self.color.text().strip() or "#00E676"
        s.brand_logo = self.logo.text().strip()
        settings_mod.save(s)
        if (s.theme, s.language) != old:
            self.main.rebuild()
        else:
            self.main.toast(t("Saved"))
