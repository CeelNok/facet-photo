"""OpenAI (ChatGPT vision models) as a labelling provider – Responses API, stdlib only.

One request per photo: the photo as an ``input_image`` (base64 data URL) plus all label questions; the answer is a
strict JSON object {label_id: probability 0..1}. Requests are not stored by OpenAI (``store: false``).
Docs: https://developers.openai.com/api/docs/guides/images-vision ·
      https://developers.openai.com/api/docs/guides/structured-outputs
"""

from __future__ import annotations

import base64
import json
import urllib.parse

from facet.ai import AIError, http_request
from facet.i18n import tr

API_BASE = "https://api.openai.com/v1"

SYSTEM_PROMPT = (
    "You are a careful photo-culling assistant for photographers. You get one photo and a list of yes/no "
    "questions about it. For every question return the probability (a number from 0.0 to 1.0) that the true "
    "answer is YES: 0 = certainly no, 0.5 = cannot tell, 1 = certainly yes. Judge only what is visible in the "
    "photo. In the questions, `photo` means the photo you are given."
)


class OpenAIClient:
    name = "OpenAI (ChatGPT)"
    supports_people = False  # OpenAI models do not identify or match people by their faces

    def __init__(self, api_key: str, model: str = "gpt-5.4-mini", base: str = API_BASE, timeout: float = 120) -> None:
        if not api_key:
            raise AIError(tr("No API key set for {provider}.", provider=self.name), 401)
        self.api_key = api_key
        self.model = model or "gpt-5.4-mini"
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Facet/0.6",
        }

    def ask_labels(self, jpeg: bytes, labels: list, faces: dict[str, list[bytes]]) -> tuple[dict[str, float], dict]:
        labels = [l for l in labels if not l.is_person]
        if not labels:
            return {}, {}
        lines = [f'- "{l.id}": {l.instructions()}' for l in labels]
        body = {
            "model": self.model,
            "store": False,
            "input": [
                {"role": "developer", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "input_text", "text": "Questions (answer every id):\n" + "\n".join(lines)},
                    {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode(),
                     "detail": "auto"},
                ]},
            ],
            "text": {"format": {
                "type": "json_schema",
                "name": "label_probabilities",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {l.id: {"type": "number"} for l in labels},
                    "required": [l.id for l in labels],
                    "additionalProperties": False,
                },
            }},
            "max_output_tokens": 600 + 40 * len(labels),
        }
        resp = http_request(f"{self.base}/responses", json.dumps(body).encode("utf-8"), self._headers(),
                            self.timeout)
        text = None
        for item in resp.get("output", []):
            for part in item.get("content", []) or []:
                if part.get("type") == "refusal":
                    raise AIError(tr("The AI refused to answer: {e}", e=part.get("refusal", "")))
                if part.get("type") == "output_text":
                    text = part.get("text")
        if text is None:
            reason = (resp.get("incomplete_details") or {}).get("reason") or resp.get("status") or "no output"
            raise AIError(tr("The AI returned no answer ({reason}).", reason=reason))
        try:
            data = json.loads(text)
        except ValueError:
            raise AIError(tr("The AI returned an unreadable answer.")) from None
        answers = {}
        for l in labels:
            try:
                answers[l.id] = min(1.0, max(0.0, float(data[l.id])))
            except (KeyError, TypeError, ValueError):
                pass
        usage = resp.get("usage") or {}
        return answers, {"input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0)}

    def test(self) -> str:
        """Checks the key and that the model exists (no tokens used)."""
        resp = http_request(f"{self.base}/models/{urllib.parse.quote(self.model)}", None, self._headers(),
                            30, method="GET", attempts=2)
        return str(resp.get("id", self.model))
