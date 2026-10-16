"""Persistent state: settings, label definitions, API key, data migration and the score database."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

from facet import APP_NAME, LEGACY_NAME
from facet.i18n import language, tr



def data_dir() -> Path:
    p = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_dir() -> Path:
    p = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
    p.mkdir(parents=True, exist_ok=True)
    return p


def faces_dir() -> Path:
    p = data_dir() / "faces"
    p.mkdir(parents=True, exist_ok=True)
    return p


def norm_dir(path: str) -> str:
    """Comparable folder path: absolute, case-folded on Windows, one Unicode form (macOS may store “á” as a+´)."""
    return unicodedata.normalize("NFC", os.path.normcase(os.path.abspath(path))).rstrip("\\/")


def path_key(path: str) -> str:
    """Canonical key for a file path (case-insensitive on Windows)."""
    return os.path.normcase(os.path.abspath(path))


# --------------------------------------------------------------------------- settings

DEFAULTS = {
    "model": "jev-latest",
    "concurrency": 4,
    "ai_max_side": 1024,
    "thumb_threads": 2,
    "grid_size": 170,
    "recursive": False,
    "last_folder": "",
    "language": "",  # "" = follow the operating system
    "auto_faces": False,  # detect faces automatically when a folder opens (opt-in)
    "provider": "jev",  # AI used for labels: "jev" | "openai"
    "openai_model": "gpt-5.4-mini",
}

KEY_FILES = {"jev": "api_key", "openai": "openai_api_key"}


class Settings:
    def __init__(self) -> None:
        self._q = QSettings()
        if not self._q.contains("faces_optin_v1"):  # 0.5: face scanning became opt-in
            self._q.setValue("auto_faces", False)
            self._q.setValue("faces_optin_v1", True)

    def get(self, key: str):
        default = DEFAULTS.get(key)
        value = self._q.value(key, default)
        if isinstance(default, bool):
            return value in (True, "true", "1", 1)
        if isinstance(default, int):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
        return value

    def set(self, key: str, value) -> None:
        self._q.setValue(key, value)

    # The API key is kept in a private file in the app's data folder (readable only by the current user).
    # The OS keychain is deliberately not used: it shows password prompts for unsigned / rebuilt apps.
    def _key_file(self, provider: str = "jev") -> Path:
        return data_dir() / KEY_FILES.get(provider, "api_key")

    def api_key(self, provider: str | None = None) -> str:
        provider = provider or self.get("provider") or "jev"
        try:
            return self._key_file(provider).read_text("utf-8").strip()
        except OSError:
            return str(self._q.value("api_key_fallback", "") or "") if provider == "jev" else ""

    def set_api_key(self, value: str, provider: str = "jev") -> None:
        value = value.strip()
        f = self._key_file(provider)
        if not value:
            f.unlink(missing_ok=True)
        else:
            fd = os.open(str(f), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as h:
                h.write(value)
            try:
                os.chmod(f, 0o600)
            except OSError:
                pass
        self._q.remove("api_key_fallback")


def migrate_legacy() -> None:
    """One-time copy of labels, database and settings from the app's previous name (no keychain access)."""
    new = data_dir()
    if (new / "labels.json").exists():
        return
    old = Path(*[LEGACY_NAME if part == APP_NAME else part for part in new.parts])
    if old != new and (old / "labels.json").exists():
        shutil.copy2(old / "labels.json", new / "labels.json")
        for suffix in ("", "-wal", "-shm"):
            src = old / f"photosieve.db{suffix}"
            if src.exists():
                shutil.copy2(src, new / f"facet.db{suffix}")
    old_settings = QSettings(LEGACY_NAME, LEGACY_NAME)
    new_settings = QSettings()
    for key in ("model", "concurrency", "ai_max_side", "thumb_threads", "grid_size", "last_source",
                "api_key_fallback"):
        if old_settings.contains(key) and not new_settings.contains(key):
            new_settings.setValue(key, old_settings.value(key))


# --------------------------------------------------------------------------- labels

PALETTE = ["#e5484d", "#f5a524", "#30a46c", "#0091ff", "#8e4ec6", "#d6409f", "#12a594", "#978365", "#6e56cf"]
MAX_REF_FACES = 6  # most recent reference faces sent per person (each one costs image tokens)

PERSON_QUESTION = (
    "The pictures in `reference_faces` all show the same person. "
    "Is that same person visible anywhere in `photo`? They may appear small, at a different angle, "
    "with different lighting, hairstyle or expression."
)
PERSON_CRITERIA = {
    "true": "The same individual shown in `reference_faces` appears in `photo`.",
    "false": "That individual does not appear in `photo` (other people may appear).",
}


@dataclass
class Label:
    name: str
    question: str
    threshold: float = 0.5
    color: str = "#0091ff"
    id: str = field(default_factory=lambda: "l" + uuid.uuid4().hex[:10])
    kind: str = "question"  # "question" | "person"
    faces: list[str] = field(default_factory=list)  # reference face crops (file names in faces_dir())
    scope: str | None = None  # "" = every folder · "folder" = only in ``folders`` · None = not yet migrated
    builtin: str = ""         # key of a built-in label (always present, fixed question, localized name)
    folders: list[str] = field(default_factory=list)  # for scope "folder": the folders it belongs to

    @property
    def folder_only(self) -> bool:
        return self.scope == "folder"

    def applies(self, path: str) -> bool:
        """Is this label used for the photo at ``path``? Built-ins and people apply everywhere."""
        if not self.folder_only:
            return True
        p = norm_dir(path)
        return any(p.startswith(norm_dir(f) + os.sep) for f in self.folders)

    @property
    def is_person(self) -> bool:
        return self.kind == "person"

    @property
    def qhash(self) -> str:
        """Hash of what is sent to the model; a changed question or new reference face invalidates old scores."""
        payload = self.instructions()
        if self.is_person:
            payload += "|" + ",".join(self.ref_faces())
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]

    def instructions(self) -> str:
        if self.is_person:
            return PERSON_QUESTION
        q = self.question.strip()
        if not q:
            return f"Does `photo` show: {self.name}?"
        if "`photo`" in q:
            return q
        # Free text (a description, or a question in any language) is turned into a clear yes/no question
        # about the photo – without this, Jev does not know which image the text refers to.
        return f"Does `photo` match this description? Description: {q}"

    def ref_faces(self) -> list[str]:
        return self.faces[-MAX_REF_FACES:]

    def api_question(self, face_refs: list[str] | None = None) -> dict:
        """The Noul question sent to Jev. Person labels carry their reference face images."""
        if self.is_person:
            return {
                "type": "noul",
                "instructions": {"reference_faces": face_refs or [], "question": PERSON_QUESTION},
                "criteria": PERSON_CRITERIA,
            }
        return {"type": "noul", "instructions": self.instructions()}


# Built-in labels: present in every folder, with a fixed question; the name follows the UI language.
# (key, English name, question, threshold, colour)
BUILTINS = [
    ("blurry", "Blurry", "Is `photo` blurry, out of focus or affected by motion blur?", 0.6, "#e5484d"),
    ("smiling", "Smiling", "Is at least one person in `photo` clearly smiling?", 0.5, "#f5a524"),
    ("eyes_closed", "Eyes closed", "Does a person who is the main subject of `photo` have their eyes closed?", 0.6,
     "#0091ff"),
    ("overexposed", "Overexposed",
     "Is `photo` overexposed – too bright, with blown-out highlights or washed-out areas that lost detail?", 0.6,
     "#d6409f"),
    ("underexposed", "Underexposed",
     "Is `photo` underexposed – too dark, with murky shadows or a subject that is hard to see?", 0.6, "#6e56cf"),
]
BUILTIN_KEYS = [b[0] for b in BUILTINS]


def ensure_builtins(labels: list[Label]) -> list[Label]:
    """Built-ins first, in a fixed order, always present. Older default labels with the same question are
    adopted (their AI results are kept)."""
    rest = list(labels)
    out = []
    for key, name, question, thr, color in BUILTINS:
        lab = next((l for l in rest if l.builtin == key), None)
        if lab is None:
            lab = next((l for l in rest if not l.builtin and l.kind == "question" and l.question == question), None)
        if lab is None:
            lab = Label(name, question, thr, color, id="b_" + key)
        rest.remove(lab) if lab in rest else None
        lab.builtin = key
        lab.kind = "question"
        lab.question = question
        lab.scope = ""
        lab.name = tr(name)
        out.append(lab)
    return out + rest


def default_labels() -> list[Label]:
    return ensure_builtins([])


def load_labels() -> list[Label]:
    f = data_dir() / "labels.json"
    if not f.exists():
        labels = default_labels()
        save_labels(labels)
        return labels
    try:
        raw = json.loads(f.read_text("utf-8"))
        labels = [Label(**{k: v for k, v in item.items() if k in Label.__dataclass_fields__}) for item in raw]
    except Exception:
        labels = []
    for l in labels:
        if l.kind == "person":
            l.scope = ""  # people are recognised across the whole library
        elif l.scope not in (None, "", "folder"):  # 0.4 stored a single folder path in ``scope``
            l.folders = l.folders or [l.scope]
            l.scope = "folder"
    return ensure_builtins(labels)


def save_labels(labels: list[Label]) -> None:
    f = data_dir() / "labels.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps([asdict(l) for l in labels], ensure_ascii=False, indent=2), "utf-8")
    os.replace(tmp, f)


# --------------------------------------------------------------------------- score DB


class ScoreDB:
    """AI scores and manual overrides, keyed by canonical file path.

    Every AI score remembers the question hash and the file signature it was computed for,
    so edited labels or changed files are re-analysed instead of trusting stale results.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (data_dir() / "facet.db")
        self.con = sqlite3.connect(str(self.path))
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=NORMAL")
        self.con.executescript(
            """
            CREATE TABLE IF NOT EXISTS scores(
                path TEXT NOT NULL, label_id TEXT NOT NULL, value REAL NOT NULL,
                qhash TEXT NOT NULL, fsig TEXT NOT NULL, ts REAL,
                PRIMARY KEY(path, label_id));
            CREATE TABLE IF NOT EXISTS manual(
                path TEXT NOT NULL, label_id TEXT NOT NULL, value INTEGER NOT NULL,
                PRIMARY KEY(path, label_id));
            CREATE TABLE IF NOT EXISTS folders(
                path TEXT PRIMARY KEY, added REAL, opened REAL, count INTEGER DEFAULT 0,
                recursive INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS collections(
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created REAL);
            CREATE TABLE IF NOT EXISTS collection_items(
                cid INTEGER NOT NULL, key TEXT NOT NULL, path TEXT NOT NULL, added REAL,
                PRIMARY KEY(cid, key));
            CREATE TABLE IF NOT EXISTS recent(key TEXT PRIMARY KEY, path TEXT NOT NULL, ts REAL);
            CREATE TABLE IF NOT EXISTS faces(
                id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, path TEXT NOT NULL, fsig TEXT NOT NULL,
                x0 REAL, y0 REAL, x1 REAL, y1 REAL, score REAL, emb BLOB NOT NULL, thumb BLOB,
                person TEXT, cluster INTEGER, hidden INTEGER DEFAULT 0);
            CREATE INDEX IF NOT EXISTS faces_key ON faces(key);
            CREATE INDEX IF NOT EXISTS faces_person ON faces(person);
            CREATE TABLE IF NOT EXISTS face_scans(key TEXT PRIMARY KEY, path TEXT NOT NULL, fsig TEXT NOT NULL);
            """
        )
        self._dirty = False

    def close(self) -> None:
        self.commit()
        self.con.close()

    def commit(self) -> None:
        if self._dirty:
            self.con.commit()
            self._dirty = False

    def load_for(self, keys: set[str]) -> tuple[dict, dict]:
        """Return ({key: [(label_id, value, qhash, fsig)]}, {key: {label_id: value}}) for the given keys."""
        scores: dict[str, list] = {}
        manual: dict[str, dict] = {}
        if not keys:
            return scores, manual
        # Load by common directory prefix, then filter in Python: one indexed range scan.
        try:
            prefix = os.path.commonpath(list(keys)) if len(keys) > 1 else next(iter(keys))
        except ValueError:  # e.g. paths on different Windows drives
            prefix = ""
        lo, hi = prefix, prefix + "￿"
        for p, lid, v, qh, fs in self.con.execute(
            "SELECT path,label_id,value,qhash,fsig FROM scores WHERE path>=? AND path<?", (lo, hi)
        ):
            if p in keys:
                scores.setdefault(p, []).append((lid, v, qh, fs))
        for p, lid, v in self.con.execute(
            "SELECT path,label_id,value FROM manual WHERE path>=? AND path<?", (lo, hi)
        ):
            if p in keys:
                manual.setdefault(p, {})[lid] = v
        return scores, manual

    def put_scores(self, key: str, fsig: str, values: dict[str, tuple[float, str]]) -> None:
        now = time.time()
        self.con.executemany(
            "INSERT OR REPLACE INTO scores(path,label_id,value,qhash,fsig,ts) VALUES(?,?,?,?,?,?)",
            [(key, lid, v, qh, fsig, now) for lid, (v, qh) in values.items()],
        )
        self._dirty = True

    def set_manual(self, key: str, label_id: str, value: int | None) -> None:
        if value is None:
            self.con.execute("DELETE FROM manual WHERE path=? AND label_id=?", (key, label_id))
        else:
            self.con.execute(
                "INSERT OR REPLACE INTO manual(path,label_id,value) VALUES(?,?,?)", (key, label_id, int(value))
            )
        self._dirty = True

    def set_manual_many(self, keys: list[str], label_id: str, value: int | None) -> None:
        if value is None:
            self.con.executemany("DELETE FROM manual WHERE path=? AND label_id=?", [(k, label_id) for k in keys])
        else:
            self.con.executemany("INSERT OR REPLACE INTO manual(path,label_id,value) VALUES(?,?,?)",
                                 [(k, label_id, int(value)) for k in keys])
        self._dirty = True

    def delete_scores(self, keys: list[str], label_ids: list[str]) -> None:
        self.con.executemany("DELETE FROM scores WHERE path=? AND label_id=?",
                             [(k, lid) for k in keys for lid in label_ids])
        self._dirty = True

    def rename(self, old: str, new: str, new_path: str | None = None) -> None:
        """A file moved: scores, overrides, collection membership and history follow it."""
        for table in ("scores", "manual"):
            self.con.execute(f"DELETE FROM {table} WHERE path=?", (new,))
            self.con.execute(f"UPDATE {table} SET path=? WHERE path=?", (new, old))
        self.con.execute("DELETE FROM face_scans WHERE key=?", (new,))
        self.con.execute("DELETE FROM faces WHERE key=?", (new,))
        self.con.execute("UPDATE face_scans SET key=?, path=COALESCE(?, path) WHERE key=?", (new, new_path, old))
        self.con.execute("UPDATE faces SET key=?, path=COALESCE(?, path) WHERE key=?", (new, new_path, old))
        if new_path:
            self.con.execute("DELETE FROM collection_items WHERE key=? AND cid IN "
                             "(SELECT cid FROM collection_items WHERE key=?)", (new, old))
            self.con.execute("UPDATE collection_items SET key=?, path=? WHERE key=?", (new, new_path, old))
            self.con.execute("DELETE FROM recent WHERE key=?", (new,))
            self.con.execute("UPDATE recent SET key=?, path=? WHERE key=?", (new, new_path, old))
        self._dirty = True

    def duplicate(self, src: str, dst: str) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO scores SELECT ?,label_id,value,qhash,fsig,ts FROM scores WHERE path=?", (dst, src)
        )
        self.con.execute("INSERT OR REPLACE INTO manual SELECT ?,label_id,value FROM manual WHERE path=?", (dst, src))
        self._dirty = True

    def remove(self, key: str) -> None:
        for sql in ("DELETE FROM scores WHERE path=?", "DELETE FROM manual WHERE path=?",
                    "DELETE FROM collection_items WHERE key=?", "DELETE FROM recent WHERE key=?",
                    "DELETE FROM faces WHERE key=?", "DELETE FROM face_scans WHERE key=?"):
            self.con.execute(sql, (key,))
        self._dirty = True

    # ------------------------------------------------------------------ library: folders

    def folders(self) -> list[tuple[str, int, bool]]:
        rows = self.con.execute("SELECT path, count, recursive FROM folders ORDER BY added").fetchall()
        return [(p, c or 0, bool(r)) for p, c, r in rows]

    def add_folder(self, path: str) -> None:
        now = time.time()
        self.con.execute("INSERT OR IGNORE INTO folders(path, added, opened) VALUES(?,?,?)", (path, now, now))
        self.con.commit()

    def update_folder(self, path: str, count: int | None = None, recursive: bool | None = None) -> None:
        self.con.execute("UPDATE folders SET opened=? WHERE path=?", (time.time(), path))
        if count is not None:
            self.con.execute("UPDATE folders SET count=? WHERE path=?", (count, path))
        if recursive is not None:
            self.con.execute("UPDATE folders SET recursive=? WHERE path=?", (int(recursive), path))
        self._dirty = True

    def folder_recursive(self, path: str) -> bool:
        row = self.con.execute("SELECT recursive FROM folders WHERE path=?", (path,)).fetchone()
        return bool(row and row[0])

    def remove_folder(self, path: str) -> None:
        self.con.execute("DELETE FROM folders WHERE path=?", (path,))
        self.con.commit()

    # ------------------------------------------------------------------ library: collections

    def collections(self) -> list[tuple[int, str, int]]:
        return self.con.execute(
            "SELECT c.id, c.name, (SELECT COUNT(*) FROM collection_items i WHERE i.cid=c.id) "
            "FROM collections c ORDER BY c.name COLLATE NOCASE").fetchall()

    def create_collection(self, name: str) -> int:
        cur = self.con.execute("INSERT INTO collections(name, created) VALUES(?,?)", (name, time.time()))
        self.con.commit()
        return int(cur.lastrowid)

    def rename_collection(self, cid: int, name: str) -> None:
        self.con.execute("UPDATE collections SET name=? WHERE id=?", (name, cid))
        self.con.commit()

    def delete_collection(self, cid: int) -> None:
        self.con.execute("DELETE FROM collection_items WHERE cid=?", (cid,))
        self.con.execute("DELETE FROM collections WHERE id=?", (cid,))
        self.con.commit()

    def collection_name(self, cid: int) -> str:
        row = self.con.execute("SELECT name FROM collections WHERE id=?", (cid,)).fetchone()
        return row[0] if row else ""

    def collection_paths(self, cid: int) -> list[str]:
        return [r[0] for r in self.con.execute(
            "SELECT path FROM collection_items WHERE cid=? ORDER BY added", (cid,))]

    def add_to_collection(self, cid: int, paths: list[str]) -> int:
        now = time.time()
        before = self.con.total_changes
        self.con.executemany("INSERT OR IGNORE INTO collection_items(cid, key, path, added) VALUES(?,?,?,?)",
                             [(cid, path_key(p), p, now + i * 1e-6) for i, p in enumerate(paths)])
        self.con.commit()
        return self.con.total_changes - before

    def remove_from_collection(self, cid: int, keys: list[str]) -> None:
        self.con.executemany("DELETE FROM collection_items WHERE cid=? AND key=?", [(cid, k) for k in keys])
        self.con.commit()

    # ------------------------------------------------------------------ library: recently opened

    RECENT_LIMIT = 300

    def add_recent(self, path: str) -> None:
        self.con.execute("INSERT OR REPLACE INTO recent(key, path, ts) VALUES(?,?,?)",
                         (path_key(path), path, time.time()))
        self.con.execute("DELETE FROM recent WHERE key NOT IN (SELECT key FROM recent ORDER BY ts DESC LIMIT ?)",
                         (self.RECENT_LIMIT,))
        self._dirty = True

    def recent_paths(self) -> list[str]:
        return [r[0] for r in self.con.execute("SELECT path FROM recent ORDER BY ts DESC")]

    def clear_recent(self) -> None:
        self.con.execute("DELETE FROM recent")
        self.con.commit()

    # ------------------------------------------------------------------ faces (local detection)

    def scanned(self, keys: set[str]) -> dict[str, str]:
        """{key: fsig} of photos whose faces were already detected."""
        out = {}
        for k, fs in self.con.execute("SELECT key, fsig FROM face_scans"):
            if k in keys:
                out[k] = fs
        return out

    def store_faces(self, key: str, path: str, fsig: str, faces: list[dict]) -> list[int]:
        self.con.execute("DELETE FROM faces WHERE key=?", (key,))
        ids = []
        for f in faces:
            cur = self.con.execute(
                "INSERT INTO faces(key,path,fsig,x0,y0,x1,y1,score,emb,thumb) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (key, path, fsig, *f["box"], f["score"], f["emb"], f["thumb"]))
            ids.append(int(cur.lastrowid))
        self.con.execute("INSERT OR REPLACE INTO face_scans(key, path, fsig) VALUES(?,?,?)", (key, path, fsig))
        self._dirty = True
        return ids

    def all_faces(self) -> list[tuple]:
        """(id, key, emb, person, cluster, hidden) for every detected face."""
        return self.con.execute("SELECT id, key, emb, person, cluster, hidden FROM faces").fetchall()

    def face_rows(self, keys: set[str]) -> list[tuple]:
        """(id, key, person, cluster, hidden, score) for faces on the given photos."""
        return [r for r in self.con.execute("SELECT id, key, person, cluster, hidden, score FROM faces")
                if r[1] in keys]

    def face_detail(self, face_id: int):
        return self.con.execute("SELECT path, x0, y0, x1, y1, thumb, key FROM faces WHERE id=?",
                                (face_id,)).fetchone()

    def faces_on(self, key: str) -> list[tuple]:
        return self.con.execute("SELECT id, x0, y0, x1, y1, person, cluster FROM faces WHERE key=?",
                                (key,)).fetchall()

    def set_face_person(self, ids: list[int], person: str | None) -> None:
        self.con.executemany("UPDATE faces SET person=? WHERE id=?", [(person, i) for i in ids])
        self._dirty = True

    def set_face_cluster(self, ids: list[int], cluster: int) -> None:
        self.con.executemany("UPDATE faces SET cluster=? WHERE id=?", [(cluster, i) for i in ids])
        self._dirty = True

    def hide_faces(self, ids: list[int]) -> None:
        self.con.executemany("UPDATE faces SET hidden=1, person=NULL WHERE id=?", [(i,) for i in ids])
        self._dirty = True

    def refresh_person_scores(self, person_ids: list[str], keys: list[str] | None = None) -> None:
        """Presence of each person on every face-scanned photo, stored as a local 0/1 score."""
        now = time.time()
        where = " WHERE 1"  # SQLite needs a WHERE before ON CONFLICT in INSERT … SELECT
        args: list = []
        if keys is not None:
            if not keys:
                return
            where = f" WHERE s.key IN ({','.join('?' * len(keys))})"
            args = list(keys)
        for pid in person_ids:
            # A local “found” always wins; a local “not found” never overwrites a Jev answer (Jev may have
            # found the person from the side or far away, where the local recogniser gives up).
            self.con.execute(
                "INSERT INTO scores(path,label_id,value,qhash,fsig,ts) "
                "SELECT s.key, ?, CASE WHEN EXISTS(SELECT 1 FROM faces f WHERE f.key=s.key AND f.person=? "
                "AND f.hidden=0) THEN 1.0 ELSE 0.0 END, 'local', s.fsig, ? FROM face_scans s" + where +
                " ON CONFLICT(path, label_id) DO UPDATE SET value=excluded.value, qhash='local', "
                "fsig=excluded.fsig, ts=excluded.ts WHERE excluded.value = 1.0 OR scores.qhash = 'local' "
                "OR scores.fsig <> excluded.fsig",
                [pid, pid, now] + args)
        self._dirty = True

    def drop_label(self, label_id: str) -> None:
        self.con.execute("UPDATE faces SET person=NULL WHERE person=?", (label_id,))
        self.con.execute("DELETE FROM scores WHERE label_id=?", (label_id,))
        self.con.execute("DELETE FROM manual WHERE label_id=?", (label_id,))
        self._dirty = True


__all__ = [
    "APP_NAME", "Settings", "Label", "ScoreDB", "load_labels", "save_labels", "default_labels",
    "data_dir", "cache_dir", "faces_dir", "path_key", "PALETTE", "migrate_legacy",
]
