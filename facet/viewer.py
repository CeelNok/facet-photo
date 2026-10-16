"""Full-screen viewer with zoom/pan, progressive loading, manual label toggles and face marking.

Loading is progressive to stay light: the cached thumbnail is shown instantly, then a
screen-sized decode, and the full-resolution image only when the user actually zooms in.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut, QTransform
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView, QHBoxLayout,
    QLabel, QPushButton, QVBoxLayout, QWidget,
)

from facet.i18n import tr
from facet.imaging import load_image
from facet.scanner import Photo
from facet.thumbs import pil_to_qimage

STAGE_THUMB, STAGE_DISPLAY, STAGE_FULL, STAGE_RAW = 0, 1, 2, 3


class _Relay(QObject):
    done = Signal(int, str, int, object)  # token, key, stage, QImage | Exception


class ImageView(QGraphicsView):
    need_full = Signal()
    face_selected = Signal(tuple)  # (x0, y0, x1, y1) as fractions of the image

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.item = QGraphicsPixmapItem()
        self.item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene().addItem(self.item)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        from facet.theme import colors

        self.setBackgroundBrush(QColor(colors()["viewer"]))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.fit_mode = True
        self.has_full = False
        self.want_100 = False
        self.viewport().grabGesture(Qt.GestureType.PinchGesture)
        self.face_mode = False
        self._origin: QPointF | None = None
        self._band: QGraphicsRectItem | None = None

    def set_face_mode(self, on: bool) -> None:
        self.face_mode = on
        self.setDragMode(QGraphicsView.DragMode.NoDrag if on else QGraphicsView.DragMode.ScrollHandDrag)
        if on:
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.viewport().unsetCursor()
            self._drop_band()

    def _drop_band(self) -> None:
        if self._band is not None:
            self.scene().removeItem(self._band)
            self._band = None
        self._origin = None

    def mousePressEvent(self, e) -> None:
        if self.face_mode and e.button() == Qt.MouseButton.LeftButton and not self.item.pixmap().isNull():
            self._drop_band()
            self._origin = self.mapToScene(e.position().toPoint())
            pen = QPen(QColor("#22d3ee"), 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self._band = self.scene().addRect(QRectF(self._origin, self._origin), pen, QColor(34, 211, 238, 40))
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self.face_mode and self._band is not None and self._origin is not None:
            self._band.setRect(QRectF(self._origin, self.mapToScene(e.position().toPoint())).normalized())
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if self.face_mode and self._band is not None:
            r = self.item.mapRectFromScene(self._band.rect())
            pw, ph = self.item.pixmap().width(), self.item.pixmap().height()
            self._drop_band()
            x0, y0 = max(0.0, r.left() / pw), max(0.0, r.top() / ph)
            x1, y1 = min(1.0, r.right() / pw), min(1.0, r.bottom() / ph)
            if x1 - x0 > 0.005 and y1 - y0 > 0.005:
                self.face_selected.emit((x0, y0, x1, y1))
            return
        super().mouseReleaseEvent(e)

    def clear(self) -> None:
        self.item.setPixmap(QPixmap())

    def set_image(self, img: QImage, upgrade: bool) -> None:
        pix = QPixmap.fromImage(img)
        old = self.item.pixmap()
        if upgrade and not old.isNull():
            scene_w = old.width() * self.item.scale()
            self.item.setPixmap(pix)
            self.item.setScale(scene_w / pix.width())  # same on-screen size, more pixels
        else:
            self.item.setPixmap(pix)
            self.item.setScale(1.0)
            self.setSceneRect(self.item.sceneBoundingRect())
            self.fit()
        if self.want_100 and self.has_full:
            self.zoom_100()

    def device_ratio(self) -> float:
        """Device pixels per image pixel at the current zoom."""
        return self.transform().m11() * self.item.scale() * self.devicePixelRatioF()

    def fit(self) -> None:
        self.fit_mode = True
        self.want_100 = False
        if not self.item.pixmap().isNull():
            self.fitInView(self.item, Qt.AspectRatioMode.KeepAspectRatio)

    def zoom_by(self, factor: float) -> None:
        if self.item.pixmap().isNull():
            return
        cur = self.transform().m11()
        fit_scale = min(self.viewport().width() / max(1.0, self.sceneRect().width()),
                        self.viewport().height() / max(1.0, self.sceneRect().height()))
        new = max(fit_scale * 0.5, min(cur * factor, 40 / max(1e-6, self.item.scale())))
        self.fit_mode = False
        self.want_100 = False
        self.scale(new / cur, new / cur)
        if not self.has_full and self.device_ratio() > 0.95:
            self.need_full.emit()

    def zoom_100(self) -> None:
        if self.item.pixmap().isNull():
            return
        self.fit_mode = False
        self.want_100 = not self.has_full
        if not self.has_full:
            self.need_full.emit()
        s = 1.0 / (self.item.scale() * self.devicePixelRatioF())
        center = self.mapToScene(self.viewport().rect().center())
        self.setTransform(QTransform.fromScale(s, s))
        self.centerOn(center)

    def toggle_zoom(self, at: QPointF | None = None) -> None:
        if self.fit_mode:
            target = self.mapToScene(at.toPoint()) if at is not None else None
            self.zoom_100()
            if target is not None:
                self.centerOn(target)
        else:
            self.fit()

    # ---------------------------------------------------------------- events

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self.fit_mode:
            self.fit()

    def wheelEvent(self, e) -> None:
        trackpad_scroll = not e.pixelDelta().isNull() and not (e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if trackpad_scroll and not self.fit_mode:
            super().wheelEvent(e)  # two-finger pan
            return
        dy = e.angleDelta().y() or e.pixelDelta().y()
        if dy:
            self.zoom_by(1.0015 ** dy)

    def viewportEvent(self, e) -> bool:
        if e.type() == QEvent.Type.NativeGesture and e.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
            self.zoom_by(1.0 + e.value())
            return True
        if e.type() == QEvent.Type.Gesture:
            g = e.gesture(Qt.GestureType.PinchGesture)
            if g is not None:
                self.zoom_by(g.scaleFactor())
                return True
        return super().viewportEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:
        if not self.face_mode:
            self.toggle_zoom(e.position())


class ViewerWindow(QWidget):
    closed = Signal(str)  # key of the photo shown last

    def __init__(self, host, photos: list[Photo], start: int) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.host = host  # MainWindow: labels, thumbs, set_manual(), analyze_photos()
        self.photos = photos
        self.idx = max(0, min(start, len(photos) - 1))
        self.token = 0
        self.stage = -1
        self.full_requested = False
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="viewer")
        self.prefetch: dict[str, QImage] = {}
        self.relay = _Relay()
        self.relay.done.connect(self._on_loaded)
        self.setWindowTitle(tr("Facet – viewer"))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self.view = ImageView()
        self.view.need_full.connect(self._load_full)
        self.view.face_selected.connect(self._face_selected)

        self.panel = QWidget()
        self.panel.setObjectName("viewerPanel")
        self.panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.panel.setFixedWidth(300)
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(18, 18, 18, 18)
        pl.setSpacing(6)
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-weight:600; font-size:14px")
        self.info = QLabel()
        self.info.setStyleSheet("color:gray")
        self.info.setWordWrap(True)
        pl.addWidget(self.title)
        pl.addWidget(self.info)
        pl.addSpacing(8)
        pl.addWidget(QLabel(tr("<b>Labels</b> <span style='color:gray'>(keys 1–9)</span>")))
        self.checks_box = QVBoxLayout()
        pl.addLayout(self.checks_box)
        self.face_btn = QPushButton(tr("👤  Mark a face  (F)"))
        self.face_btn.setCheckable(True)
        self.face_btn.setToolTip(tr("Drag a box around a face and give it a name. Facet will then find this "
                                    "person on your other photos."))
        self.face_btn.toggled.connect(self._face_mode)
        self.off_btn = QPushButton(tr("Remove all labels  (⌫)"))
        self.off_btn.clicked.connect(self._take_all_off)
        self.reset_btn = QPushButton(tr("Back to the AI's decision"))
        self.reset_btn.setToolTip(tr("Clear manual changes on this photo"))
        self.reset_btn.clicked.connect(self._reset_manual)
        self.analyze_btn = QPushButton(tr("Analyse with AI (this photo)"))
        self.analyze_btn.clicked.connect(lambda: self.host.analyze_photos([self.current], force=True))
        self.raw_btn = QPushButton(tr("Develop RAW at full quality"))
        self.raw_btn.clicked.connect(self._load_raw_full)
        pl.addSpacing(6)
        pl.addWidget(self.face_btn)
        pl.addWidget(self.off_btn)
        pl.addWidget(self.reset_btn)
        pl.addWidget(self.analyze_btn)
        pl.addWidget(self.raw_btn)
        pl.addStretch(1)
        hint = QLabel(tr(
            "← → browse · scroll / pinch: zoom\n"
            "double-click or Z: 100% ↔ fit · 0: fit\n"
            "1–9: toggle label · ⌫: remove all labels\n"
            "F: mark a face · I: panel · Esc: close"
        ))
        hint.setStyleSheet("color:gray; font-size:11px")
        hint.setWordWrap(True)
        pl.addWidget(hint)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.view, 1)
        lay.addWidget(self.panel)

        for seq, fn in [
            (Qt.Key.Key_Right, lambda: self.step(1)), (Qt.Key.Key_Left, lambda: self.step(-1)),
            (Qt.Key.Key_Down, lambda: self.step(1)), (Qt.Key.Key_Up, lambda: self.step(-1)),
            (Qt.Key.Key_Home, lambda: self.go(0)), (Qt.Key.Key_End, lambda: self.go(len(self.photos) - 1)),
            (Qt.Key.Key_Escape, self._escape), (Qt.Key.Key_Space, self.close),
            (Qt.Key.Key_F, self.face_btn.toggle), (Qt.Key.Key_0, self.view.fit), (Qt.Key.Key_Z, self.view.toggle_zoom),
            (Qt.Key.Key_Plus, lambda: self.view.zoom_by(1.25)), (Qt.Key.Key_Equal, lambda: self.view.zoom_by(1.25)),
            (Qt.Key.Key_Minus, lambda: self.view.zoom_by(0.8)),
            (Qt.Key.Key_I, lambda: self.panel.setVisible(not self.panel.isVisible())),
            (Qt.Key.Key_Backspace, self._take_all_off), (Qt.Key.Key_Delete, self._take_all_off),
        ]:
            QShortcut(QKeySequence(seq), self, activated=fn)
        for n in range(9):
            QShortcut(QKeySequence(Qt.Key.Key_1 + n), self, activated=lambda n=n: self.toggle_label(n))

        self.show_current()

    # ---------------------------------------------------------------- navigation

    @property
    def current(self) -> Photo:
        return self.photos[self.idx]

    def step(self, d: int) -> None:
        self.go(self.idx + d)

    def go(self, i: int) -> None:
        if 0 <= i < len(self.photos) and i != self.idx:
            self.face_btn.setChecked(False)
            self.idx = i
            self.show_current()

    def show_current(self) -> None:
        p = self.current
        self.token += 1
        self.stage = -1
        self.full_requested = False
        self.view.has_full = False
        self.view.want_100 = False
        cached = self.prefetch.pop(p.key, None)
        self.prefetch.clear()  # keep at most the current image + one prefetched one in memory
        if cached is not None:
            self.stage = STAGE_DISPLAY
            self.view.set_image(cached, upgrade=False)
        else:
            thumb = self.host.thumbs.get(p.key)
            if thumb is not None:
                self.stage = STAGE_THUMB
                self.view.set_image(thumb, upgrade=False)
            else:
                self.view.clear()
            self._submit(p, STAGE_DISPLAY, self.token)
        self.raw_btn.setVisible(p.is_raw)
        self.host.note_viewed(p)
        self.refresh_panel()
        if cached is not None:
            self._prefetch_next()

    def _display_side(self) -> int:
        scr = self.screen() or self.host.screen()
        g = scr.geometry()
        return int(min(4096, max(g.width(), g.height()) * scr.devicePixelRatio()))

    def _submit(self, p: Photo, stage: int, token: int) -> None:
        side = self._display_side()

        def job():
            try:
                if stage == STAGE_DISPLAY:
                    im = load_image(p.path, side)
                elif stage == STAGE_FULL:
                    im = load_image(p.path, None)
                else:
                    im = load_image(p.path, None, raw_full=True)
                img = pil_to_qimage(im)
                del im
                return img
            except Exception as e:  # noqa: BLE001
                return e

        fut = self.pool.submit(job)
        fut.add_done_callback(lambda f: self.relay.done.emit(token, p.key, stage, f.result()))

    def _load_full(self) -> None:
        if not self.full_requested and self.stage < STAGE_FULL:
            self.full_requested = True
            self._submit(self.current, STAGE_FULL, self.token)

    def _load_raw_full(self) -> None:
        self.info.setText(self.info.text() + tr("\nDeveloping RAW…"))
        self._submit(self.current, STAGE_RAW, self.token)

    def _prefetch_next(self) -> None:
        if self.idx + 1 < len(self.photos):
            self._submit(self.photos[self.idx + 1], STAGE_DISPLAY, -1)

    def _on_loaded(self, token: int, key: str, stage: int, result) -> None:
        if token == -1:  # prefetch
            if isinstance(result, QImage) and self.idx + 1 < len(self.photos) and self.photos[self.idx + 1].key == key:
                self.prefetch = {key: result}
            return
        if token != self.token:
            return
        if isinstance(result, Exception):
            self.info.setText(tr("Could not load:\n{e}", e=result))
            return
        if stage <= self.stage:
            return
        upgrade = self.stage >= STAGE_THUMB and not self.view.fit_mode
        self.stage = stage
        if stage >= STAGE_FULL:
            self.view.has_full = True
        self.view.set_image(result, upgrade=upgrade)
        self.refresh_panel(dims=(result.width(), result.height()))
        if stage == STAGE_DISPLAY:
            self._prefetch_next()

    # ---------------------------------------------------------------- labels panel

    def refresh_panel(self, dims=None) -> None:
        p = self.current
        self.setWindowTitle(f"{p.name} – Facet")
        self.title.setText(p.name)
        extra = f" · {dims[0]}×{dims[1]} px" if dims else ""
        self.info.setText(f"{self.idx + 1} / {len(self.photos)} · {p.size / 1048576:.1f} MB"
                          f"{' · RAW' if p.is_raw else ''}{extra}")
        while self.checks_box.count():
            w = self.checks_box.takeAt(0).widget()
            if w:
                w.hide()  # hide now; deleteLater only runs on the next event loop pass
                w.setParent(None)
                w.deleteLater()
        for i, l in enumerate(self.host.labels):
            v = p.scores.get(l.id)
            m = p.manual.get(l.id)
            ai = f"AI {v * 100:.0f}%" if v is not None else "AI –"
            tag = tr(" · manual") if m is not None else ""
            key = f"{i + 1}  " if i < 9 else "    "
            name = ("👤 " + l.name) if l.is_person else l.name
            cb = QCheckBox(f"{key}{name}   ({ai}{tag})")
            cb.setChecked(p.has(l))
            cb.setStyleSheet(f"QCheckBox::indicator:checked {{ background:{l.color}; border-radius:3px; }}")
            cb.clicked.connect(lambda checked, l=l: self._set(l, checked))
            self.checks_box.addWidget(cb)
        self.reset_btn.setEnabled(bool(p.manual))

    def _set(self, label, checked: bool) -> None:
        self.host.set_manual([self.current], label, 1 if checked else 0)
        self.refresh_panel()

    def toggle_label(self, n: int) -> None:
        if n < len(self.host.labels):
            l = self.host.labels[n]
            self._set(l, not self.current.has(l))

    # ---------------------------------------------------------------- faces

    def _face_mode(self, on: bool) -> None:
        self.view.set_face_mode(on)
        if on:
            self.view.fit()
            self.info.setText(tr("Drag a box around a face…"))
        else:
            self.refresh_panel()

    def _face_selected(self, rect: tuple) -> None:
        self.face_btn.setChecked(False)
        self.host.add_face(self.current, rect, parent=self)
        self.refresh_panel()

    def _escape(self) -> None:
        if self.face_btn.isChecked():
            self.face_btn.setChecked(False)
        else:
            self.close()

    def _take_all_off(self) -> None:
        self.host.take_off(self.host.labels, photos=[self.current])
        self.refresh_panel()

    def _reset_manual(self) -> None:
        for l in self.host.labels:
            self.host.set_manual([self.current], l, None)
        self.refresh_panel()

    def closeEvent(self, e) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.prefetch.clear()
        self.view.clear()
        self.closed.emit(self.current.key if self.photos else "")
        super().closeEvent(e)
