"""Light and dark themes, generated as one Qt stylesheet from a palette."""
from __future__ import annotations

LIGHT = {
    "bg": "#F6F8FA", "surface": "#FFFFFF", "surface2": "#F0F3F6", "hover": "#EEF1F4", "border": "#D8DEE4",
    "border_soft": "#E6EAEF", "text": "#1F2328", "muted": "#59636E", "faint": "#8C959F",
    "primary": "#00E676", "primary_hover": "#00D46C", "primary_press": "#00BF61", "on_primary": "#0D1117",
    "primary_text": "#0F8A47", "primary_soft": "#E3FBEE",
    "accent": "#0969DA", "accent_soft": "#DDF4FF",
    "critical": "#CF222E", "critical_soft": "#FFEBE9", "warning": "#9A6700", "warning_soft": "#FFF8C5",
    "opportunity": "#0969DA", "opportunity_soft": "#DDF4FF", "ok": "#1A7F37",
    "selection": "#DDF4FF", "selection_text": "#1F2328", "shadow": "#1F232814",
}
DARK = {
    "bg": "#0D1117", "surface": "#161B22", "surface2": "#1C2128", "hover": "#21262D", "border": "#30363D",
    "border_soft": "#262C34", "text": "#E6EDF3", "muted": "#8B949E", "faint": "#6E7681",
    "primary": "#00E676", "primary_hover": "#33EB8B", "primary_press": "#00C866", "on_primary": "#0D1117",
    "primary_text": "#00E676", "primary_soft": "#0F2A1C",
    "accent": "#58A6FF", "accent_soft": "#152A44",
    "critical": "#F85149", "critical_soft": "#3B1219", "warning": "#D29922", "warning_soft": "#3A2A0B",
    "opportunity": "#58A6FF", "opportunity_soft": "#152A44", "ok": "#3FB950",
    "selection": "#1F3A5F", "selection_text": "#E6EDF3", "shadow": "#00000066",
}

_current = dict(LIGHT)


def palette() -> dict:
    return _current


def set_theme(name: str) -> dict:
    _current.clear()
    _current.update(DARK if name == "dark" else LIGHT)
    return _current


def sev_colors(sev: str) -> tuple[str, str]:
    p = _current
    return p.get(sev, p["muted"]), p.get(f"{sev}_soft", p["surface2"])


def stylesheet(p: dict | None = None) -> str:
    p = p or _current
    return f"""
* {{ outline: none; }}
QWidget {{ color: {p['text']}; font-size: 13px; }}
QMainWindow, #Content, QDialog {{ background: {p['bg']}; }}
QToolTip {{ background: {p['surface']}; color: {p['text']}; border: 1px solid {p['border']}; padding: 6px 8px; border-radius: 6px; }}

/* ---------- sidebar ---------- */
#Sidebar {{ background: {p['surface']}; border-right: 1px solid {p['border_soft']}; }}
#Sidebar[rtl="true"] {{ border-right: none; border-left: 1px solid {p['border_soft']}; }}
#Brand {{ font-size: 18px; font-weight: 700; }}
#BrandSub {{ color: {p['muted']}; font-size: 11px; }}
#NavSection {{ color: {p['faint']}; font-size: 11px; font-weight: 600; padding: 14px 14px 4px 14px; }}
QPushButton#Nav {{ text-align: left; padding: 9px 12px; border: none; border-radius: 8px; color: {p['muted']};
                   font-weight: 500; background: transparent; }}
QPushButton#Nav[rtl="true"] {{ text-align: right; }}
QPushButton#Nav:hover {{ background: {p['hover']}; color: {p['text']}; }}
QPushButton#Nav:checked {{ background: {p['primary_soft']}; color: {p['primary_text']}; font-weight: 600; }}
QPushButton#NavBadge {{ border: none; }}

/* ---------- top bar ---------- */
#TopBar {{ background: {p['surface']}; border-bottom: 1px solid {p['border_soft']}; }}
QLineEdit#UrlInput {{ font-size: 14px; padding: 9px 14px; border-radius: 10px; background: {p['surface2']};
                      border: 1px solid {p['border_soft']}; }}
QLineEdit#UrlInput:focus {{ border: 1px solid {p['primary']}; background: {p['surface']}; }}
#StatusText {{ color: {p['muted']}; font-size: 12px; }}
#StatValue {{ font-weight: 700; }}

/* ---------- typography ---------- */
#H1 {{ font-size: 22px; font-weight: 700; }}
#H2 {{ font-size: 16px; font-weight: 700; }}
#H3 {{ font-size: 14px; font-weight: 600; }}
#Muted {{ color: {p['muted']}; }}
#Faint {{ color: {p['faint']}; font-size: 12px; }}
#Big {{ font-size: 26px; font-weight: 700; }}
#CardLabel {{ color: {p['muted']}; font-size: 12px; font-weight: 500; }}
#Link {{ color: {p['accent']}; }}

/* ---------- cards ---------- */
#Card {{ background: {p['surface']}; border: 1px solid {p['border_soft']}; border-radius: 14px; }}
#Card:hover[clickable="true"] {{ border: 1px solid {p['border']}; }}
#SoftCard {{ background: {p['surface2']}; border: 1px solid {p['border_soft']}; border-radius: 12px; }}
#Hero {{ background: {p['surface']}; border: 1px solid {p['border_soft']}; border-radius: 18px; }}

/* ---------- buttons ---------- */
QPushButton {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 7px 14px;
               font-weight: 500; }}
QPushButton:hover {{ background: {p['hover']}; }}
QPushButton:pressed {{ background: {p['surface2']}; }}
QPushButton:disabled {{ color: {p['faint']}; background: {p['surface2']}; border-color: {p['border_soft']}; }}
QPushButton#Primary {{ background: {p['primary']}; color: {p['on_primary']}; border: none; font-weight: 700; padding: 8px 18px; }}
QPushButton#Primary:hover {{ background: {p['primary_hover']}; }}
QPushButton#Primary:pressed {{ background: {p['primary_press']}; }}
QPushButton#Primary:disabled {{ background: {p['surface2']}; color: {p['faint']}; }}
QPushButton#Danger {{ color: {p['critical']}; }}
QPushButton#Ghost {{ background: transparent; border: none; color: {p['muted']}; padding: 6px 10px; }}
QPushButton#Ghost:hover {{ background: {p['hover']}; color: {p['text']}; }}
QPushButton#Chip {{ border-radius: 14px; padding: 5px 12px; color: {p['muted']}; background: {p['surface']}; font-size: 12px; }}
QPushButton#Chip:checked {{ background: {p['text']}; color: {p['surface']}; border-color: {p['text']}; font-weight: 600; }}
QPushButton#TaskCard {{ text-align: left; padding: 12px 14px; border-radius: 12px; background: {p['surface']};
                        border: 1px solid {p['border_soft']}; }}
QPushButton#TaskCard:hover {{ border-color: {p['primary']}; }}
QPushButton#TaskCard:checked {{ border: 1px solid {p['primary']}; background: {p['primary_soft']}; }}
QToolButton {{ border: none; border-radius: 6px; padding: 4px; background: transparent; }}
QToolButton:hover {{ background: {p['hover']}; }}

/* ---------- inputs ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 6px 10px;
    selection-background-color: {p['selection']}; selection-color: {p['selection_text']}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {p['primary']}; }}
QLineEdit#Search {{ border-radius: 16px; padding: 6px 14px; background: {p['surface']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 8px;
    selection-background-color: {p['hover']}; selection-color: {p['text']}; padding: 4px; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 16px; border: none; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {p['border']}; background: {p['surface']}; }}
QCheckBox::indicator:checked {{ background: {p['primary']}; border-color: {p['primary']}; image: url(:/check.svg); }}
QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 8px; border: 1px solid {p['border']}; background: {p['surface']}; }}
QRadioButton::indicator:checked {{ border: 4px solid {p['primary']}; }}

/* ---------- tables & lists ---------- */
QTableView, QTreeView, QListView, QListWidget, QTreeWidget {{
    background: {p['surface']}; border: 1px solid {p['border_soft']}; border-radius: 12px;
    gridline-color: {p['border_soft']}; selection-background-color: {p['selection']}; selection-color: {p['selection_text']};
    alternate-background-color: {p['surface2']}; }}
QTableView::item, QTreeView::item {{ padding: 4px 6px; border: none; }}
QTableView::item:hover, QTreeView::item:hover, QListWidget::item:hover {{ background: {p['hover']}; }}
QTableView::item:selected, QTreeView::item:selected, QListWidget::item:selected {{ background: {p['selection']}; color: {p['selection_text']}; }}
QListWidget::item {{ border-radius: 8px; padding: 2px; margin: 1px 4px; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {p['surface2']}; color: {p['muted']}; border: none; border-bottom: 1px solid {p['border_soft']};
    border-right: 1px solid {p['border_soft']}; padding: 7px 8px; font-weight: 600; font-size: 12px; }}
QTableCornerButton::section {{ background: {p['surface2']}; border: none; }}

/* ---------- tabs ---------- */
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {p['muted']}; padding: 8px 14px; margin-right: 4px;
    border-bottom: 2px solid transparent; font-weight: 500; }}
QTabBar::tab:hover {{ color: {p['text']}; }}
QTabBar::tab:selected {{ color: {p['text']}; border-bottom: 2px solid {p['primary']}; font-weight: 600; }}

/* ---------- misc ---------- */
QProgressBar {{ background: {p['surface2']}; border: none; border-radius: 2px; max-height: 4px; }}
QProgressBar::chunk {{ background: {p['primary']}; border-radius: 2px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p['faint']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p['border']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: transparent; }}
QMenu {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p['hover']}; }}
QMenu::indicator {{ width: 14px; height: 14px; }}
QTextBrowser {{ background: {p['surface']}; border: 1px solid {p['border_soft']}; border-radius: 12px; padding: 14px; }}
QGroupBox {{ border: 1px solid {p['border_soft']}; border-radius: 12px; margin-top: 18px; padding: 14px 12px 12px 12px;
    background: {p['surface']}; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {p['text']}; }}
#Toast {{ background: {p['text']}; color: {p['surface']}; border-radius: 10px; padding: 10px 16px; font-weight: 500; }}
"""
