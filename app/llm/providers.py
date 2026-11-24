"""HTTP adapters for Anthropic, OpenAI and Gemini (no vendor SDKs needed)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from app.llm.base import LLMError, LLMRequest, LLMResponse

TIMEOUT = httpx.Timeout(60.0, connect=10.0)
_MODEL_WORDS = ("not found", "does not exist", "not supported", "invalid model", "unknown model")


def _provider_message(resp: httpx.Response) -> str:
    """Extract the provider's own error text (all three use {"error": {"message": ...}})."""
    try:
        body = resp.json()
    except ValueError:
        return ""
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        return str(err.get("message", ""))[:300]
    return str(err or "")[:300]


def classify(status: int, message: str, model: str) -> LLMError:
    low = message.lower()
    if status in (401, 403) or "api key" in low or "api_key" in low:
        return LLMError(
            "The provider rejected the API key. Check the key on the API keys page "
            "(or the platform key in Replit Secrets).",
            kind="auth",
        )
    if status == 404 or ("model" in low and any(w in low for w in _MODEL_WORDS)):
        return LLMError(
            f"The model “{model}” isn't available for this key. Pick another model in "
            "Agent configuration.",
            kind="model",
        )
    if status == 429:
        return LLMError(
            "The provider's rate limit or quota was hit (429). Try again shortly.", kind="rate"
        )
    if status == 400 and "temperature" in low:
        return LLMError("This model doesn't accept a custom temperature.", kind="temperature")
    detail = f": {message}" if message else ""
    return LLMError(f"Provider error {status}{detail}", kind="other")


def _post(url: str, headers: dict[str, str], body: dict[str, Any], model: str) -> dict[str, Any]:
    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise LLMError(
            f"Could not reach the model provider ({type(exc).__name__}).", kind="network"
        ) from exc
    if resp.status_code >= 400:
        raise classify(resp.status_code, _provider_message(resp), model)
    data: dict[str, Any] = resp.json()
    return data


def _with_temperature_retry(
    call: Callable[[float | None], LLMResponse], req: LLMRequest
) -> LLMResponse:
    """Some newer reasoning models reject a custom temperature: retry once without it."""
    try:
        return call(req.temperature)
    except LLMError as exc:
        if exc.kind != "temperature":
            raise
        return call(None)


class AnthropicProvider:
    name = "anthropic"

    def complete(self, req: LLMRequest, api_key: str) -> LLMResponse:
        def call(temp: float | None) -> LLMResponse:
            body: dict[str, Any] = {
                "model": req.model,
                "max_tokens": req.max_tokens,
                "system": req.system,
                "messages": [{"role": "user", "content": req.user}],
            }
            if temp is not None:
                body["temperature"] = temp
            data = _post(
                "https://api.anthropic.com/v1/messages",
                {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                body,
                req.model,
            )
            text = "".join(
                b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
            )
            usage = data.get("usage", {})
            return LLMResponse(
                text, usage.get("input_tokens", 0), usage.get("output_tokens", 0), req.model
            )

        return _with_temperature_retry(call, req)


class OpenAIProvider:
    name = "openai"

    def complete(self, req: LLMRequest, api_key: str) -> LLMResponse:
        def call(temp: float | None) -> LLMResponse:
            body: dict[str, Any] = {
                "model": req.model,
                "max_completion_tokens": req.max_tokens,
                "messages": [
                    {"role": "system", "content": req.system},
                    {"role": "user", "content": req.user},
                ],
            }
            if temp is not None:
                body["temperature"] = temp
            data = _post(
                "https://api.openai.com/v1/chat/completions",
                {"Authorization": f"Bearer {api_key}"},
                body,
                req.model,
            )
            choices = data.get("choices") or [{}]
            text = (choices[0].get("message") or {}).get("content") or ""
            usage = data.get("usage", {})
            return LLMResponse(
                text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), req.model
            )

        return _with_temperature_retry(call, req)


class GeminiProvider:
    name = "gemini"

    def complete(self, req: LLMRequest, api_key: str) -> LLMResponse:
        def call(temp: float | None) -> LLMResponse:
            gen: dict[str, Any] = {"maxOutputTokens": req.max_tokens}
            if temp is not None:
                gen["temperature"] = temp
            data = _post(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{req.model}:generateContent",
                {"x-goog-api-key": api_key},
                {
                    "systemInstruction": {"parts": [{"text": req.system}]},
                    "contents": [{"role": "user", "parts": [{"text": req.user}]}],
                    "generationConfig": gen,
                },
                req.model,
            )
            cands = data.get("candidates") or [{}]
            parts = (cands[0].get("content") or {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
            usage = data.get("usageMetadata", {})
            return LLMResponse(
                text,
                usage.get("promptTokenCount", 0),
                usage.get("candidatesTokenCount", 0),
                req.model,
            )

        return _with_temperature_retry(call, req)
