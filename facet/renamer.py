"""Batch renaming: name patterns or find & replace, with RAW+JPEG pairs and sidecars kept together.

* Pattern tokens: {name} {n} {date} {time} {year} {month} {day} {folder} {label}
* Photos with the same name in the same folder (IMG_1.CR2 + IMG_1.JPG) share one new name and one number;
  companion files (.xmp, .aae, IMG_1.CR2.xmp …) follow their photo.
* Renaming is two-phase (everything to a temporary name first), so swapping numbers can never overwrite a file,
  and it rolls back if anything fails.
"""

from __future__ import annotations

import os
import re
import struct
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from facet.imaging import RAW_EXTS, SUPPORTED_EXTS
from facet.organizer import SIDECAR_EXTS

ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
TOKENS = ["{name}", "{n}", "{date}", "{time}", "{folder}", "{label}"]


# --------------------------------------------------------------------------- capture time

def _tiff_datetime(path: str) -> str | None:
    """DateTimeOriginal (or DateTime) from a TIFF-based file: CR2, NEF, ARW, DNG, ORF, RW2, PEF, SRW, TIFF."""
    try:
        with open(path, "rb") as f:
            head = f.read(8)
            if head[:2] == b"II":
                end = "<"
            elif head[:2] == b"MM":
                end = ">"
            else:
                return None
            ifd0 = struct.unpack(end + "I", head[4:8])[0]

            def entries(offset: int) -> dict[int, tuple[int, int, bytes]]:
                f.seek(offset)
                (count,) = struct.unpack(end + "H", f.read(2))
                if count > 2000:
                    return {}
                out = {}
                for _ in range(count):
                    tag, typ, n, val = struct.unpack(end + "HHI4s", f.read(12))
                    out[tag] = (typ, n, val)
                return out

            def ascii_value(e) -> str | None:
                typ, n, val = e
                if typ != 2 or n < 19:
                    return None
                f.seek(struct.unpack(end + "I", val)[0])
                return f.read(19).decode("ascii", "replace")

            ifd = entries(ifd0)
            if 0x8769 in ifd:  # Exif sub-IFD
                exif = entries(struct.unpack(end + "I", ifd[0x8769][2])[0])
                if 36867 in exif:
                    return ascii_value(exif[36867])
            if 306 in ifd:
                return ascii_value(ifd[306])
    except (OSError, struct.error):
        return None
    return None


def capture_time(path: str) -> datetime:
    """When the photo was taken (EXIF), falling back to the file's modification time."""
    raw = None
    ext = os.path.splitext(path)[1].lower()
    if ext in RAW_EXTS or ext in (".tif", ".tiff"):
        raw = _tiff_datetime(path)
    if raw is None and ext not in RAW_EXTS:
        try:
            from PIL import Image

            with Image.open(path) as im:
                exif = im.getexif()
                raw = exif.get_ifd(0x8769).get(36867) or exif.get(306)
        except Exception:
            raw = None
    if raw:
        try:
            return datetime.strptime(str(raw).strip()[:19], "%Y:%m:%d %H:%M:%S")
        except ValueError:
            pass
    return datetime.fromtimestamp(os.path.getmtime(path))


# --------------------------------------------------------------------------- planning

@dataclass
class RenameConfig:
    mode: str = "pattern"          # "pattern" | "replace"
    pattern: str = "{name}"
    start: int = 1
    digits: int = 3
    order: str = "grid"            # "grid" | "time" | "name"
    find: str = ""
    replace: str = ""
    regex: bool = False
    case_sensitive: bool = False
    lower_ext: bool = False
    companions: bool = True


@dataclass
class RenameRow:
    src: str
    dst: str
    primary: bool                  # a photo of the grid (False: companion file)
    status: str = "ok"             # ok | same | conflict | invalid
    note: str = ""


@dataclass
class RenamePlan:
    rows: list[RenameRow] = field(default_factory=list)
    error: str = ""

    @property
    def changes(self) -> list[RenameRow]:
        return [r for r in self.rows if r.status == "ok"]

    @property
    def problems(self) -> list[RenameRow]:
        return [r for r in self.rows if r.status in ("conflict", "invalid")]


def _clean(stem: str) -> str:
    return ILLEGAL.sub("_", stem).strip().rstrip(".")


def _norm(path: str) -> str:
    # macOS and Windows file systems ignore case by default: treat IMG.jpg and img.JPG as the same name
    return os.path.normcase(path).lower()


def build_plan(photos: list, cfg: RenameConfig, times: dict[str, datetime] | None = None, label_of=None) -> RenamePlan:
    plan = RenamePlan()
    times = times or {}
    # 1) groups: same folder + same name without extension → one new name
    groups: dict[tuple[str, str], list] = {}
    for p in photos:
        d, fn = os.path.split(p.path)
        groups.setdefault((d, os.path.splitext(fn)[0].lower()), []).append(p)
    keys = list(groups)
    if cfg.order == "time":
        keys.sort(key=lambda k: min(times.get(p.key, datetime.max) for p in groups[k]))
    elif cfg.order == "name":
        keys.sort(key=lambda k: (k[0].lower(), k[1]))

    if cfg.mode == "replace" and cfg.regex:
        try:
            rx = re.compile(cfg.find, 0 if cfg.case_sensitive else re.IGNORECASE)
        except re.error as e:
            plan.error = str(e)
            return plan

    index: dict[str, dict[str, list[str]]] = {}
    batch = {p.path for p in photos}
    for i, k in enumerate(keys):
        members = groups[k]
        folder, _ = k
        old_stem = os.path.splitext(os.path.basename(members[0].path))[0]
        if cfg.mode == "replace":
            if not cfg.find:
                new_stem = old_stem
            elif cfg.regex:
                new_stem = rx.sub(cfg.replace, old_stem)
            elif cfg.case_sensitive:
                new_stem = old_stem.replace(cfg.find, cfg.replace)
            else:
                new_stem = re.sub(re.escape(cfg.find), lambda _m: cfg.replace, old_stem, flags=re.IGNORECASE)
        else:
            t = min((times[p.key] for p in members if p.key in times), default=None)
            values = {
                "name": old_stem,
                "n": str(cfg.start + i).zfill(max(1, cfg.digits)),
                "folder": os.path.basename(folder.rstrip("/\\")),
                "label": (label_of(members[0]) if label_of else "") or "",
                "date": t.strftime("%Y-%m-%d") if t else "",
                "time": t.strftime("%H-%M-%S") if t else "",
                "year": t.strftime("%Y") if t else "",
                "month": t.strftime("%m") if t else "",
                "day": t.strftime("%d") if t else "",
            }
            new_stem = re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), cfg.pattern)
        new_stem = _clean(new_stem)

        files = [(p.path, True) for p in members]
        if cfg.companions:
            from facet.organizer import _companions

            for c in _companions(members[0].path, index):
                if c not in batch and not any(c == f for f, _ in files):
                    files.append((c, False))
        for path, primary in files:
            name = os.path.basename(path)
            if not name.lower().startswith(old_stem.lower()):
                continue
            suffix = name[len(old_stem):]          # ".CR2", ".jpg", ".xmp", ".CR2.xmp" …
            if cfg.lower_ext:
                suffix = suffix.lower()
            row = RenameRow(path, os.path.join(folder, new_stem + suffix), primary)
            if not new_stem:
                row.status, row.note = "invalid", "empty name"
            elif row.dst == row.src:
                row.status = "same"
            plan.rows.append(row)

    # 2) conflicts: two files to the same name, or a name taken by a file that is not renamed away
    leaving = {_norm(r.src) for r in plan.rows if r.status == "ok"}
    seen: dict[str, RenameRow] = {}
    for r in plan.rows:
        if r.status != "ok":
            continue
        k = _norm(r.dst)
        if k in seen:
            r.status = seen[k].status = "conflict"
            r.note = seen[k].note = "same new name twice"
        seen[k] = r
        if os.path.exists(r.dst) and k not in leaving and _norm(r.dst) != _norm(r.src):
            r.status, r.note = "conflict", "a file with this name already exists"
    return plan


# --------------------------------------------------------------------------- execution

def _two_phase(pairs: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], str | None]:
    """Rename src→dst for all pairs via temporary names; on failure everything is put back."""
    tag = uuid.uuid4().hex[:8]
    temps: list[tuple[str, str, str]] = []
    done: list[tuple[str, str, str]] = []
    try:
        for i, (src, dst) in enumerate(pairs):
            tmp = os.path.join(os.path.dirname(src), f".facet-rename-{tag}-{i}")
            os.rename(src, tmp)
            temps.append((src, tmp, dst))
        for src, tmp, dst in temps:
            if os.path.exists(dst):
                raise FileExistsError(dst)
            os.rename(tmp, dst)
            done.append((src, tmp, dst))
        return [(s, d) for s, _t, d in done], None
    except OSError as e:
        # roll back in two passes, so swapped names (A→B, B→A) cannot block each other
        for _src, tmp, dst in reversed(done):
            try:
                os.rename(dst, tmp)
            except OSError:
                pass
        for src, tmp, _dst in reversed(temps):
            try:
                if os.path.exists(tmp) and not os.path.exists(src):
                    os.rename(tmp, src)
            except OSError:
                pass
        return [], f"{type(e).__name__}: {e}"


def execute(plan: RenamePlan) -> tuple[list[tuple[str, str]], str | None]:
    return _two_phase([(r.src, r.dst) for r in plan.changes])


def undo(done: list[tuple[str, str]]) -> str | None:
    _, err = _two_phase([(dst, src) for src, dst in done])
    return err


__all__ = ["RenameConfig", "RenamePlan", "build_plan", "execute", "undo", "capture_time", "TOKENS",
           "SUPPORTED_EXTS", "SIDECAR_EXTS"]
