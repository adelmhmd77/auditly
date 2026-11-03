"""AI assistant: Claude-powered tasks over the crawl, plus chat with your crawl."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QTextCursor
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QHBoxLayout, QLineEdit, QPushButton, QScrollArea,
                               QTextBrowser, QVBoxLayout, QWidget)

from ...integrations import claude
from .. import theme
from ..i18n import t
from ..icons import icon
from ..widgets import button, empty_state, label, run_worker
from .base import View


class TaskCard(QPushButton):
    """A checkable card with a bold title and a wrapped description."""

    def __init__(self, title: str, desc: str, icon_name: str):
        super().__init__()
        self.setObjectName("TaskCard")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)
        ic = label()
        ic.setPixmap(icon(icon_name, theme.palette()["primary_text"], 18).pixmap(18, 18))
        ic.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(ic, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        for text, name in ((title, "H3"), (desc, "Faint")):
            lb = label(text, name, wrap=True)
            lb.setAttribute(Qt.WA_TransparentForMouseEvents)
            col.addWidget(lb)
        lay.addLayout(col, 1)
        self.setMinimumHeight(lay.sizeHint().height() + 4)


TASK_ICONS = {"summary": "file", "plan": "check", "rewrite": "pages", "linking": "tree", "intent": "search",
              "clusters": "dashboard", "cannibal": "compare", "schema": "columns", "alt": "globe", "quality": "zap"}


class AIView(View):
    def __init__(self, main):
        super().__init__(main)
        self.header(t("AI assistant"), "Powered by Claude · " + "your crawl data stays local until you run a task")
        row = QHBoxLayout()
        row.setSpacing(16)

        left = QScrollArea()
        left.setWidgetResizable(True)
        left.setFixedWidth(320)
        left.setFrameShape(QScrollArea.NoFrame)
        left.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lw = QWidget()
        left.setWidget(lw)
        ll = QVBoxLayout(lw)
        ll.setContentsMargins(0, 0, 6, 0)
        ll.setSpacing(8)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.task_buttons = {}
        chat_btn = TaskCard(t("Chat with your crawl"), "Ask questions about this crawl in plain language.", "ai")
        self.group.addButton(chat_btn)
        self.task_buttons["chat"] = chat_btn
        ll.addWidget(chat_btn)
        for key, meta in claude.TASKS.items():
            b = TaskCard(meta["label"], meta["desc"], TASK_ICONS.get(key, "ai"))
            self.group.addButton(b)
            self.task_buttons[key] = b
            ll.addWidget(b)
        ll.addStretch()
        for key, b in self.task_buttons.items():
            b.clicked.connect(lambda _=False, k=key: self.select(k))
        row.addWidget(left)

        right = QVBoxLayout()
        right.setSpacing(10)
        opts = QHBoxLayout()
        opts.addWidget(label(t("AI output language")))
        self.lang = QComboBox()
        self.lang.addItem("English", "en")
        self.lang.addItem("العربية", "ar")
        opts.addWidget(self.lang)
        opts.addStretch()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(t("Page URL (for content quality)"))
        opts.addWidget(self.url_input, 1)
        self.run_btn = button(t("Run"), "Primary", "play", on=self.run_task)
        opts.addWidget(self.run_btn)
        right.addLayout(opts)
        self.out = QTextBrowser()
        self.out.setOpenExternalLinks(True)
        right.addWidget(self.out, 1)
        self.chat_row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText(t("Ask anything about this crawl…"))
        self.chat_input.returnPressed.connect(self.send_chat)
        self.chat_row.addWidget(self.chat_input, 1)
        self.send_btn = button("", "Primary", "send", on=self.send_chat)
        self.chat_row.addWidget(self.send_btn)
        right.addLayout(self.chat_row)
        acts = QHBoxLayout()
        self.status = label("", "Faint")
        acts.addWidget(self.status, 1)
        acts.addWidget(button(t("Copy"), icon_name="copy", on=self._copy))
        acts.addWidget(button(t("Save to exports"), icon_name="save", on=self._save))
        right.addLayout(acts)
        row.addLayout(right, 1)
        self.body.addLayout(row, 1)
        self.task = None
        self.chat = None
        self.text = ""
        self.chat_log = ""
        self.busy = False
        self.select("chat")

    def load(self, session):
        super().load(session)
        self.chat = None
        self.chat_log = ""
        self.lang.setCurrentIndex(1 if self.main.settings.report_language == "ar" else 0)
        self.select(self.task or "chat")

    def select(self, key: str, url: str = ""):
        self.task = key
        self.task_buttons[key].setChecked(True)
        chat = key == "chat"
        for i in range(self.chat_row.count()):
            self.chat_row.itemAt(i).widget().setVisible(chat)
        self.run_btn.setVisible(not chat)
        self.url_input.setVisible(key == "quality")
        if url:
            self.url_input.setText(url)
        if chat:
            self._render(self.chat_log or self._intro())
        else:
            meta = claude.TASKS[key]
            self._render(f"## {meta['label']}\n\n{meta['desc']}\n\nPress **Run** to generate it from this crawl.")
        if not self.main.settings.api_key:
            self.status.setText(t("Add your Anthropic API key in Settings to use AI features."))

    def _intro(self):
        return ("## Chat with your crawl\n\nAsk questions like:\n\n- *Which pages have the most issues?*\n"
                "- *Which important pages have fewer than 3 internal links?*\n- *List 404s and the pages that link to them.*\n"
                "- *ما الصفحات التي تفتقد وصف الميتا؟*\n\nClaude reads the crawl database to answer (read-only).")

    def _render(self, md: str):
        self.text = md
        self.out.setMarkdown(md)
        self.out.moveCursor(QTextCursor.End)

    def _ready(self) -> bool:
        if not self.session:
            self.main.toast("Open or run a crawl first.")
            return False
        if not self.main.settings.api_key:
            self.main.toast(t("Add your Anthropic API key in Settings to use AI features."))
            self.main.goto("settings")
            return False
        return not self.busy

    def _busy(self, on: bool, msg: str = ""):
        self.busy = on
        self.run_btn.setEnabled(not on)
        self.send_btn.setEnabled(not on)
        self.status.setText(msg)

    # ------------------------------------------------------------------ tasks
    def run_task(self):
        if not self._ready():
            return
        try:
            system, user = claude.build_task(self.task, self.session.db_path, self.lang.currentData(), self.url_input.text().strip())
        except Exception as e:
            self.main.toast(str(e))
            return
        self._render("")
        self.stream_buf = []
        self._busy(True, t("Thinking…"))
        s = self.main.settings
        run_worker(self, claude.stream_text, s.api_key, s.claude_model, system, user, stream=True,
                   effort=claude.TASKS[self.task]["effort"], on_chunk=self._chunk, on_result=self._done, on_error=self._error)

    def _chunk(self, text: str):
        self.stream_buf.append(text)
        if not getattr(self, "_flush_pending", False):
            self._flush_pending = True
            QTimer.singleShot(150, self._flush)

    def _flush(self):
        self._flush_pending = False
        if self.busy:
            self._render("".join(self.stream_buf))
            self.status.setText(f"{t('Thinking…')} {len(''.join(self.stream_buf)):,} chars")

    def _done(self, text):
        self._render(text)
        self._busy(False, f"Done · {datetime.now():%H:%M}")

    def _error(self, msg):
        self._busy(False, "")
        self._render(f"**Error:** {msg}")

    # ------------------------------------------------------------------ chat
    def send_chat(self):
        q = self.chat_input.text().strip()
        if not q or not self._ready():
            return
        s = self.main.settings
        if self.chat is None:
            try:
                self.chat = claude.CrawlChat(s.api_key, s.claude_model, self.session.db_path)
            except Exception as e:
                self.main.toast(str(e))
                return
        self.chat_input.clear()
        self.chat_log += f"\n\n---\n\n**You:** {q}\n\n"
        self._render(self.chat_log + f"_{t('Thinking…')}_")
        self._busy(True, t("Thinking…"))
        self.queries = []

        def on_tool(sql):  # called from the worker thread; just record
            self.queries.append(sql)

        run_worker(self, self.chat.ask, q, on_tool=on_tool, on_result=self._chat_done, on_error=self._chat_error)

    def _chat_done(self, answer):
        n = len(getattr(self, "queries", []))
        self.chat_log += f"**Claude:** {answer}\n\n" + (f"<sub>{n} database queries</sub>" if n else "")
        self._render(self.chat_log)
        self._busy(False, "")

    def _chat_error(self, msg):
        self.chat_log += f"**Error:** {msg}\n\n"
        self._render(self.chat_log)
        self._busy(False, "")

    # ------------------------------------------------------------------ output
    def _copy(self):
        QGuiApplication.clipboard().setText(self.text)
        self.main.toast(t("Copy") + " ✓")

    def _save(self):
        if not self.text.strip():
            return
        name = f"AI_{self.task}_{datetime.now():%Y%m%d-%H%M}.md"
        dest = self.main.export_destination(name)
        if dest:
            with open(dest, "w", encoding="utf-8") as f:
                f.write(self.text)
            self.main.toast(f"{t('Exported')}: {dest}")


__all__ = ["AIView", "empty_state", "theme", "Qt"]
