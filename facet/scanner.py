"""Folder scanning and the lightweight in-memory photo record."""

from __future__ import annotations

import os
import re

from facet.imaging import RAW_EXTS, SUPPORTED_EXTS
from facet.storage import path_key


class Photo:
    """One file in the grid. ``__slots__`` keeps 100k photos in a few tens of MB."""

    __slots__ = ("path", "key", "name", "ext", "size", "mtime_ns", "is_raw", "scores", "manual")

    def __init__(self, path: str, size: int, mtime_ns: int) -> None:
        self.path = path
        self.key = path_key(path)
        self.name = os.path.basename(path)
        self.ext = os.path.splitext(path)[1].lower()
        self.size = size
        self.mtime_ns = mtime_ns
        self.is_raw = self.ext in RAW_EXTS
        self.scores: dict[str, float] = {}  # label_id -> AI probability (only still-valid ones)
        self.manual: dict[str, int] = {}    # label_id -> 1 / 0 manual override

    @property
    def fsig(self) -> str:
        return f"{self.size}:{self.mtime_ns}"

    def has(self, label) -> bool:
        m = self.manual.get(label.id)
        if m is not None:
            return bool(m)
        v = self.scores.get(label.id)
        return v is not None and v >= label.threshold

    def missing(self, labels) -> list:
        """Labels that apply to this photo (by folder) but have no AI result yet."""
        return [l for l in labels if l.id not in self.scores and l.applies(self.path)]


def scan_folder(folder: str, recursive: bool) -> list[Photo]:
    out: list[Photo] = []
    stack = [folder]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.name.startswith("."):
                        continue
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if recursive:
                                stack.append(e.path)
                            continue
                        if os.path.splitext(e.name)[1].lower() in SUPPORTED_EXTS:
                            st = e.stat()
                            out.append(Photo(e.path, st.st_size, st.st_mtime_ns))
                    except OSError:
                        continue
        except OSError:
            continue
    return out


def load_paths(paths: list[str]) -> tuple[list[Photo], int]:
    """Photos for an explicit file list (collections, history). Returns (photos, missing count)."""
    out: list[Photo] = []
    missing = 0
    seen: set[str] = set()
    for p in paths:
        try:
            st = os.stat(p)
        except OSError:
            missing += 1
            continue
        ph = Photo(p, st.st_size, st.st_mtime_ns)
        if ph.key not in seen:
            seen.add(ph.key)
            out.append(ph)
    return out, missing


_num = re.compile(r"(\d+)")


def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in _num.split(s)]
