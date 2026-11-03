"""Shared widgets: cards, charts, pills, toasts and background workers."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import theme
from .i18n import t
from .icons import icon


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def button(text: str, name: str | None = None, icon_name: str | None = None, on=None, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    if name:
        b.setObjectName(name)
    if icon_name:
        p = theme.palette()
        col = p["on_primary"] if name == "Primary" else p["muted"]
        b.setIcon(icon(icon_name, col, 16))
        b.setIconSize(QSize(16, 16))
    if on:
        b.clicked.connect(on)
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    return b


class Card(QFrame):
    clicked = Signal()

    def __init__(self, parent=None, name: str = "Card", padding: int = 18, spacing: int = 10, clickable: bool = False):
        super().__init__(parent)
        self.setObjectName(name)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(padding, padding, padding, padding)
        self.lay.setSpacing(spacing)
        self._clickable = clickable
        if clickable:
            self.setProperty("clickable", True)
            self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if self._clickable and e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def add(self, w, stretch: int = 0):
        if isinstance(w, QWidget):
            self.lay.addWidget(w, stretch)
        else:
            self.lay.addLayout(w, stretch)
        return w


def soft_shadow(w: QWidget, blur: int = 24, y: int = 4) -> None:
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(blur)
    eff.setOffset(0, y)
    eff.setColor(QColor(theme.palette()["shadow"]))
    w.setGraphicsEffect(eff)


class KpiCard(Card):
    def __init__(self, title: str, value: str = "—", caption: str = "", color: str | None = None, icon_name: str | None = None):
        super().__init__(padding=16, spacing=4, clickable=True)
        top = QHBoxLayout()
        top.setSpacing(8)
        if icon_name:
            ic = QLabel()
            ic.setPixmap(icon(icon_name, color or theme.palette()["muted"], 16).pixmap(16, 16))
            top.addWidget(ic)
        top.addWidget(label(title, "CardLabel"))
        top.addStretch()
        self.add(top)
        self.value = label(value, "Big")
        if color:
            self.value.setStyleSheet(f"color:{color}")
        self.add(self.value)
        self.caption = label(caption, "Faint")
        self.add(self.caption)
        self.setMinimumWidth(110)

    def set(self, value: str, caption: str = ""):
        self.value.setText(value)
        self.caption.setText(caption)


class HealthRing(QWidget):
    def __init__(self, size: int = 116):
        super().__init__()
        self.score = None
        self.setFixedSize(size, size)

    def set_score(self, s):
        self.score = s
        self.update()

    def paintEvent(self, _):
        p = theme.palette()
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        w = 11
        r = QRectF(w / 2 + 2, w / 2 + 2, self.width() - w - 4, self.height() - w - 4)
        qp.setPen(QPen(QColor(p["surface2"]), w, Qt.SolidLine, Qt.RoundCap))
        qp.drawArc(r, 0, 360 * 16)
        s = self.score
        if s is not None:
            col = p["ok"] if s >= 80 else p["warning"] if s >= 50 else p["critical"]
            qp.setPen(QPen(QColor(col), w, Qt.SolidLine, Qt.RoundCap))
            qp.drawArc(r, 90 * 16, -int(360 * 16 * s / 100))
        qp.setPen(QColor(p["text"]))
        f = QFont(self.font())
        f.setPixelSize(30)
        f.setWeight(QFont.Bold)
        qp.setFont(f)
        qp.drawText(self.rect().adjusted(0, -8, 0, -8), Qt.AlignCenter, "—" if s is None else str(s))
        f.setPixelSize(11)
        f.setWeight(QFont.Normal)
        qp.setFont(f)
        qp.setPen(QColor(p["muted"]))
        qp.drawText(self.rect().adjusted(0, 30, 0, 0), Qt.AlignCenter, "/ 100")
        qp.end()


class BarList(QWidget):
    """Horizontal bar chart: rows of (label, value, colour). Click a row to emit its label."""
    clicked = Signal(str)

    def __init__(self, row_h: int = 30):
        super().__init__()
        self.rows: list[tuple[str, float, str]] = []
        self.row_h = row_h
        self.setMouseTracking(True)
        self.hover = -1
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_rows(self, rows):
        self.rows = rows
        self.setFixedHeight(max(1, len(rows)) * self.row_h + 4)
        self.update()

    def mouseMoveEvent(self, e):
        i = int(e.position().y() // self.row_h)
        if i != self.hover:
            self.hover = i
            self.setCursor(Qt.PointingHandCursor if 0 <= i < len(self.rows) else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, _):
        self.hover = -1
        self.update()

    def mouseReleaseEvent(self, e):
        i = int(e.position().y() // self.row_h)
        if 0 <= i < len(self.rows):
            self.clicked.emit(self.rows[i][0])

    def paintEvent(self, _):
        p = theme.palette()
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        if not self.rows:
            qp.setPen(QColor(p["faint"]))
            qp.drawText(self.rect(), Qt.AlignCenter, "—")
            return
        mx = max(v for _, v, _ in self.rows) or 1
        lw = min(190, int(self.width() * 0.42))
        vw = 64
        rtl = self.layoutDirection() == Qt.RightToLeft
        for i, (lab, v, col) in enumerate(self.rows):
            y = i * self.row_h
            if i == self.hover:
                qp.setPen(Qt.NoPen)
                qp.setBrush(QColor(p["hover"]))
                qp.drawRoundedRect(QRectF(0, y + 1, self.width(), self.row_h - 2), 6, 6)
            qp.setPen(QColor(p["text"]))
            text_rect = QRectF(self.width() - lw - 6, y, lw, self.row_h) if rtl else QRectF(8, y, lw, self.row_h)
            qp.drawText(text_rect, (Qt.AlignRight if rtl else Qt.AlignLeft) | Qt.AlignVCenter,
                        qp.fontMetrics().elidedText(lab, Qt.ElideRight, lw - 6))
            bar_max = self.width() - lw - vw - 24
            bw = max(3, bar_max * v / mx)
            bh = 8
            bx = (self.width() - lw - 14 - bw) if rtl else (lw + 14)
            qp.setPen(Qt.NoPen)
            qp.setBrush(QColor(p["surface2"]))
            qp.drawRoundedRect(QRectF((vw + 8) if rtl else lw + 14, y + (self.row_h - bh) / 2, bar_max, bh), 4, 4)
            qp.setBrush(QColor(col))
            qp.drawRoundedRect(QRectF(bx, y + (self.row_h - bh) / 2, bw, bh), 4, 4)
            qp.setPen(QColor(p["muted"]))
            vr = QRectF(4, y, vw, self.row_h) if rtl else QRectF(self.width() - vw - 6, y, vw, self.row_h)
            qp.drawText(vr, (Qt.AlignLeft if rtl else Qt.AlignRight) | Qt.AlignVCenter, f"{int(v):,}")
        qp.end()


class StackBar(QWidget):
    """A thin bar split into critical / warning / opportunity segments."""

    def __init__(self):
        super().__init__()
        self.values = (0, 0, 0)
        self.setFixedHeight(6)

    def set(self, c, w, o):
        self.values = (c, w, o)
        self.update()

    def paintEvent(self, _):
        p = theme.palette()
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        total = sum(self.values) or 1
        x = 0.0
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(p["surface2"]))
        qp.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 3, 3)
        for v, key in zip(self.values, ("critical", "warning", "opportunity")):
            if not v:
                continue
            w = self.width() * v / total
            qp.setBrush(QColor(p[key]))
            qp.drawRoundedRect(QRectF(x, 0, max(w, 3), self.height()), 3, 3)
            x += w
        qp.end()


def pill(sev: str, text: str | None = None) -> QLabel:
    fg, bg = theme.sev_colors(sev)
    lb = QLabel(text or t(sev.capitalize()))
    lb.setStyleSheet(f"background:{bg}; color:{fg}; border-radius:9px; padding:2px 9px; font-size:11px; font-weight:700;")
    lb.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return lb


def status_pill(ok: bool | None, text: str) -> QLabel:
    p = theme.palette()
    fg, bg = ((p["ok"], p["primary_soft"]) if ok else (p["critical"], p["critical_soft"])) if ok is not None else \
        (p["muted"], p["surface2"])
    lb = QLabel(text)
    lb.setStyleSheet(f"background:{bg}; color:{fg}; border-radius:9px; padding:3px 10px; font-size:12px; font-weight:600;")
    return lb


class Toast(QLabel):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.hide()
        self.timer = QTimer(self, singleShot=True, timeout=self.hide)

    def show_message(self, text: str, ms: int = 3200):
        self.setText(text)
        self.adjustSize()
        par = self.parentWidget()
        self.move((par.width() - self.width()) // 2, par.height() - self.height() - 28)
        self.raise_()
        self.show()
        self.timer.start(ms)


def hline() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background:{theme.palette()['border_soft']};")
    return f


def empty_state(icon_name: str, title: str, text: str, action: QWidget | None = None) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.addStretch()
    ic = QLabel()
    ic.setPixmap(icon(icon_name, theme.palette()["faint"], 44).pixmap(44, 44))
    ic.setAlignment(Qt.AlignCenter)
    lay.addWidget(ic)
    h = label(title, "H2")
    h.setAlignment(Qt.AlignCenter)
    lay.addWidget(h)
    m = label(text, "Muted", wrap=True)
    m.setAlignment(Qt.AlignCenter)
    m.setMaximumWidth(460)
    row = QHBoxLayout()
    row.addStretch()
    row.addWidget(m)
    row.addStretch()
    lay.addLayout(row)
    if action:
        r2 = QHBoxLayout()
        r2.addStretch()
        r2.addWidget(action)
        r2.addStretch()
        lay.addLayout(r2)
    lay.addStretch()
    return w


# ------------------------------------------------------------------------------- workers
class Worker(QThread):
    """Run fn(*args, **kwargs) in a thread. If fn accepts `emit`, it can stream text back."""
    result = Signal(object)
    error = Signal(str)
    chunk = Signal(str)

    def __init__(self, fn, *args, stream: bool = False, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs, self.stream = fn, args, kwargs, stream

    def run(self):
        try:
            if self.stream:
                res = self.fn(*self.args, on_text=self.chunk.emit, **self.kwargs)
            else:
                res = self.fn(*self.args, **self.kwargs)
            self.result.emit(res)
        except Exception as e:
            msg = str(e) or type(e).__name__
            if not getattr(e, "user_facing", False) and type(e).__name__ not in ("AIError", "RuntimeError", "ValueError"):
                traceback.print_exc()
            self.error.emit(msg)


class Bridge(QObject):
    """Thread-safe signals from the crawler thread to the UI."""
    progress = Signal(dict)
    message = Signal(str)
    finished = Signal(bool)
    failed = Signal(str)
    audit_step = Signal(str)


def run_worker(owner, fn, *args, on_result=None, on_error=None, on_chunk=None, stream=False, **kwargs) -> Worker:
    w = Worker(fn, *args, stream=stream, **kwargs)
    if on_result:
        w.result.connect(on_result)
    if on_error:
        w.error.connect(on_error)
    if on_chunk:
        w.chunk.connect(on_chunk)
    jobs = owner.__dict__.setdefault("_jobs", set())
    jobs.add(w)
    w.finished.connect(lambda: jobs.discard(w))
    w.start()
    return w


__all__ = ["QPointF"]
