"""Thumbnail pipeline: disk cache + bounded in-memory LRU + visibility-aware worker threads.

Only thumbnails for cells that are currently on screen are decoded; requests for cells that
scrolled away are dropped before any work is done. Workers sleep on a condition variable when
idle, so the app uses no CPU while the user is just looking at the grid.
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict, deque

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from facet.imaging import make_thumbnail_jpeg

THUMB_SIDE = 320  # stored size; crisp for ~160pt cells on HiDPI screens
CACHE_VERSION = "1"


def pil_to_qimage(im) -> QImage:
    im = im.convert("RGB") if im.mode != "RGB" else im
    data = im.tobytes()
    q = QImage(data, im.width, im.height, im.width * 3, QImage.Format.Format_RGB888)
    return q.convertToFormat(QImage.Format.Format_RGB32)  # owns its pixels; fastest to paint


class ThumbLoader(QObject):
    loaded = Signal(str, QImage)  # path key, image
    failed = Signal(str)

    def __init__(self, cache_dir: str, threads: int = 2, memory_budget_mb: int = 96) -> None:
        super().__init__()
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._lru: OrderedDict[str, QImage] = OrderedDict()
        self._bytes = 0
        self._budget = memory_budget_mb * 1024 * 1024
        self._queue: deque = deque()
        self._pending: set[str] = set()
        self._wanted: set[str] | None = None
        self._cv = threading.Condition()
        self._stop = False
        self._failed: set[str] = set()
        self._threads = [
            threading.Thread(target=self._worker, name=f"thumb-{i}", daemon=True) for i in range(max(1, threads))
        ]
        for t in self._threads:
            t.start()

    # ---------------------------------------------------------------- main-thread API

    def get(self, key: str) -> QImage | None:
        img = self._lru.get(key)
        if img is not None:
            self._lru.move_to_end(key)
        return img

    def request(self, key: str, path: str, sig: str) -> None:
        if key in self._failed:
            return
        with self._cv:
            if key in self._pending:
                return
            self._pending.add(key)
            self._queue.append((key, path, sig))
            self._cv.notify()

    def set_wanted(self, keys: set[str] | None) -> None:
        """Keys currently visible (plus a margin). Queued work for anything else is skipped."""
        with self._cv:
            self._wanted = keys

    def store(self, key: str, img: QImage) -> None:
        with self._cv:
            self._pending.discard(key)
        old = self._lru.pop(key, None)
        if old is not None:
            self._bytes -= old.sizeInBytes()
        self._lru[key] = img
        self._bytes += img.sizeInBytes()
        while self._bytes > self._budget and len(self._lru) > 1:
            _, ev = self._lru.popitem(last=False)
            self._bytes -= ev.sizeInBytes()

    def mark_failed(self, key: str) -> None:
        with self._cv:
            self._pending.discard(key)
        self._failed.add(key)

    def forget(self, key: str) -> None:
        img = self._lru.pop(key, None)
        if img is not None:
            self._bytes -= img.sizeInBytes()
        self._failed.discard(key)

    def clear_memory(self) -> None:
        with self._cv:
            self._queue.clear()
            self._pending.clear()
        self._lru.clear()
        self._bytes = 0
        self._failed.clear()

    def cache_file(self, path: str, sig: str) -> str:
        # Keyed by file name + size + mtime (not the folder), so thumbnails survive moves and copies.
        h = hashlib.sha1(f"{CACHE_VERSION}|{os.path.basename(path)}|{sig}".encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, h[:2], h + ".jpg")

    def shutdown(self) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify_all()

    # ---------------------------------------------------------------- workers

    def _next(self):
        with self._cv:
            while True:
                if self._stop:
                    return None
                while self._queue:
                    item = self._queue.pop()  # LIFO: most recently requested (= just scrolled into view) first
                    if self._wanted is None or item[0] in self._wanted:
                        return item
                    self._pending.discard(item[0])
                self._cv.wait()

    def _worker(self) -> None:
        while True:
            item = self._next()
            if item is None:
                return
            key, path, sig = item
            cf = self.cache_file(path, sig)
            img = QImage()
            if os.path.exists(cf):
                img.load(cf)
            if img.isNull():
                try:
                    os.makedirs(os.path.dirname(cf), exist_ok=True)
                    img = pil_to_qimage(make_thumbnail_jpeg(path, THUMB_SIDE, cf))
                except Exception:
                    self.failed.emit(key)
                    continue
            else:
                img = img.convertToFormat(QImage.Format.Format_RGB32)
            self.loaded.emit(key, img)
