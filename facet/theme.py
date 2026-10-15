"""Modern look: Fusion style + palette + stylesheet, light and dark, following the operating system."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#6D5BF6"
ACCENT_HOVER = "#5B49EA"

LIGHT = {
    "bg": "#F4F5F9", "surface": "#FFFFFF", "surface2": "#EEF0F6", "border": "#E2E4EE",
    "text": "#1B1D26", "muted": "#6B7080", "soft": "#ECE9FE", "scroll": "#C9CCD8", "viewer": "#101114",
}
DARK = {
    "bg": "#121318", "surface": "#1B1D24", "surface2": "#252832", "border": "#2E313C",
    "text": "#E9EAF0", "muted": "#9097A8", "soft": "#2D2860", "scroll": "#3C404D", "viewer": "#0B0C0F",
}

_current: dict = LIGHT


def colors() -> dict:
    return _current


def is_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def apply_theme(app: QApplication) -> None:
    global _current
    c = DARK if is_dark() else LIGHT
    _current = c
    app.setStyle("Fusion")
    pal = QPalette()
    for role, key in [
        (QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.Base, "surface"),
        (QPalette.ColorRole.AlternateBase, "surface2"), (QPalette.ColorRole.Button, "surface"),
        (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.ToolTipBase, "surface"),
        (QPalette.ColorRole.ToolTipText, "text"), (QPalette.ColorRole.PlaceholderText, "muted"),
        (QPalette.ColorRole.Mid, "border"), (QPalette.ColorRole.Midlight, "surface2"),
    ]:
        pal.setColor(role, QColor(c[key]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(c["muted"]))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(c["muted"]))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(c["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(STYLE.format(accent=ACCENT, accent_hover=ACCENT_HOVER, **c))


def follow_system(app: QApplication, on_change=None) -> None:
    """Re-theme when the user switches between light and dark mode."""
    try:
        def changed(_scheme):
            apply_theme(app)
            if on_change:
                on_change()

        QGuiApplication.styleHints().colorSchemeChanged.connect(changed)
    except Exception:
        pass


STYLE = """
QWidget {{ font-size: 13px; }}
QMainWindow, QDialog {{ background: {bg}; }}
QMainWindow::separator {{ background: {bg}; width: 8px; height: 8px; }}

QToolBar {{ background: {bg}; border: none; padding: 8px 10px 6px 10px; spacing: 4px; }}
QToolBar::separator {{ background: {border}; width: 1px; margin: 6px 6px; }}
QToolBar QToolButton {{ background: transparent; border: none; border-radius: 9px; padding: 7px 12px;
    color: {text}; }}
QToolBar QToolButton:hover {{ background: {surface2}; }}
QToolBar QToolButton:pressed, QToolBar QToolButton:checked {{ background: {soft}; color: {accent}; }}
QToolBar QToolButton:disabled {{ color: {muted}; }}
QToolButton#primary {{ background: {accent}; color: white; font-weight: 600; padding: 7px 30px 7px 14px; }}
QToolButton#primary:hover {{ background: {accent_hover}; }}
QToolButton#primary::menu-button {{ border: none; border-left: 1px solid rgba(255,255,255,0.35);
    border-top-right-radius: 9px; border-bottom-right-radius: 9px; width: 20px; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton#gear {{ padding: 7px 12px; border-radius: 9px; }}
QPushButton#settingsBtn {{ text-align: left; padding: 9px 14px; border-radius: 10px; font-weight: 600; }}
QToolButton#plus {{ color: {accent}; font-weight: 700; border: none; border-radius: 8px; padding: 3px 9px;
    background: transparent; }}
QToolButton#plus:hover {{ background: {soft}; }}

QDockWidget {{ color: {muted}; font-weight: 600; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {soft}; border-radius: 3px; }}
QToolButton#chevronBtn {{ border: none; background: transparent; color: {muted}; font-size: 12px; padding: 0 2px;
    min-width: 16px; }}
QToolButton#chevronBtn:hover {{ color: {accent}; }}
QWidget#sectionHeader {{ background: transparent; }}
QDockWidget::title {{ padding: 10px 12px 2px 14px; background: {bg}; text-align: left; }}

QListView, QListWidget, QTableWidget, QTreeView {{ background: {surface}; border: 1px solid {border};
    border-radius: 12px; padding: 4px; outline: 0; }}
QListWidget::item {{ border-radius: 8px; padding: 5px 6px; margin: 1px 2px; color: {text}; }}
QListWidget::item:hover {{ background: {surface2}; }}
QListWidget::item:selected {{ background: {soft}; color: {text}; }}
QListView#photoGrid {{ background: {bg}; border: none; padding: 6px; }}
QListWidget#faceStrip {{ background: transparent; border: none; padding: 0; }}
QListWidget#faceStrip::item {{ border-radius: 14px; padding: 6px 2px; }}
QWidget#facesPanel {{ background: {surface}; border: 1px solid {border}; border-radius: 14px; }}

QPushButton {{ background: {surface}; border: 1px solid {border}; border-radius: 9px; padding: 7px 14px;
    color: {text}; }}
QPushButton:hover {{ background: {surface2}; }}
QPushButton:pressed {{ background: {soft}; }}
QPushButton:checked {{ background: {accent}; color: white; border-color: {accent}; }}
QPushButton:disabled {{ color: {muted}; }}
QPushButton#primary, QDialogButtonBox QPushButton:default {{ background: {accent}; color: white;
    border: 1px solid {accent}; font-weight: 600; }}
QPushButton#primary:hover, QDialogButtonBox QPushButton:default:hover {{ background: {accent_hover}; }}

QLineEdit, QComboBox, QSpinBox {{ background: {surface}; border: 1px solid {border}; border-radius: 9px;
    padding: 6px 10px; color: {text}; selection-background-color: {accent}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {accent}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {surface}; border: 1px solid {border}; border-radius: 10px;
    padding: 4px; selection-background-color: {soft}; selection-color: {text}; }}
QSpinBox::up-button, QSpinBox::down-button {{ border: none; width: 16px; }}

QMenu {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 7px; color: {text}; }}
QMenu::item:selected {{ background: {soft}; }}
QMenu::item:disabled {{ color: {muted}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 5px 8px; }}
QMenu::icon {{ padding-left: 8px; }}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: 3px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 3px; }}
QScrollBar::handle {{ background: {scroll}; border-radius: 4px; min-height: 32px; min-width: 32px; }}
QScrollBar::handle:hover {{ background: {muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QStatusBar {{ background: {bg}; color: {muted}; }}
QStatusBar::item {{ border: none; }}
QProgressBar {{ background: {surface2}; border: none; border-radius: 5px; max-height: 10px; text-align: center;
    color: transparent; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}
QSlider::groove:horizontal {{ height: 4px; background: {surface2}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: white; border: 1px solid {border}; width: 16px; height: 16px;
    margin: -7px 0; border-radius: 8px; }}

QHeaderView::section {{ background: {surface2}; border: none; padding: 7px; font-weight: 600; color: {muted}; }}
QTableWidget {{ gridline-color: {border}; }}
QGroupBox {{ border: 1px solid {border}; border-radius: 12px; margin-top: 16px; padding: 12px 10px 10px 10px;
    background: {surface}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 4px; color: {muted}; font-weight: 600; }}
QToolTip {{ background: {surface}; color: {text}; border: 1px solid {border}; border-radius: 8px; padding: 6px 8px; }}
QLabel#muted {{ color: {muted}; }}
QPushButton#chevron {{ border: none; background: transparent; padding: 2px; font-size: 14px; color: {muted}; }}
QPushButton#chevron:hover {{ color: {accent}; }}
QLabel#sectionTitle {{ font-weight: 700; color: {text}; }}
QWidget#viewerPanel {{ background: {surface}; border-left: 1px solid {border}; }}
QGraphicsView {{ border: none; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
"""
