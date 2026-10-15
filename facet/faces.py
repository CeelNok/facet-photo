"""Local face detection, recognition and grouping (no API calls, nothing leaves the computer).

* Detection: YuNet (OpenCV zoo, MIT). Recognition: SFace (OpenCV zoo, Apache-2.0) → 128-d embeddings.
* Faces of the same person are grouped by cosine similarity; named groups become person labels.
* Scanning runs in one background thread with OpenCV limited to one thread, and the models are
  only loaded while a scan is running, so idle memory and energy use stay low.
"""

from __future__ import annotations

import io
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from facet.imaging import load_image

MODELS = Path(__file__).resolve().parent / "assets" / "models"
DETECTOR = MODELS / "face_detection_yunet_2023mar.onnx"
RECOGNIZER = MODELS / "face_recognition_sface_2021dec.onnx"
DETECT_SIDE = 1280      # long side of the image the detector sees
MIN_FACE_PX = 28        # smaller faces cannot be recognised reliably
MATCH = 0.42            # cosine similarity above which two faces are the same person
THUMB_SIDE = 160

try:
    import cv2
    import numpy as np

    cv2.setNumThreads(1)  # one core is plenty here and keeps the fans quiet
    try:
        cv2.setLogLevel(2)  # errors only
    except Exception:
        pass
    FACES_OK = DETECTOR.exists() and RECOGNIZER.exists() and hasattr(cv2, "FaceDetectorYN")
except Exception:  # pragma: no cover - optional dependency
    cv2 = None
    np = None
    FACES_OK = False


class FaceEngine:
    def __init__(self) -> None:
        self.det = cv2.FaceDetectorYN.create(str(DETECTOR), "", (320, 320), 0.8, 0.3, 5000)
        self.rec = cv2.FaceRecognizerSF.create(str(RECOGNIZER), "")

    def scan(self, path: str) -> list[dict]:
        im = load_image(path, DETECT_SIDE)
        w, h = im.size
        bgr = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
        self.det.setInputSize((w, h))
        _, found = self.det.detect(bgr)
        out = []
        for row in found if found is not None else []:
            x, y, bw, bh = (float(v) for v in row[:4])
            if bw < MIN_FACE_PX or bh < MIN_FACE_PX:
                continue
            emb = self.rec.feature(self.rec.alignCrop(bgr, row)).flatten().astype("float32")
            emb /= max(1e-6, float(np.linalg.norm(emb)))
            side = max(bw, bh) * 1.6
            cx, cy = x + bw / 2, y + bh / 2
            crop = im.crop((int(max(0, cx - side / 2)), int(max(0, cy - side / 2)),
                            int(min(w, cx + side / 2)), int(min(h, cy + side / 2))))
            crop.thumbnail((THUMB_SIDE, THUMB_SIDE))
            buf = io.BytesIO()
            crop.save(buf, "JPEG", quality=85)
            out.append({
                "box": (max(0.0, x / w), max(0.0, y / h), min(1.0, (x + bw) / w), min(1.0, (y + bh) / h)),
                "score": float(row[-1]),
                "emb": emb.tobytes(),
                "thumb": buf.getvalue(),
            })
        return out


class FaceScanJob(QObject):
    result = Signal(str, str, str, list)  # key, path, fsig, faces
    progress = Signal(int, int)
    finished = Signal()

    def __init__(self, tasks: list[tuple[str, str, str]]) -> None:
        super().__init__()
        self.tasks = tasks  # (key, path, fsig)
        self._cancel = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._run, name="faces", daemon=True).start()

    def cancel(self) -> None:
        self._cancel.set()

    def _run(self) -> None:
        engine = FaceEngine()
        total = len(self.tasks)
        for i, (key, path, fsig) in enumerate(self.tasks):
            if self._cancel.is_set():
                break
            try:
                faces = engine.scan(path)
            except Exception:
                faces = []  # unreadable file: remember it as scanned without faces
            self.result.emit(key, path, fsig, faces)
            self.progress.emit(i + 1, total)
        del engine  # release the models (~100 MB) as soon as the scan is done
        self.finished.emit()


class FaceIndex:
    """In-memory view of all detected faces for matching and grouping (main thread only)."""

    def __init__(self, db) -> None:
        self.db = db
        self.loaded = False

    def load(self) -> None:
        self.emb: dict[int, "np.ndarray"] = {}
        self.person: dict[int, str | None] = {}
        self.cluster: dict[int, int | None] = {}
        self.hidden: set[int] = set()
        for fid, _key, blob, person, cluster, hidden in self.db.all_faces():
            self.emb[fid] = np.frombuffer(blob, dtype="float32")
            self.person[fid] = person
            self.cluster[fid] = cluster
            if hidden:
                self.hidden.add(fid)
        self.next_cluster = max([c for c in self.cluster.values() if c is not None], default=0) + 1
        self._named = None
        self.loaded = True

    def ensure(self) -> None:
        if not self.loaded:
            self.load()

    # ---------------------------------------------------------------- matching

    def _named_matrix(self):
        if self._named is None:
            ids = [f for f, p in self.person.items() if p and f not in self.hidden]
            mat = np.vstack([self.emb[f] for f in ids]) if ids else None
            self._named = (ids, mat)
        return self._named

    def best_person(self, e) -> tuple[str | None, float]:
        ids, mat = self._named_matrix()
        if mat is None:
            return None, 0.0
        sims = mat @ e
        i = int(np.argmax(sims))
        return self.person[ids[i]], float(sims[i])

    def _centroids(self) -> dict[int, "np.ndarray"]:
        groups: dict[int, list] = {}
        for f, c in self.cluster.items():
            if c is not None and not self.person.get(f) and f not in self.hidden:
                groups.setdefault(c, []).append(self.emb[f])
        out = {}
        for c, vs in groups.items():
            m = np.mean(vs, axis=0)
            out[c] = m / max(1e-6, float(np.linalg.norm(m)))
        return out

    def add(self, ids: list[int], faces: list[dict]) -> None:
        """Assign newly detected faces to a known person or to a (new) group of similar faces."""
        self.ensure()
        cents = self._centroids()
        for fid, f in zip(ids, faces):
            e = np.frombuffer(f["emb"], dtype="float32")
            self.emb[fid] = e
            pid, sim = self.best_person(e)
            if pid and sim >= MATCH:
                self.person[fid] = pid
                self.cluster[fid] = None
                self.db.set_face_person([fid], pid)
                self._named = None
                continue
            best, best_sim = None, 0.0
            for c, v in cents.items():
                s = float(v @ e)
                if s > best_sim:
                    best, best_sim = c, s
            if best is None or best_sim < MATCH:
                best = self.next_cluster
                self.next_cluster += 1
                cents[best] = e
            self.person[fid] = None
            self.cluster[fid] = best
            self.db.set_face_cluster([fid], best)

    def forget_keys(self, removed_ids: list[int]) -> None:
        for fid in removed_ids:
            self.emb.pop(fid, None)
            self.person.pop(fid, None)
            self.cluster.pop(fid, None)
            self.hidden.discard(fid)
        self._named = None

    # ---------------------------------------------------------------- naming

    def name_faces(self, ids: list[int], pid: str) -> None:
        """Give faces (usually a whole group) a person, then pull in other groups that look the same."""
        self.ensure()
        clusters = {self.cluster.get(f) for f in ids} - {None}
        members = [f for f, c in self.cluster.items() if c in clusters and not self.person.get(f)]
        target = sorted(set(ids) | set(members))
        for f in target:
            self.person[f] = pid
            self.hidden.discard(f)
        self.db.set_face_person(target, pid)
        self._named = None
        # absorb unnamed groups that match this person
        pv = np.vstack([self.emb[f] for f, p in self.person.items() if p == pid])
        for c, v in self._centroids().items():
            if float(np.max(pv @ v)) >= MATCH:
                fs = [f for f, cc in self.cluster.items() if cc == c and not self.person.get(f)]
                for f in fs:
                    self.person[f] = pid
                self.db.set_face_person(fs, pid)

    def unname(self, pid: str) -> None:
        self.ensure()
        for f, p in list(self.person.items()):
            if p == pid:
                self.person[f] = None
                if self.cluster.get(f) is None:
                    self.cluster[f] = self.next_cluster
                    self.db.set_face_cluster([f], self.next_cluster)
        self.next_cluster += 1
        self._named = None

    def hide(self, ids: list[int]) -> None:
        self.ensure()
        for f in ids:
            self.hidden.add(f)
            self.person[f] = None
        self.db.hide_faces(ids)
        self._named = None


def box_iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0
