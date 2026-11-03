"""Auditly desktop app: main window."""
from __future__ import annotations

import asyncio
import sys
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import QSize, Qt, QThread, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLineEdit, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from .. import settings as settings_mod
from ..audits import run_audits
from ..crawl import db as dbm
from ..crawl.config import MODES, CrawlConfig
from ..crawl.crawler import Crawler
from ..crawl.urls import strip_www
from ..paths import data_dir
from ..sessions import new_session_dir
from . import i18n, theme
from .crawl_dialog import MODE_LABELS, CrawlDialog
from .data import SessionData
from .i18n import t
from .icons import app_icon, icon, logo_pixmap
from .views.ai import AIView
from .views.compare import CompareView
from .views.dashboard import DashboardView
from .views.exports import ExportView
from .views.history import HistoryView
from .views.integrations import IntegrationsView
from .views.issues import IssuesView
from .views.pages_view import PagesView
from .views.settings_view import SettingsView
from .views.structure import StructureView
from .widgets import Bridge, Toast, button, label

NAV = [
    ("Workspace", [("dashboard", "Dashboard", "dashboard"), ("pages", "Pages", "pages"), ("issues", "Issues", "issues"),
                   ("structure", "Site structure", "tree")]),
    ("Analyse", [("ai", "AI assistant", "ai"), ("compare", "Compare crawls", "compare")]),
    ("Tools", [("exports", "Exports", "export"), ("integrations", "Integrations", "plug"), ("history", "History", "history")]),
]


class CrawlThread(QThread):
    def __init__(self, crawler: Crawler, bridge: Bridge):
        super().__init__()
        self.crawler, self.bridge = crawler, bridge

    def run(self):
        c = self.crawler
        try:
            asyncio.run(c.run())
        except Exception as e:
            self.bridge.failed.emit(f"{type(e).__name__}: {e}")
            return
        try:
            self.bridge.message.emit(t("Running audits…"))
            run_audits(c.db_path, progress=self.bridge.audit_step.emit)
        except Exception as e:
            self.bridge.failed.emit(f"Audits failed: {type(e).__name__}: {e}")
            return
        self.bridge.finished.emit(c.user_stopped)


class MainWindow(QMainWindow):
    def __init__(self, settings: settings_mod.Settings, session_path: str | None = None):
        super().__init__()
        self.settings = settings
        self.session: SessionData | None = None
        self.crawler: Crawler | None = None
        self.thread: CrawlThread | None = None
        self.live = deque()
        self.bridge = Bridge()
        self.bridge.progress.connect(self._on_progress)
        self.bridge.message.connect(self._on_message)
        self.bridge.finished.connect(self._on_finished)
        self.bridge.failed.connect(self._on_failed)
        self.bridge.audit_step.connect(lambda s: self.status.setText(f"{t('Running audits…')} {s}"))
        self.cfg = CrawlConfig.from_dict(settings.last_profile) if settings.last_profile else CrawlConfig()
        self.cfg.auth_pass = ""
        self._closing_ok = False

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)
        rtl = i18n.is_rtl()

        root = QWidget()
        root.setObjectName("Content")
        rl = QHBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        self.setCentralWidget(root)

        # ---------------- sidebar
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setProperty("rtl", rtl)
        side.setFixedWidth(232)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 18, 14, 14)
        sl.setSpacing(2)
        brand = QHBoxLayout()
        lg = label()
        lg.setPixmap(logo_pixmap(34))
        brand.addWidget(lg)
        bcol = QVBoxLayout()
        bcol.setSpacing(0)
        bcol.addWidget(label(APP_NAME, "Brand"))
        bcol.addWidget(label(t("Technical SEO auditor"), "BrandSub"))
        brand.addLayout(bcol)
        brand.addStretch()
        sl.addLayout(brand)
        sl.addSpacing(12)
        p = theme.palette()
        self.nav: dict[str, QPushButton] = {}
        for section, items in NAV:
            sl.addWidget(label(t(section).upper() if not rtl else t(section), "NavSection"))
            for key, text, ic in items:
                b = QPushButton(f"  {t(text)}")
                b.setObjectName("Nav")
                b.setProperty("rtl", rtl)
                b.setCheckable(True)
                b.setAutoExclusive(True)
                b.setIcon(icon(ic, p["muted"], 18, active=p["primary_text"]))
                b.setIconSize(QSize(18, 18))
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, k=key: self.goto(k))
                sl.addWidget(b)
                self.nav[key] = b
        sl.addStretch()
        sb = QPushButton(f"  {t('Settings')}")
        sb.setObjectName("Nav")
        sb.setProperty("rtl", rtl)
        sb.setCheckable(True)
        sb.setAutoExclusive(True)
        sb.setIcon(icon("settings", p["muted"], 18, active=p["primary_text"]))
        sb.setIconSize(QSize(18, 18))
        sb.clicked.connect(lambda: self.goto("settings"))
        sl.addWidget(sb)
        self.nav["settings"] = sb
        tog = QHBoxLayout()
        dark = self.settings.theme == "dark"
        self.theme_btn = button(t("Light") if dark else t("Dark"), "Ghost", "sun" if dark else "moon", on=self.toggle_theme)
        tog.addWidget(self.theme_btn)
        self.lang_btn = button("English" if rtl else "العربية", "Ghost", "language", on=self.toggle_language)
        tog.addWidget(self.lang_btn)
        sl.addLayout(tog)
        sl.addWidget(label(f"v{__version__}", "Faint"))
        rl.addWidget(side)

        # ---------------- main column
        main = QWidget()
        main.setObjectName("Content")
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        top = QFrame()
        top.setObjectName("TopBar")
        tl = QVBoxLayout(top)
        tl.setContentsMargins(24, 14, 24, 10)
        tl.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.url = QLineEdit()
        self.url.setObjectName("UrlInput")
        self.url.setPlaceholderText(t("Enter a website URL, e.g. https://example.com"))
        self.url.addAction(icon("globe", p["faint"], 18), QLineEdit.LeadingPosition)
        self.url.returnPressed.connect(self.start)
        self.url.setText(self.cfg.url)
        row.addWidget(self.url, 1)
        self.mode = QComboBox()
        for m in MODES:
            self.mode.addItem(t(MODE_LABELS[m]), m)
        self.mode.setCurrentIndex(list(MODES).index(self.cfg.mode) if self.cfg.mode in MODES else 0)
        self.mode.setMinimumWidth(170)
        row.addWidget(self.mode)
        row.addWidget(button("", icon_name="sliders", on=self.open_crawl_settings, tip=t("Crawl settings")))
        self.start_btn = button(t("Start audit"), "Primary", "play", on=self.start)
        row.addWidget(self.start_btn)
        self.pause_btn = button(t("Pause"), icon_name="pause", on=self.toggle_pause)
        self.pause_btn.hide()
        row.addWidget(self.pause_btn)
        self.stop_btn = button(t("Stop"), "Danger", "stop", on=self.stop)
        self.stop_btn.hide()
        row.addWidget(self.stop_btn)
        tl.addLayout(row)
        srow = QHBoxLayout()
        self.status = label(t("Ready. Enter a URL and press Start audit."), "StatusText")
        srow.addWidget(self.status, 1)
        self.stats = label("", "StatusText")
        srow.addWidget(self.stats)
        tl.addLayout(srow)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFixedHeight(3)
        tl.addWidget(self.progress)
        ml.addWidget(top)

        self.stack = QStackedWidget()
        self.views = {
            "dashboard": DashboardView(self), "pages": PagesView(self), "issues": IssuesView(self),
            "structure": StructureView(self), "ai": AIView(self), "compare": CompareView(self),
            "exports": ExportView(self), "integrations": IntegrationsView(self), "history": HistoryView(self),
            "settings": SettingsView(self),
        }
        for v in self.views.values():
            self.stack.addWidget(v)
        ml.addWidget(self.stack, 1)
        rl.addWidget(main, 1)

        self.toaster = Toast(self)
        self.live_timer = QTimer(self, interval=400, timeout=self._drain_live)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.focus_url)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=lambda: self.goto("exports"))

        if session_path:
            self.open_session(session_path, switch=False)
        else:
            self.set_session(None)
        self.goto("dashboard")

    # ------------------------------------------------------------------ navigation
    def goto(self, key: str, **kw):
        v = self.views[key]
        if key in self.nav:
            self.nav[key].setChecked(True)
        self.stack.setCurrentWidget(v)
        if key in ("history", "compare", "settings", "exports"):
            v.load(self.session)
        if key == "issues" and kw:
            v.focus(kw.get("issue"), kw.get("severity"), kw.get("category"))
        if key == "pages" and kw.get("status"):
            v.set_filter(kw["status"])
        if key == "ai" and kw.get("task"):
            v.select(kw["task"], kw.get("url", ""))

    def focus_url(self):
        self.url.setFocus()
        self.url.selectAll()

    def toast(self, msg: str):
        self.toaster.show_message(str(msg))

    # ------------------------------------------------------------------ sessions
    def set_session(self, session: SessionData | None):
        self.session = session
        for k, v in self.views.items():
            v.load(session)
        n = sum(1 for i in session.issues) if session else 0
        self.nav["issues"].setText(f"  {t('Issues')}" + (f"   {n}" if n else ""))
        if session:
            self.setWindowTitle(f"{APP_NAME} — {session.start_url}")

    def open_session(self, path, switch: bool = True):
        try:
            self.set_session(SessionData(path))
            cfg = self.session.json_meta("config") or {}
            self.url.setText(self.session.start_url)
            if cfg.get("mode") in MODES:
                self.mode.setCurrentIndex(list(MODES).index(cfg["mode"]))
            h = self.session.summary["health"]
            self.status.setText(f"{self.session.start_url} · {self.session.summary['total']:,} pages · "
                                f"{t('Health score')} {h}/100")
            if switch:
                self.goto("dashboard")
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, f"Couldn't open this crawl:\n{e}")

    def reload_session(self):
        if self.session:
            self.set_session(SessionData(self.session.path))

    # ------------------------------------------------------------------ crawl settings
    def open_crawl_settings(self):
        self.cfg.url = self.url.text().strip() or self.cfg.url
        self.cfg.mode = self.mode.currentData()
        dlg = CrawlDialog(self.cfg, self)
        if dlg.exec():
            pw = dlg.cfg.auth_pass
            self.cfg = dlg.cfg
            self.cfg.auth_pass = pw
            self.mode.setCurrentIndex(list(MODES).index(self.cfg.mode))
            self._save_profile()

    def _save_profile(self):
        self.settings.last_profile = self.cfg.to_dict()
        settings_mod.save(self.settings)

    # ------------------------------------------------------------------ crawl control
    def running(self) -> bool:
        return bool(self.thread and self.thread.isRunning())

    def start(self):
        if self.running():
            return
        url = self.url.text().strip()
        mode = self.mode.currentData()
        if mode == "list" and not self.cfg.url_list:
            self.toast("Add your URL list in Crawl settings first.")
            self.open_crawl_settings()
            if not self.cfg.url_list:
                return
        if not url and mode == "list" and self.cfg.url_list:
            url = self.cfg.url_list[0]
        if not url:
            self.toast(t("Enter a website URL, e.g. https://example.com"))
            self.focus_url()
            return
        full = url if "://" in url else "https://" + url
        if not urlsplit(full).hostname or "." not in (urlsplit(full).hostname or "") and urlsplit(full).hostname != "localhost":
            self.toast(f"'{url}' doesn't look like a valid URL.")
            return
        self.cfg.url, self.cfg.mode = full, mode
        if self.cfg.render_js:
            try:
                import playwright  # noqa: F401
            except ImportError:
                QMessageBox.information(self, APP_NAME, "JavaScript rendering needs Playwright:\n\n"
                                        "pip install playwright\nplaywright install chromium\n\nCrawling without it.")
                self.cfg.render_js = False
        self._save_profile()
        try:
            crawler = Crawler(self.cfg, new_session_dir(full))
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        self._launch(crawler)

    def resume_session(self, path):
        if self.running():
            self.toast("A crawl is already running.")
            return
        db = dbm.connect(Path(path) / "crawl.db", readonly=True)
        cfg = CrawlConfig.from_dict(dbm.get_meta(db, "config", {}, as_json=True))
        db.close()
        self.url.setText(cfg.url)
        self._launch(Crawler(cfg, path, resume=True))

    def _launch(self, crawler: Crawler):
        self.crawler = crawler
        crawler.on_page = self.live.append
        crawler.on_progress = self.bridge.progress.emit
        crawler.on_message = self.bridge.message.emit
        self.set_session(None)
        self.views["pages"].live_reset()
        self.live.clear()
        self.started_at = time.time()
        self.start_btn.hide()
        self.pause_btn.setText(t("Pause"))
        self.pause_btn.setIcon(icon("pause", theme.palette()["muted"], 16))
        self.pause_btn.show()
        self.stop_btn.show()
        self.stop_btn.setEnabled(True)
        self.url.setEnabled(False)
        self.mode.setEnabled(False)
        self.progress.setRange(0, 0)
        self.status.setText(f"{t('Crawled')} {crawler.start} …")
        self.goto("pages")
        self.thread = CrawlThread(crawler, self.bridge)
        self.thread.start()
        self.live_timer.start()

    def toggle_pause(self):
        if not self.crawler:
            return
        if self.crawler.paused:
            self.crawler.unpause()
            self.pause_btn.setText(t("Pause"))
            self.pause_btn.setIcon(icon("pause", theme.palette()["muted"], 16))
            self.progress.setRange(0, 0)
        else:
            self.crawler.pause()
            self.pause_btn.setText(t("Resume"))
            self.pause_btn.setIcon(icon("play", theme.palette()["muted"], 16))
            self.progress.setRange(0, 1)
            self.status.setText(t("Paused"))

    def stop(self):
        if self.crawler:
            self.crawler.request_stop()
            self.stop_btn.setEnabled(False)
            self.pause_btn.hide()
            self.status.setText(t("Stopping…"))

    def _drain_live(self):
        rows = []
        while self.live and len(rows) < 2000:
            rows.append(self.live.popleft())
        if rows:
            self.views["pages"].live_append(rows)

    def _on_progress(self, s: dict):
        el = int(s["elapsed"])
        self.stats.setText(f"{t('Crawled')} <b>{s['crawled']:,}</b>  ·  {t('Queued')} <b>{s['queued']:,}</b>  ·  "
                           f"{s['rate']:.1f} {t('pages/s')}  ·  {el // 60}:{el % 60:02d}"
                           + (f"  ·  {t('Errors')} {s['errors']}" if s["errors"] else ""))
        if not s["paused"] and self.crawler and not self.crawler.stop:
            self.status.setText(f"{t('Crawled')} {self.crawler.start}")

    def _on_message(self, m: str):
        self.status.setText(m)

    def _reset_controls(self):
        self.live_timer.stop()
        self._drain_live()
        self.start_btn.show()
        self.pause_btn.hide()
        self.stop_btn.hide()
        self.url.setEnabled(True)
        self.mode.setEnabled(True)
        self.progress.setRange(0, 1)
        self.progress.setValue(1)

    def _on_finished(self, stopped: bool):
        self._reset_controls()
        path = self.crawler.session_dir
        self.open_session(path, switch=False)
        h = self.session.summary["health"] if self.session else 0
        self.status.setText(f"{t('Audit complete')} · {self.session.summary['total']:,} pages · {t('Health score')} {h}/100"
                            + (" · stopped early (resume from History)" if stopped else
                               " · page limit reached" if self.crawler.limit_reached else ""))
        self.goto("dashboard")
        self.toast(f"{t('Audit complete')} · {t('Health score')} {h}/100")

    def _on_failed(self, msg: str):
        self._reset_controls()
        self.status.setText("Crawl failed.")
        QMessageBox.critical(self, APP_NAME, f"The crawl stopped with an error:\n\n{msg}")

    # ------------------------------------------------------------------ exports helper
    def export_destination(self, filename: str) -> str | None:
        host = strip_www(urlsplit(self.session.start_url).hostname or "site") if self.session else "auditly"
        root = self.settings.export_root / host
        if self.settings.ask_export_folder:
            path, _ = QFileDialog.getSaveFileName(self, t("Save to"), str(root / filename))
            return path or None
        root.mkdir(parents=True, exist_ok=True)
        return str(root / filename)

    # ------------------------------------------------------------------ theme / language
    def toggle_theme(self):
        self.settings.theme = "light" if self.settings.theme == "dark" else "dark"
        settings_mod.save(self.settings)
        self.rebuild()

    def toggle_language(self):
        self.settings.language = "en" if self.settings.language == "ar" else "ar"
        settings_mod.save(self.settings)
        self.rebuild()

    def rebuild(self):
        if self.running():
            self.toast("Finish or stop the crawl first.")
            return
        apply_look(QApplication.instance(), self.settings)
        w = MainWindow(self.settings, str(self.session.path) if self.session else None)
        w.setGeometry(self.geometry())
        if self.isMaximized():
            w.showMaximized()
        else:
            w.show()
        _windows.append(w)
        self._closing_ok = True
        self.close()
        if self in _windows:
            _windows.remove(self)

    def closeEvent(self, e):
        if self.running() and not self._closing_ok:
            if QMessageBox.question(self, APP_NAME, "A crawl is still running. Stop it and quit?\n"
                                    "(You can resume it later from History.)") != QMessageBox.Yes:
                e.ignore()
                return
            self.crawler.request_stop()
            self.thread.wait(8000)
        e.accept()


_windows: list[MainWindow] = []


def _pick_font() -> QFont:
    fams = set(QFontDatabase.families())
    for f in ("Inter", "Segoe UI Variable Text", "Segoe UI", "SF Pro Text", ".AppleSystemUIFont", "Helvetica Neue",
              "Cantarell", "Noto Sans", "Ubuntu", "DejaVu Sans"):
        if f in fams:
            font = QFont(f)
            font.setPointSizeF(10 if sys.platform.startswith("win") else 10.5)
            return font
    return QApplication.font()


def apply_look(app: QApplication, s: settings_mod.Settings) -> None:
    theme.set_theme(s.theme)
    i18n.set_language(s.language)
    app.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)
    check = data_dir() / "ui" / f"check_{s.theme}.svg"
    check.parent.mkdir(parents=True, exist_ok=True)
    check.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="'
                     f'{theme.palette()["on_primary"]}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">'
                     '<path d="M20 6L9 17l-5-5"/></svg>', encoding="utf-8")
    p = theme.palette()
    pal = QPalette()
    for role, key in ((QPalette.Window, "bg"), (QPalette.Base, "surface"), (QPalette.AlternateBase, "surface2"),
                      (QPalette.Button, "surface"), (QPalette.Text, "text"), (QPalette.WindowText, "text"),
                      (QPalette.ButtonText, "text"), (QPalette.ToolTipBase, "surface"), (QPalette.ToolTipText, "text"),
                      (QPalette.Highlight, "selection"), (QPalette.HighlightedText, "selection_text"),
                      (QPalette.PlaceholderText, "faint"), (QPalette.Link, "accent"), (QPalette.Mid, "border"),
                      (QPalette.Light, "surface"), (QPalette.Midlight, "surface2"), (QPalette.Dark, "border"),
                      (QPalette.Shadow, "border")):
        pal.setColor(role, QColor(p[key]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(p["faint"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(p["faint"]))
    app.setPalette(pal)
    app.setStyleSheet(theme.stylesheet().replace(":/check.svg", check.as_posix()))


def run() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setDesktopFileName("auditly")
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")
    app.setFont(_pick_font())
    s = settings_mod.load()
    apply_look(app, s)
    w = MainWindow(s)
    _windows.append(w)
    w.show()
    return app.exec()
