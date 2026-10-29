"""TypeSafe System One (Jev) HTTP client – stdlib only.

Images are sent as multipart file parts (no base64 overhead), as recommended in
https://docs.typesafe.ai/images#over-http .
"""

from __future__ import annotations

import json
import uuid

from facet.ai import AIError, http_request
from facet.i18n import tr

API_URL = "https://api.typesafe.ai/v1/systemone"

JevError = AIError  # backwards-compatible name


class JevClient:
    name = "TypeSafe Jev"
    supports_people = True  # can compare reference faces with the photo

    def __init__(self, api_key: str, model: str = "jev-latest", url: str = API_URL, timeout: float = 90) -> None:
        if not api_key:
            raise AIError(tr("No API key set for {provider}.", provider=self.name), 401)
        self.api_key = api_key
        self.model = model or "jev-latest"
        self.url = url
        self.timeout = timeout

    # ------------------------------------------------------------------ provider interface

    def ask_labels(self, jpeg: bytes, labels: list, faces: dict[str, list[bytes]]) -> tuple[dict[str, float], dict]:
        """Probability that each label applies to the photo. ``faces`` holds reference faces per person label."""
        questions: dict[str, dict] = {}
        extra: dict[str, bytes] = {}
        for l in labels:
            refs = []
            for data in faces.get(l.id, []) if l.is_person else []:
                ref = f"face-{uuid.uuid4().hex}"
                extra[ref] = data
                refs.append(ref)
            if l.is_person and not refs:
                continue  # a person without a readable reference face cannot be asked
            questions[l.id] = l.api_question(refs)
        if not questions:
            return {}, {}
        return self.ask_image(jpeg, questions, extra)

    def test(self) -> str:
        """Cheap text-only request to validate the key and model."""
        body = {
            "model": self.model,
            "state": "Facet connection test.",
            "questions": {"ok": {"type": "noul", "instructions": "Is this a connection test?"}},
        }
        resp = self._post(json.dumps(body).encode("utf-8"), "application/json", images=False)
        return str(resp.get("model", self.model))

    # ------------------------------------------------------------------ Jev specifics

    def ask_image(self, jpeg: bytes, questions: dict[str, dict],
                  extra_images: dict[str, bytes] | None = None) -> tuple[dict[str, float], dict]:
        """Ask Noul questions about one photo. ``extra_images`` maps references used in the questions to JPEGs."""
        ref = f"photo-{uuid.uuid4().hex}"
        assets = {ref: {"type": "image", "part": "photo"}}
        parts = [("photo", "photo.jpg", "image/jpeg", jpeg)]
        for i, (r, data) in enumerate((extra_images or {}).items()):
            assets[r] = {"type": "image", "part": f"ref{i}"}
            parts.append((f"ref{i}", f"ref{i}.jpg", "image/jpeg", data))
        body = {"model": self.model, "state": {"photo": ref}, "assets": assets, "questions": questions}
        data, ctype = _multipart([("request", None, "application/json", json.dumps(body).encode("utf-8"))] + parts)
        resp = self._post(data, ctype, images=True)
        answers = {qid: float(a.get("noul", 0.0)) for qid, a in resp.get("answers", {}).items()}
        return answers, resp.get("usage", {})

    def _post(self, data: bytes, content_type: str, images: bool) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": content_type,
            "Accept": "application/json",
            "User-Agent": "Facet/0.6",
        }
        if images:
            headers["TypeSafe-Danger-Zone-Images"] = "true"
        return http_request(self.url, data, headers, self.timeout)


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
