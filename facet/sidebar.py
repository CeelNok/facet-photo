"""Lightroom-style sidebar: collapsible sections in a splitter, so every part can be folded or resized."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSplitter, QToolButton, QVBoxLayout, QWidget

QT_MAX = 16777215


class Section(QWidget):
    toggled = Signal(bool)

    def __init__(self, key: str, title: str, body: QWidget, action_text: str | None = None,
                 action_tip: str | None = None, on_action=None, min_open: int = 80) -> None:
        super().__init__()
        self.key = key
        self.body = body
        self.min_open = min_open
        self.collapsed = False
        self.setObjectName("section")

        self.header = QWidget()
        self.header.setObjectName("sectionHeader")
        h = QHBoxLayout(self.header)
        h.setContentsMargins(2, 4, 2, 2)
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
        lay.setContentsMargins(0, 0, 0, 4)
        lay.setSpacing(2)
        lay.addWidget(self.header)
        lay.addWidget(body, 1)
        self._sync()

    def _sync(self) -> None:
        self.chevron.setText("▸" if self.collapsed else "▾")
        self.body.setVisible(not self.collapsed)
        if self.collapsed:
            self.setMaximumHeight(self.header.sizeHint().height() + 6)
            self.setMinimumHeight(self.header.sizeHint().height() + 6)
        else:
            self.setMaximumHeight(QT_MAX)
            self.setMinimumHeight(self.header.sizeHint().height() + 40)

    def set_collapsed(self, on: bool) -> None:
        if on == self.collapsed:
            return
        self.collapsed = on
        self._sync()
        self.toggled.emit(on)


class Sidebar(QSplitter):
    """Vertical stack of sections; drag the gaps to resize, click a title to fold."""

    def __init__(self, settings) -> None:
        super().__init__(Qt.Orientation.Vertical)
        self.settings = settings
        self.setChildrenCollapsible(False)
        self.setHandleWidth(6)
        self.setObjectName("sidebar")
        self.sections: list[Section] = []

    def add(self, section: Section, size: int, collapsed: bool = False) -> Section:
        stored = self.settings._q.value(f"sidebar/{section.key}/collapsed")
        if stored is not None:
            collapsed = stored in (True, "true")
        section.set_collapsed(collapsed)
        section.toggled.connect(lambda on, s=section: self._toggled(s, on))
        self.addWidget(section)
        self.sections.append(section)
        self._default_sizes = getattr(self, "_default_sizes", []) + [size]
        return section

    def restore(self) -> None:
        sizes = self.settings._q.value("sidebar/sizes")
        try:
            sizes = [int(x) for x in sizes] if sizes else None
        except (TypeError, ValueError):
            sizes = None
        self.setSizes(sizes if sizes and len(sizes) == len(self.sections) else self._default_sizes)

    def save(self) -> None:
        self.settings._q.setValue("sidebar/sizes", self.sizes())
        for s in self.sections:
            self.settings._q.setValue(f"sidebar/{s.key}/collapsed", s.collapsed)

    def _toggled(self, section: Section, collapsed: bool) -> None:
        if collapsed:
            return
        # give an opened section a useful height, taken from the tallest open neighbour
        sizes = self.sizes()
        i = self.sections.index(section)
        if sizes[i] < section.min_open:
            need = section.min_open - sizes[i]
            j = max((k for k in range(len(sizes)) if k != i and not self.sections[k].collapsed),
                    key=lambda k: sizes[k], default=None)
            if j is not None:
                take = min(need, max(0, sizes[j] - self.sections[j].min_open))
                sizes[j] -= take
                sizes[i] += take
                self.setSizes(sizes)
