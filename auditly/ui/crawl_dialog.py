"""Crawl settings dialog."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLineEdit, QMessageBox, QPlainTextEdit, QSpinBox, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ..crawl.config import MODES, USER_AGENTS, CrawlConfig, Extraction
from ..paths import profiles_dir
from .i18n import t
from .widgets import button, label

MODE_LABELS = {"spider": "Spider (whole site)", "list": "List of URLs", "sitemap": "Sitemap only", "single": "Single URL"}


def _form() -> tuple[QWidget, QFormLayout]:
    w = QWidget()
    f = QFormLayout(w)
    f.setContentsMargins(18, 18, 18, 18)
    f.setVerticalSpacing(12)
    f.setHorizontalSpacing(18)
    return w, f


class CrawlDialog(QDialog):
    def __init__(self, cfg: CrawlConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Crawl settings"))
        self.setMinimumSize(720, 560)
        self.cfg = cfg
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.addWidget(label(t("Crawl settings"), "H1"))
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)

        # general
        w, f = _form()
        self.mode = QComboBox()
        for m in MODES:
            self.mode.addItem(t(MODE_LABELS[m]), m)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        f.addRow(t("Crawl mode"), self.mode)
        self.url_list = QPlainTextEdit()
        self.url_list.setPlaceholderText("https://example.com/page-1\nhttps://example.com/page-2")
        self.url_list_label = label(t("URLs (one per line)"))
        f.addRow(self.url_list_label, self.url_list)
        self.sitemap_url = QLineEdit()
        self.sitemap_url.setPlaceholderText("https://example.com/sitemap.xml")
        self.sitemap_label = label(t("Sitemap URL (blank = auto-detect)"))
        f.addRow(self.sitemap_label, self.sitemap_url)
        self.threads = QSpinBox(minimum=1, maximum=100)
        f.addRow(t("Threads"), self.threads)
        self.delay = QDoubleSpinBox(minimum=0, maximum=60, singleStep=0.25, decimals=2)
        f.addRow(t("Delay between requests (s)"), self.delay)
        self.max_urls = QSpinBox(minimum=0, maximum=100_000_000, singleStep=100)
        f.addRow(t("Max URLs (0 = unlimited)"), self.max_urls)
        self.max_depth = QSpinBox(minimum=0, maximum=1000)
        f.addRow(t("Max depth (0 = unlimited)"), self.max_depth)
        self.tabs.addTab(w, t("General"))

        # scope
        w, f = _form()
        self.robots = QCheckBox(t("Respect robots.txt"))
        self.sitemaps = QCheckBox(t("Use XML sitemaps"))
        self.subdomains = QCheckBox(t("Crawl subdomains"))
        self.external = QCheckBox(t("Check external links"))
        self.images = QCheckBox(t("Check images (broken / size)"))
        for cb in (self.robots, self.sitemaps, self.subdomains, self.external, self.images):
            f.addRow(cb)
        self.include = QPlainTextEdit()
        self.include.setMaximumHeight(70)
        self.include.setPlaceholderText("/blog/")
        f.addRow(t("Include only URLs matching (regex, one per line)"), self.include)
        self.exclude = QPlainTextEdit()
        self.exclude.setMaximumHeight(70)
        self.exclude.setPlaceholderText(r"\?sort=" + "\n/tag/")
        f.addRow(t("Exclude URLs matching (regex, one per line)"), self.exclude)
        self.strip = QLineEdit()
        f.addRow(t("Remove URL parameters (comma separated)"), self.strip)
        self.tabs.addTab(w, t("Scope"))

        # rendering & UA
        w, f = _form()
        self.ua = QComboBox()
        self.ua.setEditable(True)
        self.ua.addItems(list(USER_AGENTS))
        f.addRow(t("User-agent"), self.ua)
        self.render = QCheckBox(t("Render JavaScript (Playwright)"))
        f.addRow(self.render)
        f.addRow(label("pip install playwright && playwright install chromium", "Faint"))
        self.mobile = QCheckBox(t("Compare mobile vs desktop content"))
        f.addRow(self.mobile)
        self.tabs.addTab(w, t("Rendering & user-agent").replace("&", "&&"))

        # auth
        w, f = _form()
        self.user = QLineEdit()
        f.addRow(t("Username"), self.user)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        f.addRow(t("Password"), self.password)
        self.cookies = QLineEdit()
        self.cookies.setPlaceholderText("session=abc123; consent=yes")
        f.addRow(t("Cookies"), self.cookies)
        self.headers = QPlainTextEdit()
        self.headers.setPlaceholderText("Authorization: Bearer …\nX-Preview: 1")
        f.addRow(t("Extra headers (Name: value per line)"), self.headers)
        self.tabs.addTab(w, t("Authentication"))

        # extraction
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 18, 18, 18)
        v.addWidget(label("CSS selector, XPath or Regex. Results appear as extra columns in the Pages table.", "Muted", True))
        self.ex_table = QTableWidget(0, 4)
        self.ex_table.setHorizontalHeaderLabels([t("Name"), t("Type"), t("Expression"), t("Attribute")])
        self.ex_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.ex_table.verticalHeader().hide()
        v.addWidget(self.ex_table, 1)
        row = QHBoxLayout()
        row.addWidget(button(t("Add rule"), icon_name="check", on=lambda: self._add_ex(Extraction("price", "css", ".price"))))
        row.addWidget(button(t("Remove"), icon_name="trash", on=self._remove_ex))
        row.addStretch()
        v.addLayout(row)
        self.tabs.addTab(w, t("Custom extraction"))

        # advanced
        w, f = _form()
        self.timeout = QSpinBox(minimum=3, maximum=300)
        f.addRow(t("Timeout (s)"), self.timeout)
        self.retries = QSpinBox(minimum=0, maximum=10)
        f.addRow(t("Retries"), self.retries)
        self.verify = QCheckBox(t("Verify TLS certificates"))
        f.addRow(self.verify)
        self.tabs.addTab(w, t("Advanced"))

        btns = QHBoxLayout()
        btns.addWidget(button(t("Load profile…"), icon_name="folder", on=self._load_profile))
        btns.addWidget(button(t("Save profile…"), icon_name="save", on=self._save_profile))
        btns.addStretch()
        btns.addWidget(button(t("Cancel"), on=self.reject))
        btns.addWidget(button(t("Apply"), "Primary", on=self._accept))
        lay.addLayout(btns)
        self._fill(cfg)

    # ------------------------------------------------------------------
    def _add_ex(self, ex: Extraction):
        r = self.ex_table.rowCount()
        self.ex_table.insertRow(r)
        self.ex_table.setItem(r, 0, QTableWidgetItem(ex.name))
        kind = QComboBox()
        kind.addItems(["css", "xpath", "regex"])
        kind.setCurrentText(ex.kind)
        self.ex_table.setCellWidget(r, 1, kind)
        self.ex_table.setItem(r, 2, QTableWidgetItem(ex.expr))
        self.ex_table.setItem(r, 3, QTableWidgetItem(ex.attr))

    def _remove_ex(self):
        r = self.ex_table.currentRow()
        if r >= 0:
            self.ex_table.removeRow(r)

    def _mode_changed(self):
        m = self.mode.currentData()
        for wdg in (self.url_list, self.url_list_label):
            wdg.setVisible(m == "list")
        for wdg in (self.sitemap_url, self.sitemap_label):
            wdg.setVisible(m in ("sitemap", "spider"))

    def _fill(self, c: CrawlConfig):
        self.mode.setCurrentIndex(max(0, list(MODES).index(c.mode) if c.mode in MODES else 0))
        self.url_list.setPlainText("\n".join(c.url_list))
        self.sitemap_url.setText(c.sitemap_url)
        self.threads.setValue(c.threads)
        self.delay.setValue(c.delay)
        self.max_urls.setValue(c.max_urls)
        self.max_depth.setValue(c.max_depth)
        self.robots.setChecked(c.respect_robots)
        self.sitemaps.setChecked(c.use_sitemaps)
        self.subdomains.setChecked(c.subdomains)
        self.external.setChecked(c.check_external)
        self.images.setChecked(c.check_images)
        self.include.setPlainText("\n".join(c.include))
        self.exclude.setPlainText("\n".join(c.exclude))
        self.strip.setText(", ".join(c.strip_params))
        self.ua.setCurrentText(c.user_agent)
        self.render.setChecked(c.render_js)
        self.mobile.setChecked(c.mobile_parity)
        self.user.setText(c.auth_user)
        self.password.setText(c.auth_pass)
        self.cookies.setText(c.cookies)
        self.headers.setPlainText("\n".join(f"{k}: {v}" for k, v in (c.headers or {}).items()))
        self.ex_table.setRowCount(0)
        for ex in c.extractions:
            self._add_ex(ex)
        self.timeout.setValue(c.timeout)
        self.retries.setValue(c.retries)
        self.verify.setChecked(c.verify_tls)
        self._mode_changed()

    def collect(self) -> CrawlConfig:
        import re
        c = CrawlConfig(url=self.cfg.url)
        c.mode = self.mode.currentData()
        c.url_list = [u.strip() for u in self.url_list.toPlainText().splitlines() if u.strip()]
        c.sitemap_url = self.sitemap_url.text().strip()
        c.threads, c.delay = self.threads.value(), self.delay.value()
        c.max_urls, c.max_depth = self.max_urls.value(), self.max_depth.value()
        c.respect_robots, c.use_sitemaps = self.robots.isChecked(), self.sitemaps.isChecked()
        c.subdomains, c.check_external, c.check_images = self.subdomains.isChecked(), self.external.isChecked(), self.images.isChecked()
        c.include = [x.strip() for x in self.include.toPlainText().splitlines() if x.strip()]
        c.exclude = [x.strip() for x in self.exclude.toPlainText().splitlines() if x.strip()]
        for pat in c.include + c.exclude:
            re.compile(pat)
        c.strip_params = [x.strip() for x in self.strip.text().split(",") if x.strip()]
        c.user_agent = self.ua.currentText().strip() or "Auditly"
        c.render_js, c.mobile_parity = self.render.isChecked(), self.mobile.isChecked()
        c.auth_user, c.auth_pass, c.cookies = self.user.text().strip(), self.password.text(), self.cookies.text().strip()
        hdrs = {}
        for line in self.headers.toPlainText().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                hdrs[k.strip()] = v.strip()
        c.headers = hdrs
        exs = []
        for r in range(self.ex_table.rowCount()):
            name = (self.ex_table.item(r, 0).text() if self.ex_table.item(r, 0) else "").strip()
            expr = (self.ex_table.item(r, 2).text() if self.ex_table.item(r, 2) else "").strip()
            if name and expr:
                exs.append(Extraction(name, self.ex_table.cellWidget(r, 1).currentText(), expr,
                                      (self.ex_table.item(r, 3).text() if self.ex_table.item(r, 3) else "").strip()))
        c.extractions = exs
        c.timeout, c.retries, c.verify_tls = self.timeout.value(), self.retries.value(), self.verify.isChecked()
        return c

    def _accept(self):
        try:
            self.cfg = self.collect()
        except Exception as e:
            QMessageBox.warning(self, "Auditly", f"Invalid setting: {e}")
            return
        self.accept()

    def _save_profile(self):
        path, _ = QFileDialog.getSaveFileName(self, t("Save profile…"), str(profiles_dir() / "profile.yaml"), "YAML (*.yaml *.yml)")
        if path:
            try:
                self.collect().save_yaml(path)
            except Exception as e:
                QMessageBox.warning(self, "Auditly", str(e))

    def _load_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, t("Load profile…"), str(profiles_dir()), "YAML (*.yaml *.yml)")
        if path:
            try:
                c = CrawlConfig.load_yaml(path)
                c.url = c.url or self.cfg.url
                self.cfg.url = c.url
                self._fill(c)
            except Exception as e:
                QMessageBox.warning(self, "Auditly", str(e))
