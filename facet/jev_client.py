"""Minimal TypeSafe System One (Jev) HTTP client – stdlib only.

Images are sent as multipart file parts (no base64 overhead), as recommended in
https://docs.typesafe.ai/images#over-http .
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
import uuid

from facet.i18n import tr

API_URL = "https://api.typesafe.ai/v1/systemone"
RETRY_STATUS = {429, 500, 502, 503, 504, 529}


class JevError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status

    @property
    def fatal(self) -> bool:
        """Errors that will fail for every image (bad key, no permission)."""
        return self.status in (401, 403)


class JevClient:
    def __init__(self, api_key: str, model: str = "jev-latest", url: str = API_URL, timeout: float = 90) -> None:
        if not api_key:
            raise JevError(tr("No API key set."), 401)
        self.api_key = api_key
        self.model = model or "jev-latest"
        self.url = url
        self.timeout = timeout

    # ------------------------------------------------------------------ public

    def ask_image(self, jpeg: bytes, questions: dict[str, dict],
                  extra_images: dict[str, bytes] | None = None) -> tuple[dict[str, float], dict]:
        """Ask Noul questions about one photo. Returns ({question_id: probability}, usage).

        ``questions`` maps ids to question objects. ``extra_images`` maps reference strings that
        appear inside those questions (e.g. reference faces) to JPEG bytes.
        """
        ref = f"photo-{uuid.uuid4().hex}"
        assets = {ref: {"type": "image", "part": "photo"}}
        parts = [("photo", "photo.jpg", "image/jpeg", jpeg)]
        for i, (r, data) in enumerate((extra_images or {}).items()):
            assets[r] = {"type": "image", "part": f"ref{i}"}
            parts.append((f"ref{i}", f"ref{i}.jpg", "image/jpeg", data))
        body = {
            "model": self.model,
            "state": {"photo": ref},
            "assets": assets,
            "questions": questions,
        }
        data, ctype = _multipart([("request", None, "application/json", json.dumps(body).encode("utf-8"))] + parts)
        resp = self._post(data, ctype, images=True)
        answers = {qid: float(a.get("noul", 0.0)) for qid, a in resp.get("answers", {}).items()}
        return answers, resp.get("usage", {})

    def test(self) -> str:
        """Cheap text-only request to validate the key and model."""
        body = {
            "model": self.model,
            "state": "Facet connection test.",
            "questions": {"ok": {"type": "noul", "instructions": "Is this a connection test?"}},
        }
        resp = self._post(json.dumps(body).encode("utf-8"), "application/json", images=False)
        return str(resp.get("model", self.model))

    # ------------------------------------------------------------------ internals

    def _post(self, data: bytes, content_type: str, images: bool, attempts: int = 5) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": content_type,
            "Accept": "application/json",
            "User-Agent": "Facet/0.4",
        }
        if images:
            headers["TypeSafe-Danger-Zone-Images"] = "true"
        delay = 1.0
        for attempt in range(attempts):
            req = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = _error_text(e)
                if e.code in RETRY_STATUS and attempt < attempts - 1:
                    retry_after = e.headers.get("Retry-After") if e.headers else None
                    try:
                        wait = float(retry_after) if retry_after else delay
                    except ValueError:
                        wait = delay
                    time.sleep(min(wait, 30) + random.random() * 0.5)
                    delay *= 2
                    continue
                raise JevError(f"HTTP {e.code}: {detail}", e.code) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt < attempts - 1:
                    time.sleep(delay + random.random() * 0.5)
                    delay *= 2
                    continue
                raise JevError(tr("Network error: {e}", e=getattr(e, "reason", e))) from None
        raise JevError(tr("Unknown error"))


def _error_text(e: urllib.error.HTTPError) -> str:
    try:
        raw = e.read().decode("utf-8", "replace")
    except Exception:
        return e.reason or ""
    try:
        j = json.loads(raw)
        if isinstance(j, dict):
            for k in ("detail", "message", "error"):
                if k in j:
                    v = j[k]
                    if isinstance(v, dict) and isinstance(v.get("message"), str):
                        return v["message"]
                    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    except ValueError:
        pass
    return raw[:500]


def _multipart(parts: list[tuple[str, str | None, str, bytes]]) -> tuple[bytes, str]:
    boundary = "----Facet" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, filename, ctype, payload in parts:
        disp = f'form-data; name="{name}"'
        if filename:
            disp += f'; filename="{filename}"'
        chunks.append(
            f"--{boundary}\r\nContent-Disposition: {disp}\r\nContent-Type: {ctype}\r\n\r\n".encode("ascii")
        )
        chunks.append(payload)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"
