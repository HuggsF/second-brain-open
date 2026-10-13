"""Cliente mínimo do Ollama: chat com saída presa a um JSON schema."""
from dataclasses import dataclass
from typing import Optional

import httpx

from config import settings


class LocalModelError(Exception):
    """Falha do modelo local. `reason` é "local_unavailable" ou "timeout".

    A mensagem nunca carrega o conteúdo da requisição.
    """

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass
class Completion:
    text: str
    tokens_in: int
    tokens_out: int
    ms: int
    model: str


class OllamaClient:
    def __init__(
        self,
        base_url: str = settings.ollama_url,
        timeout: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport

    def _http(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=self.timeout, transport=self._transport)

    def chat(self, model: str, system: str, user: str, schema: dict) -> Completion:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0},
        }
        try:
            with self._http() as client:
                resp = client.post("/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise LocalModelError("timeout", type(exc).__name__) from None
        except httpx.TransportError as exc:
            raise LocalModelError("local_unavailable", type(exc).__name__) from None
        if resp.status_code >= 400:
            raise LocalModelError("local_unavailable", f"http {resp.status_code}")
        try:
            data = resp.json()
            text = data["message"]["content"]
            if not isinstance(text, str):
                raise TypeError("content")
        except (ValueError, KeyError, TypeError):
            raise LocalModelError("local_unavailable", "resposta sem message.content") from None
        return Completion(
            text=text,
            tokens_in=int(data.get("prompt_eval_count") or 0),
            tokens_out=int(data.get("eval_count") or 0),
            ms=int(data.get("total_duration") or 0) // 1_000_000,
            model=model,
        )

    def available(self, model: str) -> bool:
        try:
            with self._http() as client:
                resp = client.get("/api/tags")
            if resp.status_code >= 400:
                return False
            names = {m.get("name") for m in resp.json().get("models", [])}
        except Exception:
            return False
        return model in names or f"{model}:latest" in names
