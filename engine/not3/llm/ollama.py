"""Ollama client.

Only the pieces the pipeline needs: a structured (JSON-schema-constrained)
chat call, a plain chat call, and embeddings. Kept deliberately small so
swapping in another local runtime later is a single-file change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


class LlmError(RuntimeError):
    pass


class LlmUnavailable(LlmError):
    """Ollama is not running or not reachable."""


class LlmTruncated(LlmError):
    """The model ran out of context before finishing.

    Ollama silently caps generation at `num_ctx`, which defaults to 4096 no
    matter how much context the model itself supports. A prompt near that
    limit leaves no room to answer, and the reply arrives as valid-looking
    JSON cut off mid-token. The give-away is `done_reason == "length"`.
    """


# Roughly 3.2 characters per token for English transcripts plus JSON. Slightly
# pessimistic on purpose: under-estimating the prompt is what causes the
# failure this constant exists to avoid.
CHARS_PER_TOKEN = 3.2

# Bounds for the context window we request. The floor keeps small prompts from
# asking for a pointlessly small window; the ceiling keeps the KV cache from
# evicting the model itself out of VRAM on an 8 GB card.
MIN_NUM_CTX = 4096
MAX_NUM_CTX = 32768


def estimate_tokens(messages: list[dict[str, str]]) -> int:
    chars = sum(len(m.get("content", "")) for m in messages)
    return int(chars / CHARS_PER_TOKEN) + 16 * len(messages)


def plan_num_ctx(messages: list[dict[str, str]], output_tokens: int, cap: int) -> int:
    """Ask for a window big enough for the prompt *and* the answer.

    Sizing this per call rather than pinning one large value keeps short
    prompts cheap: the KV cache is allocated to `num_ctx`, so a fixed 32k
    would cost VRAM on every request that needs 5k.
    """
    needed = estimate_tokens(messages) + output_tokens + 256
    size = MIN_NUM_CTX
    while size < needed and size < cap:
        size *= 2
    return min(max(size, MIN_NUM_CTX), cap)


@dataclass
class Client:
    base_url: str = "http://127.0.0.1:11434"
    timeout_s: float = 600.0
    max_num_ctx: int = MAX_NUM_CTX

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url.rstrip('/')}{path}"
        try:
            r = httpx.post(url, json=payload, timeout=self.timeout_s)
        except httpx.ConnectError as exc:
            raise LlmUnavailable(
                f"Cannot reach Ollama at {self.base_url}. Is `ollama serve` running?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LlmError(f"Ollama timed out after {self.timeout_s:.0f}s.") from exc
        if r.status_code == 404:
            model = payload.get("model", "?")
            raise LlmError(f"Model '{model}' not found. Try: ollama pull {model}")
        if r.status_code >= 400:
            raise LlmError(f"Ollama returned {r.status_code}: {r.text[:300]}")
        return r.json()

    # -- capability checks -------------------------------------------------

    def available(self) -> bool:
        try:
            httpx.get(f"{self.base_url.rstrip('/')}/api/version", timeout=5.0)
        except httpx.HTTPError:
            return False
        return True

    def models(self) -> list[str]:
        try:
            r = httpx.get(f"{self.base_url.rstrip('/')}/api/tags", timeout=15.0)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LlmUnavailable(f"Cannot list Ollama models: {exc}") from exc
        return sorted(m["name"] for m in r.json().get("models", []))

    # -- generation --------------------------------------------------------

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        num_ctx: int | None = None,
        think: bool = False,
    ) -> str:
        options: dict[str, Any] = {
            "temperature": temperature,
            "num_ctx": num_ctx or plan_num_ctx(messages, 1024, self.max_num_ctx),
        }
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": think,
            "options": options,
        }
        data = self._post("/api/chat", payload)
        return (data.get("message") or {}).get("content", "")

    def structured(
        self,
        model: str,
        messages: list[dict[str, str]],
        schema: dict,
        *,
        temperature: float = 0.2,
        num_ctx: int | None = None,
        output_tokens: int = 1536,
        think: bool = False,
    ) -> dict:
        """Chat constrained to a JSON schema.

        The schema guarantees shape, never truth — whether the quotes it
        returns actually occur in the transcript is decided later, by
        `anchor.py`. Both gates are needed.

        The context window is sized for this specific prompt, and a reply that
        still runs out of room is retried with a larger one before giving up.
        """
        planned = num_ctx or plan_num_ctx(messages, output_tokens, self.max_num_ctx)
        attempts = []

        while True:
            options: dict[str, Any] = {"temperature": temperature, "num_ctx": planned}
            data = self._post("/api/chat", {
                "model": model,
                "messages": messages,
                "stream": False,
                "think": think,
                "format": schema,
                "options": options,
            })
            content = (data.get("message") or {}).get("content", "").strip()
            truncated = data.get("done_reason") == "length"
            attempts.append(planned)

            if not truncated and content:
                try:
                    return json.loads(content)
                except json.JSONDecodeError as exc:
                    raise LlmError(
                        f"{model} returned invalid JSON despite a schema: "
                        f"{content[:300]}"
                    ) from exc

            if truncated and planned < self.max_num_ctx:
                planned = min(planned * 2, self.max_num_ctx)
                continue  # the answer did not fit; give it more room

            if truncated:
                prompt_tokens = data.get("prompt_eval_count", "?")
                raise LlmTruncated(
                    f"{model} ran out of context and its answer was cut off "
                    f"(prompt {prompt_tokens} tokens, tried num_ctx "
                    f"{', '.join(str(a) for a in attempts)}). "
                    f"Use a smaller chunk size, or a model with more context."
                )
            raise LlmError(f"{model} returned an empty response.")

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        data = self._post("/api/embed", {"model": model, "input": texts})
        return data.get("embeddings") or []
