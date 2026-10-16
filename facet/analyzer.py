"""Background AI analysis: one request per photo (Jev or OpenAI), all labels asked in that single request."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QObject, Signal

from facet.i18n import tr
from facet.imaging import prepare_for_ai
from facet.ai import AIError
from facet.storage import faces_dir


class AnalyzeJob(QObject):
    # path_key, fsig, {label_id: (value, qhash)}
    result = Signal(str, str, dict)
    failed = Signal(str, str)
    progress = Signal(int, int, int)  # done, total, input tokens so far
    finished = Signal(bool, str)      # cancelled, message

    def __init__(self, client, tasks: list[tuple[str, str, str, list]], max_side: int, concurrency: int):
        """tasks: (file path, path key, fsig, [Label, ...] still missing for that photo)."""
        super().__init__()
        self.client = client
        self.tasks = tasks
        self.max_side = max_side
        self.concurrency = max(1, min(16, concurrency))
        self._cancel = threading.Event()
        self._faces: dict[str, bytes] = {}  # reference face crops, read from disk once per job
        self._faces_lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._run, name="jev-analyze", daemon=True).start()

    def cancel(self) -> None:
        self._cancel.set()

    def _face(self, name: str) -> bytes | None:
        with self._faces_lock:
            if name not in self._faces:
                try:
                    self._faces[name] = (faces_dir() / name).read_bytes()
                except OSError:
                    self._faces[name] = b""
            return self._faces[name] or None

    def _one(self, task):
        path, key, fsig, labels = task
        if self._cancel.is_set():
            return None
        jpeg = prepare_for_ai(path, self.max_side)  # decoded inside the worker: memory bounded by concurrency
        if self._cancel.is_set():
            return None
        faces = {l.id: [d for d in (self._face(n) for n in l.ref_faces()) if d] for l in labels if l.is_person}
        answers, usage = self.client.ask_labels(jpeg, labels, faces)
        if not answers:
            return key, fsig, {}, 0
        values = {l.id: (answers[l.id], l.qhash) for l in labels if l.id in answers}
        return key, fsig, values, int(usage.get("input_tokens", 0) or 0)

    def _run(self) -> None:
        total = len(self.tasks)
        done = tokens = errors = 0
        fatal: str | None = None
        with ThreadPoolExecutor(max_workers=self.concurrency, thread_name_prefix="jev") as pool:
            futures = {pool.submit(self._one, t): t for t in self.tasks}
            for fut in as_completed(futures):
                task = futures[fut]
                done += 1
                try:
                    res = fut.result()
                    if res:
                        key, fsig, values, used = res
                        tokens += used
                        if values:
                            self.result.emit(key, fsig, values)
                except AIError as e:
                    errors += 1
                    self.failed.emit(task[1], str(e))
                    if e.fatal:
                        fatal = str(e)
                        self._cancel.set()
                except Exception as e:  # decode errors etc.
                    errors += 1
                    self.failed.emit(task[1], f"{type(e).__name__}: {e}")
                self.progress.emit(done, total, tokens)
                if self._cancel.is_set():
                    for f in futures:
                        f.cancel()
        if fatal:
            self.finished.emit(True, tr("Analysis stopped: {e}", e=fatal))
        elif self._cancel.is_set():
            self.finished.emit(True, tr("Analysis cancelled."))
        else:
            msg = tr("Analysis finished: {n} photos", n=total - errors)
            if errors:
                msg += tr(", {n} errors", n=errors)
            self.finished.emit(False, msg + tr(" · {t} input tokens", t=f"{tokens:,}".replace(",", " ")))
