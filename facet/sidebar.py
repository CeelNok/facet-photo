"""Lightroom-style sidebar: collapsible sections stacked in ONE scrollable column.

Lists are as tall as their content (no scroll bars inside the sidebar), so everything reads top to bottom and a
single scroll bar moves the whole sidebar.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)


def autofit_list(lst: QListWidget, min_rows: int = 1) -> None:
    """Keep a list exactly as tall as its rows, so it never scrolls on its own."""
    lst.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def fit() -> None:
        n = lst.count()
        rows = 0
        for i in range(n):
            if not lst.item(i).isHidden():
                rows += max(lst.sizeHintForRow(i), 1) + 2  # +2: item margin from the stylesheet
        rows = max(rows, min_rows * 30)
        lst.setFixedHeight(rows + 2 * lst.frameWidth() + 12)  # + list padding

    timer = QTimer(lst, singleShot=True, interval=0, timeout=fit)
    m = lst.model()
    for sig in (m.rowsInserted, m.rowsRemoved, m.modelReset, m.layoutChanged, m.dataChanged):
        sig.connect(lambda *_a: timer.start())
    lst.refit = timer.start
    timer.start()


class Section(QWidget):
    toggled = Signal(bool)

    def __init__(self, key: str, title: str, body: QWidget, action_text: str | None = None,
                 action_tip: str | None = None, on_action=None, min_open: int = 0) -> None:
        super().__init__()
        self.key = key
        self.body = body
        self.collapsed = False
        self.setObjectName("section")
        if isinstance(body, QListWidget):
            autofit_list(body)

        self.header = QWidget()
        self.header.setObjectName("sectionHeader")
        h = QHBoxLayout(self.header)
        h.setContentsMargins(2, 6, 2, 2)
        h.setSpacing(2)
        self.chevron = QToolButton()
        self.chevron.setObjectName("chevronBtn")
        self.chevron.setAutoRaise(True)
        self.chevron.clicked.connect(lambda: self.set_collapsed(not self.collapsed))
        self.title = QLabel(title)
        self.title.setObjectName("sectionTitle")
        self.title.mousePressEvent = lambda _e: self.set_collapsed(not self.collapsed)
        self.title.setCursor(Qt.CursorShape.PointingHandCursor)
        h.addWidget(self.chevron)
        h.addWidget(self.title, 1)
        self.action = None
        if action_text:
            self.action = QToolButton()
            self.action.setObjectName("plus")
            self.action.setText(action_text)
            self.action.setToolTip(action_tip or "")
            self.action.setCursor(Qt.CursorShape.PointingHandCursor)
            self.action.clicked.connect(on_action)
            h.addWidget(self.action)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 2)
        lay.setSpacing(4)
        lay.addWidget(self.header)
        lay.addWidget(body)
        self._sync()

    def _sync(self) -> None:
        self.chevron.setText("▸" if self.collapsed else "▾")
        self.body.setVisible(not self.collapsed)

    def set_collapsed(self, on: bool) -> None:
        if on == self.collapsed:
            return
        self.collapsed = on
        self._sync()
        self.toggled.emit(on)


class Sidebar(QScrollArea):
    """One scrollable column of sections; click a title (or ▾) to fold a section."""

    def __init__(self, settings) -> None:
        super().__init__()
        self.settings = settings
        self.setObjectName("sidebar")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.inner = QWidget()
        self.inner.setObjectName("sidebarInner")
        self.column = QVBoxLayout(self.inner)
        self.column.setContentsMargins(0, 0, 6, 0)  # room for the scroll bar
        self.column.setSpacing(6)
        self.column.addStretch(1)
        self.setWidget(self.inner)
        self.sections: list[Section] = []

    def add(self, section: Section, size: int = 0, collapsed: bool = False) -> Section:
        stored = self.settings._q.value(f"sidebar/{section.key}/collapsed")
        if stored is not None:
            collapsed = stored in (True, "true")
        section.set_collapsed(collapsed)
        self.column.insertWidget(self.column.count() - 1, section)  # keep the stretch at the bottom
        self.sections.append(section)
        return section

    def restore(self) -> None:
        pos = self.settings._q.value("sidebar/scroll")
        try:
            QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(int(pos or 0)))
        except (TypeError, ValueError):
            pass

    def save(self) -> None:
        self.settings._q.setValue("sidebar/scroll", self.verticalScrollBar().value())
        for s in self.sections:
            self.settings._q.setValue(f"sidebar/{s.key}/collapsed", s.collapsed)
