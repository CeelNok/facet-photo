"""Virtualised thumbnail grid (only visible cells are painted / decoded)."""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QAbstractItemView, QListView, QStyle, QStyledItemDelegate

from facet.models import PhotoModel, PhotoRole

TEXT_H = 18
CHIP_H = 17
PAD = 7
RADIUS = 12


class PhotoDelegate(QStyledItemDelegate):
    def __init__(self, view: "PhotoGrid", model: PhotoModel, labels_ref) -> None:
        super().__init__(view)
        self.view = view
        self.model = model
        self.labels_ref = labels_ref
        self.side = 170
        self.small = QFont()
        self.small.setPointSizeF(max(8.0, self.small.pointSizeF() - 2.0))
        self.small_fm = QFontMetrics(self.small)

    def sizeHint(self, option, index) -> QSize:
        return QSize(self.side + 2 * PAD + 4, self.side + 2 * PAD + TEXT_H + CHIP_H + 10)

    def paint(self, painter: QPainter, option, index) -> None:
        p = index.data(PhotoRole)
        if p is None:
            return
        self.view.painted_keys.add(p.key)
        pal = option.palette
        r = QRectF(option.rect.adjusted(4, 4, -4, -4))
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        accent = QColor(pal.color(QPalette.ColorRole.Highlight))

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        # card
        card = QColor(pal.color(QPalette.ColorRole.Base))
        if selected:
            tint = QColor(accent)
            tint.setAlpha(34)
            painter.setPen(QPen(accent, 2))
            painter.setBrush(card)
            painter.drawRoundedRect(r, RADIUS, RADIUS)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(tint)
            painter.drawRoundedRect(r, RADIUS, RADIUS)
        else:
            if hover:
                card = card.darker(104) if card.lightness() > 128 else card.lighter(125)
            painter.setPen(QPen(QColor(pal.color(QPalette.ColorRole.Mid)), 1))
            painter.setBrush(card)
            painter.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)

        box = QRect(int(r.x()) + PAD, int(r.y()) + PAD, self.side, self.side)
        img = self.model.thumbnail(p)
        if img is not None and not img.isNull():
            iw, ih = img.width(), img.height()
            sc = min(box.width() / iw, box.height() / ih)
            tw, th = int(iw * sc), int(ih * sc)
            target = QRectF(box.x() + (box.width() - tw) // 2, box.y() + (box.height() - th) // 2, tw, th)
            clip = QPainterPath()
            clip.addRoundedRect(target, 8, 8)
            painter.save()
            painter.setClipPath(clip)
            painter.drawImage(target, img)
            painter.restore()
        else:
            c = QColor(pal.color(QPalette.ColorRole.Text))
            c.setAlpha(14)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(c)
            painter.drawRoundedRect(QRectF(box.adjusted(8, 8, -8, -8)), 10, 10)

        painter.setFont(self.small)
        if p.is_raw:
            badge = QRectF(box.x() + 6, box.y() + 6, self.small_fm.horizontalAdvance("RAW") + 10, CHIP_H)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 140))
            painter.drawRoundedRect(badge, CHIP_H / 2, CHIP_H / 2)
            painter.setPen(QColor("white"))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, "RAW")

        y = box.bottom() + 6
        painter.setPen(pal.color(QPalette.ColorRole.Text))
        name = self.small_fm.elidedText(p.name, Qt.TextElideMode.ElideMiddle, box.width())
        painter.drawText(QRect(box.x(), y, box.width(), TEXT_H), Qt.AlignmentFlag.AlignCenter, name)

        # label chips (pills)
        x = box.x()
        y += TEXT_H
        right = box.right()
        labels = [l for l in self.labels_ref() if p.has(l)]
        for i, l in enumerate(labels):
            text = ("👤 " + l.name) if l.is_person else l.name
            w = min(self.small_fm.horizontalAdvance(text) + 14, 96)
            rest = len(labels) - i - 1
            if x + w > right - (24 if rest else 0):
                more = f"+{len(labels) - i}"
                painter.setPen(pal.color(QPalette.ColorRole.PlaceholderText))
                painter.drawText(QRect(x + 2, y, right - x, CHIP_H), Qt.AlignmentFlag.AlignVCenter, more)
                break
            chip = QRectF(x, y, w, CHIP_H)
            col = QColor(l.color)
            bg = QColor(col)
            bg.setAlpha(42)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(chip, CHIP_H / 2, CHIP_H / 2)
            painter.setPen(col.darker(125) if pal.color(QPalette.ColorRole.Base).lightness() > 128 else col.lighter(135))
            painter.drawText(chip.adjusted(7, 0, -5, 0), Qt.AlignmentFlag.AlignVCenter,
                             self.small_fm.elidedText(text, Qt.TextElideMode.ElideRight, w - 12))
            x += w + 4
        painter.restore()


class PhotoGrid(QListView):
    open_requested = Signal()
    label_key = Signal(int)  # 0-based label index from number keys
    clear_key = Signal()     # Backspace / Delete: take every label off the selection

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.painted_keys: set[str] = set()
        self.loader = None
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setLayoutMode(QListView.LayoutMode.Batched)
        self.setBatchSize(400)
        self.setSpacing(4)
        self.setObjectName("photoGrid")
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(24)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setUniformItemSizes(True)
        self.setWordWrap(False)
        # Drag photos onto a collection, or out to Finder / Explorer (copy). Never reorders the grid.
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.doubleClicked.connect(lambda _i: self.open_requested.emit())

    def set_cell_side(self, side: int) -> None:
        d: PhotoDelegate = self.itemDelegate()
        d.side = side
        # Forces a relayout with the new uniform size.
        self.setGridSize(QSize())
        self.scheduleDelayedItemsLayout()
        self.viewport().update()

    def paintEvent(self, e) -> None:
        full = e.rect().contains(self.viewport().rect())
        if full:
            self.painted_keys = set()
        super().paintEvent(e)
        if full and self.loader is not None:
            # Anything that is not on screen after this paint is no longer worth decoding.
            self.loader.set_wanted(set(self.painted_keys))

    def keyPressEvent(self, e) -> None:
        k = e.key()
        if k in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.open_requested.emit()
            return
        if k in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self.clear_key.emit()
            return
        if Qt.Key.Key_1 <= k <= Qt.Key.Key_9 and not (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.label_key.emit(k - Qt.Key.Key_1)
            return
        super().keyPressEvent(e)
