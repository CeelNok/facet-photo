"""Qt item models: the photo list and the label/type/text filter on top of it."""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QMimeData, QModelIndex, QSortFilterProxyModel, Qt, QUrl
from PySide6.QtGui import QImage

from facet.i18n import tr
from facet.scanner import Photo
from facet.thumbs import ThumbLoader

PhotoRole = Qt.ItemDataRole.UserRole + 1


class PhotoModel(QAbstractListModel):
    def __init__(self, thumbs: ThumbLoader, labels_ref) -> None:
        super().__init__()
        self.thumbs = thumbs
        self.labels_ref = labels_ref  # callable -> current list[Label]
        self.photos: list[Photo] = []
        self._row: dict[str, int] = {}
        thumbs.loaded.connect(self._on_thumb)
        thumbs.failed.connect(self._on_fail)

    # ------------------------------------------------------------------ Qt API

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.photos)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        p = self.photos[index.row()]
        if role == PhotoRole:
            return p
        if role == Qt.ItemDataRole.DisplayRole:
            return p.name
        if role == Qt.ItemDataRole.ToolTipRole:
            lines = [p.name, f"{p.size / 1048576:.1f} MB" + (" · RAW" if p.is_raw else "")]
            for l in self.labels_ref():
                v = p.scores.get(l.id)
                m = p.manual.get(l.id)
                if v is None and m is None:
                    continue
                mark = "✓" if p.has(l) else "·"
                extra = tr(" (manual)") if m is not None else ""
                pct = f"{v * 100:.0f}%" if v is not None else "–"
                lines.append(f"{mark} {'👤 ' if l.is_person else ''}{l.name}: {pct}{extra}")
            return "\n".join(lines)
        return None

    def flags(self, index):
        f = super().flags(index)
        return f | Qt.ItemFlag.ItemIsDragEnabled if index.isValid() else f

    def mimeTypes(self) -> list[str]:
        return ["text/uri-list"]

    def mimeData(self, indexes) -> QMimeData:
        md = QMimeData()
        rows = sorted({i.row() for i in indexes})
        md.setUrls([QUrl.fromLocalFile(self.photos[r].path) for r in rows])
        return md

    def supportedDragActions(self):
        return Qt.DropAction.CopyAction

    # ------------------------------------------------------------------ helpers

    def set_photos(self, photos: list[Photo]) -> None:
        self.beginResetModel()
        self.photos = photos
        self._row = {p.key: i for i, p in enumerate(photos)}
        self.endResetModel()

    def thumbnail(self, p: Photo) -> QImage | None:
        img = self.thumbs.get(p.key)
        if img is None:
            self.thumbs.request(p.key, p.path, p.fsig)
        return img

    def photo_by_key(self, key: str) -> Photo | None:
        r = self._row.get(key)
        return None if r is None else self.photos[r]

    def touch(self, key: str) -> None:
        r = self._row.get(key)
        if r is not None:
            idx = self.index(r)
            self.dataChanged.emit(idx, idx)

    def touch_all(self) -> None:
        if self.photos:
            self.dataChanged.emit(self.index(0), self.index(len(self.photos) - 1))

    def remove_keys(self, keys: set[str]) -> None:
        keep = [p for p in self.photos if p.key not in keys]
        if len(keep) != len(self.photos):
            for k in keys:
                self.thumbs.forget(k)
            self.set_photos(keep)

    def _on_thumb(self, key: str, img: QImage) -> None:
        self.thumbs.store(key, img)
        r = self._row.get(key)
        if r is not None:
            idx = self.index(r)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])

    def _on_fail(self, key: str) -> None:
        self.thumbs.mark_failed(key)
        self.touch(key)


class PhotoFilter(QSortFilterProxyModel):
    """Filtering only; sorting is done once on the Python list (much cheaper than lessThan callbacks)."""

    def __init__(self, labels_ref) -> None:
        super().__init__()
        self.labels_ref = labels_ref
        self.include: set[str] = set()
        self.exclude: set[str] = set()
        self.match_all = False
        self.special: str | None = None  # None | "unanalyzed" | "unlabeled"
        self.type_filter = "all"  # all | raw | nonraw
        self.text = ""
        self.key_filter: set[str] | None = None  # e.g. photos containing an unnamed face group
        self.setDynamicSortFilter(False)  # no automatic re-filtering on every dataChanged (saves CPU)
        self._prepare()

    def refilter(self) -> None:
        self._prepare()
        self.invalidateFilter()

    def _prepare(self) -> None:
        labels = self.labels_ref()
        by_id = {l.id: l for l in labels}
        self._labels = labels
        self._inc = [by_id[i] for i in self.include if i in by_id]
        self._exc = [by_id[i] for i in self.exclude if i in by_id]

    @property
    def uses_labels(self) -> bool:
        return bool(self.include or self.exclude or self.special or self.key_filter is not None)

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        p: Photo = self.sourceModel().photos[source_row]
        if self.type_filter == "raw" and not p.is_raw:
            return False
        if self.type_filter == "nonraw" and p.is_raw:
            return False
        if self.text and self.text not in p.name.lower():
            return False
        if self.key_filter is not None and p.key not in self.key_filter:
            return False
        if self.special == "unanalyzed" and not p.missing(self._labels):
            return False
        if self.special == "unlabeled" and any(p.has(l) for l in self._labels):
            return False
        if any(p.has(l) for l in self._exc):
            return False
        if self._inc:
            hits = [p.has(l) for l in self._inc]
            if not (all(hits) if self.match_all else any(hits)):
                return False
        return True
