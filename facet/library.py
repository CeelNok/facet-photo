"""Lightroom-style library panel: saved folders, collections and recently opened photos."""

from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QMenu, QMessageBox, QToolButton,
    QVBoxLayout, QWidget,
)

from facet.i18n import tr
from facet.imaging import SUPPORTED_EXTS
from facet.storage import ScoreDB

RECENT = "recent"


def section_header(title: str, plus_tip: str, on_plus) -> tuple[QWidget, QToolButton]:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(2, 6, 0, 2)
    lbl = QLabel(title)
    lbl.setObjectName("sectionTitle")
    btn = QToolButton()
    btn.setText("+")
    btn.setToolTip(plus_tip)
    btn.setObjectName("plus")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(on_plus)
    h.addWidget(lbl, 1)
    h.addWidget(btn)
    return w, btn


class DropList(QListWidget):
    """List that accepts files/folders dragged from the grid, Finder or Explorer onto an item."""

    dropped = Signal(object, list)  # item (or None), local paths

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setIconSize(QSize(16, 16))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setUniformItemSizes(True)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.dropped.emit(self.itemAt(e.position().toPoint()), paths)
            e.acceptProposedAction()


class LibraryPanel(QWidget):
    open_folder = Signal(str)
    open_collection = Signal(int)
    open_recent = Signal()
    add_folder_requested = Signal()
    add_selected_to = Signal(int)  # collection id
    collections_changed = Signal()
    reveal = Signal(str)

    def __init__(self, db: ScoreDB, parent=None) -> None:
        """Owns the folder and collection lists; the main window places them in sidebar sections."""
        super().__init__(parent)
        self.hide()
        self.db = db
        self.active: tuple[str, object] | None = None
        self.folders = DropList()
        self.folders.setToolTip(tr("Click to open · drop a folder here to add it to the library"))
        self.folders.itemClicked.connect(self._folder_clicked)
        self.folders.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folders.customContextMenuRequested.connect(self._folder_menu)
        self.folders.dropped.connect(self._folders_dropped)
        self.colls = DropList()
        self.colls.setToolTip(tr("Drag photos from the grid or your file manager onto a collection to add them"))
        self.colls.itemClicked.connect(self._coll_clicked)
        self.colls.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.colls.customContextMenuRequested.connect(self._coll_menu)
        self.colls.dropped.connect(self._colls_dropped)
        self.refresh()

    # ---------------------------------------------------------------- content

    def refresh(self) -> None:
        self.folders.clear()
        for path, count, recursive in self.db.folders():
            name = os.path.basename(path.rstrip("/\\")) or path
            it = QListWidgetItem(f"📁  {name}" + (f"  ({count})" if count else ""))
            it.setData(Qt.ItemDataRole.UserRole, path)
            it.setToolTip(path + (tr("\n(including subfolders)") if recursive else ""))
            if not os.path.isdir(path):
                it.setForeground(Qt.GlobalColor.gray)
                it.setToolTip(path + tr("\nFolder not available (disconnected drive?)"))
            self.folders.addItem(it)
        self.colls.clear()
        rec = QListWidgetItem("🕘  " + tr("Recently opened photos"))
        rec.setData(Qt.ItemDataRole.UserRole, RECENT)
        rec.setToolTip(tr("Photos you recently opened in the viewer"))
        self.colls.addItem(rec)
        for cid, name, count in self.db.collections():
            it = QListWidgetItem(f"🗂  {name}  ({count})")
            it.setData(Qt.ItemDataRole.UserRole, cid)
            self.colls.addItem(it)
        self._highlight()

    def set_active(self, kind: str, ident) -> None:
        self.active = (kind, ident)
        self._highlight()

    def _highlight(self) -> None:
        for lst, kind in ((self.folders, "folder"), (self.colls, None)):
            for i in range(lst.count()):
                it = lst.item(i)
                data = it.data(Qt.ItemDataRole.UserRole)
                if kind == "folder":
                    on = self.active == ("folder", data)
                elif data == RECENT:
                    on = self.active == ("recent", None)
                else:
                    on = self.active == ("collection", data)
                f = it.font()
                f.setBold(on)
                it.setFont(f)
                it.setSelected(on)

    # ---------------------------------------------------------------- folders

    def _folder_clicked(self, it: QListWidgetItem) -> None:
        path = it.data(Qt.ItemDataRole.UserRole)
        if os.path.isdir(path):
            self.open_folder.emit(path)
        else:
            QMessageBox.information(self, tr("Folder"), tr("This folder is not available:\n{path}", path=path))
            self._highlight()

    def _folders_dropped(self, _item, paths: list[str]) -> None:
        dirs = [p for p in paths if os.path.isdir(p)]
        for d in dirs:
            self.db.add_folder(os.path.abspath(d))
        self.refresh()
        if dirs:
            self.open_folder.emit(os.path.abspath(dirs[0]))

    def _folder_menu(self, pos) -> None:
        it = self.folders.itemAt(pos)
        if not it:
            return
        path = it.data(Qt.ItemDataRole.UserRole)
        m = QMenu(self)
        m.addAction(tr("Open"), lambda: self._folder_clicked(it))
        m.addAction(tr("Show in file manager"), lambda: self.reveal.emit(path))
        m.addSeparator()
        m.addAction(tr("Remove from list (files are kept)"), lambda: (self.db.remove_folder(path), self.refresh()))
        m.exec(self.folders.mapToGlobal(pos))

    # ---------------------------------------------------------------- collections

    def new_collection(self, paths: list[str] | None = None) -> int | None:
        name, ok = QInputDialog.getText(self, tr("New collection"), tr("Collection name:"))
        name = name.strip()
        if not ok or not name:
            return None
        cid = self.db.create_collection(name)
        if paths:
            self.db.add_to_collection(cid, paths)
        self.refresh()
        self.collections_changed.emit()
        return cid

    def _coll_clicked(self, it: QListWidgetItem) -> None:
        data = it.data(Qt.ItemDataRole.UserRole)
        if data == RECENT:
            self.open_recent.emit()
        else:
            self.open_collection.emit(int(data))

    def _colls_dropped(self, item, paths: list[str]) -> None:
        files = _image_files(paths)
        if not files:
            return
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        if data is None or data == RECENT:
            self.new_collection(files)
            return
        n = self.db.add_to_collection(int(data), files)
        self.refresh()
        self.collections_changed.emit()
        self.parent().statusBar().showMessage(tr("Added {n} photos to {name}", n=n, name=self.db.collection_name(int(data))), 4000)

    def _coll_menu(self, pos) -> None:
        it = self.colls.itemAt(pos)
        m = QMenu(self)
        if it is None:
            m.addAction(tr("New collection…"), self.new_collection)
        elif it.data(Qt.ItemDataRole.UserRole) == RECENT:
            m.addAction(tr("Open"), self.open_recent.emit)
            m.addAction(tr("Clear list"), self._clear_recent)
        else:
            cid = int(it.data(Qt.ItemDataRole.UserRole))
            m.addAction(tr("Open"), lambda: self.open_collection.emit(cid))
            m.addAction(tr("Add selected photos"), lambda: self.add_selected_to.emit(cid))
            m.addAction(tr("Add photos from files…"), lambda: self._add_files(cid))
            m.addSeparator()
            m.addAction(tr("Rename…"), lambda: self._rename(cid))
            m.addAction(tr("Delete collection (photos are kept)"), lambda: self._delete(cid))
        m.exec(self.colls.mapToGlobal(pos))

    def _add_files(self, cid: int) -> None:
        from PySide6.QtWidgets import QFileDialog

        pattern = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTS))
        files, _ = QFileDialog.getOpenFileNames(self, tr("Add photos"), os.path.expanduser("~"),
                                                tr("Images") + f" ({pattern} {pattern.upper()})")
        if files:
            self.db.add_to_collection(cid, files)
            self.refresh()
            self.collections_changed.emit()

    def _rename(self, cid: int) -> None:
        name, ok = QInputDialog.getText(self, tr("Rename"), tr("New name:"), text=self.db.collection_name(cid))
        if ok and name.strip():
            self.db.rename_collection(cid, name.strip())
            self.refresh()
            self.collections_changed.emit()

    def _delete(self, cid: int) -> None:
        name = self.db.collection_name(cid)
        if QMessageBox.question(self, tr("Delete collection"),
                                tr("Delete the collection “{name}”?\nThe image files are not deleted.", name=name)) \
                == QMessageBox.StandardButton.Yes:
            self.db.delete_collection(cid)
            self.refresh()
            self.collections_changed.emit()

    def _clear_recent(self) -> None:
        self.db.clear_recent()
        self.collections_changed.emit()


def _image_files(paths: list[str]) -> list[str]:
    out = []
    for p in paths:
        if os.path.isdir(p):
            try:
                out += [os.path.join(p, n) for n in sorted(os.listdir(p))
                        if os.path.splitext(n)[1].lower() in SUPPORTED_EXTS]
            except OSError:
                pass
        elif os.path.splitext(p)[1].lower() in SUPPORTED_EXTS:
            out.append(p)
    return out
