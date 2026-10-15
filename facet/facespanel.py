"""“Faces in this view” strip: round thumbnails of detected people, named or not."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem, QMenu, QPushButton, QVBoxLayout, QWidget,
)

from facet.i18n import tr

AVATAR = 60


def round_avatar(jpeg: bytes | None, size: int = AVATAR, ring: str | None = None) -> QIcon:
    src = QPixmap()
    if jpeg:
        src.loadFromData(jpeg)
    dpr = 2.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    inset = 3 if ring else 0
    r = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
    path = QPainterPath()
    path.addEllipse(r)
    p.setClipPath(path)
    if not src.isNull():
        s = src.scaled(int(r.width() * dpr), int(r.height() * dpr), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                       Qt.TransformationMode.SmoothTransformation)
        s.setDevicePixelRatio(dpr)
        p.drawPixmap(r.topLeft(), s, QRectF(0, 0, s.width(), s.height()))
    else:
        p.fillRect(r, QColor(128, 128, 128, 60))
    p.setClipping(False)
    if ring:
        p.setPen(QPen(QColor(ring), 2.5))
        p.drawEllipse(r.adjusted(-1.5, -1.5, 1.5, 1.5))
    p.end()
    return QIcon(pm)


class FacesPanel(QWidget):
    activated = Signal(str, object)        # kind ("person" | "cluster"), id   – click: filter
    name_requested = Signal(str, object)   # double-click / menu: name or edit
    ignore_requested = Signal(str, object)
    jev_requested = Signal(str)            # person label id: search with Jev too
    name_jev_requested = Signal(str, object)  # unnamed group: name it, then search with Jev too
    scan_requested = Signal()
    collapsed_changed = Signal(bool)

    def __init__(self, parent=None, collapsed: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("facesPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 8)
        lay.setSpacing(4)
        head = QHBoxLayout()
        self.toggle = QPushButton()
        self.toggle.setObjectName("chevron")
        self.toggle.setFlat(True)
        self.toggle.setFixedWidth(28)
        self.toggle.setToolTip(tr("Show / hide faces"))
        self.toggle.clicked.connect(lambda: self.set_collapsed(not self.collapsed))
        title = QLabel(tr("Faces in this view"))
        title.setObjectName("sectionTitle")
        head.addWidget(self.toggle)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.scan_btn = QPushButton(tr("Find faces"))
        self.scan_btn.setToolTip(tr("Detect and group faces on the photos of this view (runs on this computer, "
                                    "free, nothing is uploaded)"))
        self.scan_btn.clicked.connect(self.scan_requested.emit)
        head.addWidget(title)
        head.addSpacing(8)
        head.addWidget(self.status, 1)
        head.addWidget(self.scan_btn)
        lay.addLayout(head)

        self.list = QListWidget()
        self.list.setObjectName("faceStrip")
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setFlow(QListView.Flow.LeftToRight)
        self.list.setWrapping(True)  # drag the strip taller to see more people
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setIconSize(QSize(AVATAR, AVATAR))
        self.list.setGridSize(QSize(AVATAR + 40, AVATAR + 48))
        self.list.setMinimumHeight(AVATAR + 56)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list.setWordWrap(True)
        self.list.setUniformItemSizes(True)
        self.list.itemClicked.connect(self._clicked)
        self.list.itemDoubleClicked.connect(self._double)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.empty = QLabel(tr("No faces yet. Press “Find faces” – or they are found automatically after a folder "
                               "opens (Settings)."))
        self.empty.setObjectName("muted")
        self.empty.setWordWrap(True)
        lay.addWidget(self.list)
        lay.addWidget(self.empty)
        self.active: tuple[str, object] | None = None
        self.collapsed = False
        self._has = False
        self.set_collapsed(collapsed)

    def set_collapsed(self, on: bool) -> None:
        self.collapsed = on
        self.toggle.setText("▸" if on else "▾")
        self.list.setVisible(not on and self._has)
        self.empty.setVisible(not on and not self._has)
        head_h = self.toggle.sizeHint().height() + 22
        self.setMaximumHeight(head_h if on else 16777215)
        self.setMinimumHeight(head_h if on else head_h + 60)
        self.collapsed_changed.emit(on)

    def set_groups(self, groups: list[dict]) -> None:
        """groups: {kind, id, name, count, thumb, color}"""
        self.list.clear()
        for g in groups:
            named = g["kind"] == "person"
            text = f"{g['name']}\n{g['count']}" if named else f"{tr('Unnamed')}\n{g['count']}"
            it = QListWidgetItem(round_avatar(g["thumb"], ring=g.get("color") if named else None), text)
            it.setData(Qt.ItemDataRole.UserRole, (g["kind"], g["id"]))
            it.setToolTip(tr("{name} · on {n} photos\nClick: show these photos · double-click: edit",
                             name=g["name"], n=g["count"]) if named else
                          tr("Unnamed person · on {n} photos\nClick: show these photos · double-click: name",
                             n=g["count"]))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            if not named:
                it.setForeground(self.palette().color(self.palette().ColorRole.PlaceholderText))
            self.list.addItem(it)
            if self.active == (g["kind"], g["id"]):
                it.setSelected(True)
        self._has = bool(groups)
        self.list.setVisible(self._has and not self.collapsed)
        self.empty.setVisible(not self._has and not self.collapsed)

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def _clicked(self, it: QListWidgetItem) -> None:
        kind, ident = it.data(Qt.ItemDataRole.UserRole)
        self.active = None if self.active == (kind, ident) else (kind, ident)
        if self.active is None:
            self.list.clearSelection()
        self.activated.emit(kind, ident)

    def _double(self, it: QListWidgetItem) -> None:
        kind, ident = it.data(Qt.ItemDataRole.UserRole)
        self.name_requested.emit(kind, ident)

    def _menu(self, pos) -> None:
        it = self.list.itemAt(pos)
        if not it:
            return
        kind, ident = it.data(Qt.ItemDataRole.UserRole)
        m = QMenu(self)
        m.addAction(tr("Show these photos"), lambda: self._clicked(it))
        if kind == "cluster":
            m.addAction(tr("Name this person…"), lambda: self.name_requested.emit(kind, ident))
            m.addAction(tr("Name and also search with Jev AI (side views, small faces)…"),
                        lambda: self.name_jev_requested.emit(kind, ident))
            m.addSeparator()
            m.addAction(tr("Ignore (not a person / not interesting)"),
                        lambda: self.ignore_requested.emit(kind, ident))
        else:
            m.addAction(tr("Edit person…"), lambda: self.name_requested.emit(kind, ident))
            m.addAction(tr("Also search with Jev AI (side views, small faces)…"),
                        lambda: self.jev_requested.emit(ident))
            m.addAction(tr("Forget the name (faces become unnamed)"),
                        lambda: self.ignore_requested.emit(kind, ident))
        m.exec(self.list.mapToGlobal(pos))
