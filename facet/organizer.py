"""Copy / move photos into folders (by label or into one chosen folder), with undo."""

from __future__ import annotations

import os
import re
import shutil
import threading
from dataclasses import dataclass

from PySide6.QtCore import QFile, QObject, Signal

from facet.i18n import tr
from facet.imaging import SUPPORTED_EXTS
from facet.scanner import Photo

SIDECAR_EXTS = {".xmp", ".aae", ".thm", ".pp3", ".dop", ".on1"}


@dataclass
class Op:
    src: str
    dst_dir: str
    primary: bool  # False for sidecar / companion files
    dst: str = ""


def safe_folder_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(". ")
    return name or "label"


def _companions(path: str, index: dict[str, dict[str, list[str]]]) -> list[str]:
    d, fn = os.path.split(path)
    if d not in index:
        groups: dict[str, list[str]] = {}
        try:
            for n in os.listdir(d):
                groups.setdefault(os.path.splitext(n)[0].lower(), []).append(n)
        except OSError:
            pass
        index[d] = groups
    stem = os.path.splitext(fn)[0].lower()
    out = []
    for n in index[d].get(stem, []) + index[d].get(fn.lower(), []):  # IMG_1.xmp, IMG_1.jpg, IMG_1.CR2.xmp
        if n == fn:
            continue
        ext = os.path.splitext(n)[1].lower()
        if ext in SIDECAR_EXTS or ext in SUPPORTED_EXTS:
            out.append(os.path.join(d, n))
    return out


def _with_sidecars(pairs: list[tuple[Photo, str]], include: bool) -> list[Op]:
    ops: list[Op] = []
    seen: set[tuple[str, str]] = set()
    index: dict = {}
    primaries = {p.path for p, _ in pairs}
    for p, dst in pairs:
        if (p.path, dst) not in seen:
            seen.add((p.path, dst))
            ops.append(Op(p.path, dst, True))
        if include:
            for c in _companions(p.path, index):
                if c not in primaries and (c, dst) not in seen:
                    seen.add((c, dst))
                    ops.append(Op(c, dst, False))
    return ops


def plan_by_labels(photos: list[Photo], labels, base: str, move: bool, unlabeled: str | None,
                   sidecars: bool) -> list[Op]:
    """One sub-folder per label. Copy: a photo goes into every matching folder.
    Move: into the first matching label in label order (a file can only be in one place)."""
    pairs: list[tuple[Photo, str]] = []
    for p in photos:
        hits = [l for l in labels if p.has(l)]
        if move:
            hits = hits[:1]
        for l in hits:
            pairs.append((p, os.path.join(base, safe_folder_name(l.name))))
        if not hits and unlabeled:
            pairs.append((p, os.path.join(base, safe_folder_name(unlabeled))))
    return _with_sidecars(pairs, sidecars)


def plan_to_folder(photos: list[Photo], dst: str, sidecars: bool) -> list[Op]:
    return _with_sidecars([(p, dst) for p in photos], sidecars)


def _unique(dst_dir: str, name: str) -> str:
    target = os.path.join(dst_dir, name)
    if not os.path.exists(target):
        return target
    stem, ext = os.path.splitext(name)
    i = 1
    while True:
        target = os.path.join(dst_dir, f"{stem} ({i}){ext}")
        if not os.path.exists(target):
            return target
        i += 1


class OrganizeJob(QObject):
    progress = Signal(int, int)
    finished = Signal(list, list)  # done ops, error strings

    def __init__(self, ops: list[Op], move: bool) -> None:
        super().__init__()
        self.ops = ops
        self.move = move
        self._cancel = threading.Event()
        self.created_dirs: list[str] = []

    def start(self) -> None:
        threading.Thread(target=self._run, name="organize", daemon=True).start()

    def cancel(self) -> None:
        self._cancel.set()

    def _run(self) -> None:
        done: list[Op] = []
        errors: list[str] = []
        total = len(self.ops)
        for i, op in enumerate(self.ops):
            if self._cancel.is_set():
                break
            try:
                if os.path.normcase(os.path.dirname(op.src)) == os.path.normcase(op.dst_dir):
                    continue  # already there
                if not os.path.isdir(op.dst_dir):
                    os.makedirs(op.dst_dir)
                    self.created_dirs.append(op.dst_dir)
                op.dst = _unique(op.dst_dir, os.path.basename(op.src))
                if self.move:
                    shutil.move(op.src, op.dst)
                else:
                    shutil.copy2(op.src, op.dst)
                done.append(op)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{os.path.basename(op.src)}: {e}")
            self.progress.emit(i + 1, total)
        self.finished.emit(done, errors)


def undo(done: list[Op], moved: bool, created_dirs: list[str]) -> list[str]:
    """Reverse a finished operation. Copies are sent to the OS trash, never hard-deleted."""
    errors = []
    for op in reversed(done):
        try:
            if moved:
                if os.path.exists(op.src):
                    raise FileExistsError(tr("a file with this name already exists at the original location"))
                os.makedirs(os.path.dirname(op.src), exist_ok=True)
                shutil.move(op.dst, op.src)
            elif os.path.exists(op.dst):
                if not QFile.moveToTrash(op.dst):
                    raise OSError(tr("could not move it to the Trash"))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{os.path.basename(op.dst)}: {e}")
    for d in sorted(set(created_dirs), key=len, reverse=True):
        try:
            os.rmdir(d)  # only folders this operation created, and only if empty again
        except OSError:
            pass
    return errors
