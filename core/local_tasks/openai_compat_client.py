"""Cliente para APIs compativeis com OpenAI (chat/completions)."""
from __future__ import annotations

import os
import time
from typing import Optional

import httpx

from core.local_tasks.ollama_client import Completion, LocalModelError


class OpenAICompatClient:
    """POST {base_url}/chat/completions; mesma interface do OllamaClient."""

    def __init__(
        self,
        base_url: str,
        api_key_env: str | None = None,
        timeout: float = 30.0,
        structured: str = "json_schema",
        extra: dict | None = None,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.structured = structured
        self.extra = dict(extra or {})
        self._transport = transport

    def _http(self) -> httpx.Client:
        headers = {}
        if self.api_key_env:
            key = os.environ.get(self.api_key_env, "")
            if key:
                headers["Authorization"] = f"Bearer {key}"
        return httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self._transport,
            headers=headers,
        )

    def chat(self, model: str, system: str, user: str, schema: dict) -> Completion:
        body: dict = {}
        # Merge extra first, then overwrite protected keys
        if self.extra:
            body.update({k: v for k, v in self.extra.items() if k not in ("model", "messages")})
        body["model"] = model
        body["messages"] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        body["temperature"] = 0
        if self.structured == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "strict": True, "schema": schema},
            }
        elif self.structured == "json_object":
            body["response_format"] = {"type": "json_object"}
        # "none" -> no response_format

        t0 = time.perf_counter()
        try:
            with self._http() as client:
                resp = client.post("/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise LocalModelError("timeout", type(exc).__name__) from None
        except httpx.TransportError as exc:
            raise LocalModelError("local_unavailable", type(exc).__name__) from None
        ms = int((time.perf_counter() - t0) * 1000)

        if resp.status_code >= 400:
            raise LocalModelError("local_unavailable", f"http {resp.status_code}")

        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            if not isinstance(text, str):
                raise TypeError("content is not a string")
        except (ValueError, KeyError, TypeError, IndexError):
            raise LocalModelError("local_unavailable", "response missing choices[0].message.content") from None

        usage = data.get("usage") or {}
        return Completion(
            text=text,
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            ms=ms,
            model=model,
        )

    def available(self) -> bool:
        """GET {base_url}/models com timeout de 5 s. Nunca levanta."""
        try:
            with httpx.Client(base_url=self.base_url, timeout=5.0, transport=self._transport) as client:
                resp = client.get("/models")
            return resp.status_code < 400
        except Exception:
            return False
