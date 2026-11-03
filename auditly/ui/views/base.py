from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ..widgets import label


class View(QWidget):
    """A page in the main window. Subclasses implement load(session)."""

    title = ""
    subtitle = ""

    def __init__(self, main, scroll: bool = False):
        super().__init__()
        self.main = main
        self.session = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        if scroll:
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QScrollArea.NoFrame)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            inner = QWidget()
            inner.setObjectName("Content")
            area.setWidget(inner)
            outer.addWidget(area)
            host = inner
        else:
            host = self
        self.body = QVBoxLayout(host) if scroll else QVBoxLayout()
        if not scroll:
            outer.addLayout(self.body)
        self.body.setContentsMargins(28, 22, 28, 22)
        self.body.setSpacing(16)

    def header(self, title: str, subtitle: str = "", right: list | None = None):
        row = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        self.h_title = label(title, "H1")
        col.addWidget(self.h_title)
        self.h_sub = label(subtitle, "Muted", wrap=True)
        col.addWidget(self.h_sub)
        if not subtitle:
            self.h_sub.hide()
        row.addLayout(col, 1)
        for w in right or []:
            row.addWidget(w, 0, Qt.AlignBottom)
        self.body.addLayout(row)
        return row

    def load(self, session) -> None:
        self.session = session

    def clear_layout(self, lay):
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                self.clear_layout(item.layout())
