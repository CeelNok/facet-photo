"""Application entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from facet import APP_NAME, ORG_NAME

ASSETS = Path(__file__).resolve().parent / "assets"


def self_test() -> int:
    """Print what this build can do (no window, no user data touched)."""
    from facet import __version__
    from facet.faces import FACES_OK, FaceEngine
    from facet.imaging import HEIF_OK, RAW_OK

    print(f"{APP_NAME} {__version__}: RAW={RAW_OK} HEIC={HEIF_OK} FACES={FACES_OK}")
    if FACES_OK:
        FaceEngine()
        print("face models loaded")
    return 0


def main() -> None:
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    QCoreApplication.setOrganizationName(ORG_NAME)
    QCoreApplication.setApplicationName(APP_NAME)
    app = QApplication(sys.argv)
    app.setApplicationDisplayName(APP_NAME)
    icon = ASSETS / "facet.svg"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    from facet.i18n import set_language
    from facet.storage import ScoreDB, Settings, migrate_legacy

    migrate_legacy()
    settings = Settings()
    set_language(settings.get("language") or None)

    from facet.mainwindow import MainWindow
    from facet.theme import apply_theme, follow_system

    apply_theme(app)
    win = MainWindow(settings, ScoreDB())
    follow_system(app, win.on_theme_changed)
    win.show()
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args and os.path.isdir(args[0]):
        win.open_folder(args[0])
    sys.exit(app.exec())
