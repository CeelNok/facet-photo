"""AI provider layer: every provider answers yes/no label questions about one photo with probabilities.

Providers:
* ``jev``    – TypeSafe Jev (System One): calibrated yes/no probabilities, can compare reference faces.
* ``openai`` – OpenAI (ChatGPT models with vision) via the Responses API and a strict JSON schema.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request

from facet.i18n import tr

PROVIDERS = {"jev": "TypeSafe Jev", "openai": "OpenAI (ChatGPT)"}
DEFAULT_MODELS = {"jev": "jev-latest", "openai": "gpt-5.4-mini"}
KEY_URLS = {"jev": "https://console.typesafe.ai/keys", "openai": "https://platform.openai.com/api-keys"}
RETRY_STATUS = {429, 500, 502, 503, 504, 529}


class AIError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status

    @property
    def fatal(self) -> bool:
        """Errors that will fail for every image (bad key, no permission, no credit)."""
        return self.status in (401, 402, 403)


def http_request(url: str, data: bytes | None, headers: dict, timeout: float, method: str = "POST",
                 attempts: int = 5) -> dict:
    """JSON request with exponential back-off on rate limits / overload / network errors."""
    delay = 1.0
    for attempt in range(attempts):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = error_text(e)
            if e.code in RETRY_STATUS and attempt < attempts - 1:
                retry_after = e.headers.get("Retry-After") if e.headers else None
                try:
                    wait = float(retry_after) if retry_after else delay
                except ValueError:
                    wait = delay
                time.sleep(min(wait, 30) + random.random() * 0.5)
                delay *= 2
                continue
            raise AIError(f"HTTP {e.code}: {detail}", e.code) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt < attempts - 1:
                time.sleep(delay + random.random() * 0.5)
                delay *= 2
                continue
            raise AIError(tr("Network error: {e}", e=getattr(e, "reason", e))) from None
    raise AIError(tr("Unknown error"))


def error_text(e: urllib.error.HTTPError) -> str:
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


def make_client(settings, provider: str | None = None):
    """Client for the provider chosen in Settings (raises AIError when its API key is missing)."""
    provider = provider or settings.get("provider") or "jev"
    key = settings.api_key(provider)
    if provider == "openai":
        from facet.openai_client import OpenAIClient

        return OpenAIClient(key, settings.get("openai_model") or DEFAULT_MODELS["openai"])
    from facet.jev_client import JevClient

    return JevClient(key, settings.get("model") or DEFAULT_MODELS["jev"])


def provider_name(settings) -> str:
    return PROVIDERS.get(settings.get("provider") or "jev", PROVIDERS["jev"])
