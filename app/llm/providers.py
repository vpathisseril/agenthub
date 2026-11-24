"""HTTP adapters for Anthropic, OpenAI and Gemini (no vendor SDKs needed)."""

from __future__ import annotations

from typing import Any

import httpx

from app.llm.base import LLMError, LLMRequest, LLMResponse

TIMEOUT = httpx.Timeout(60.0, connect=10.0)


def _post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise LLMError(f"Could not reach the model provider ({type(exc).__name__}).") from exc
    if resp.status_code == 401:
        raise LLMError("The provider rejected the API key (401).")
    if resp.status_code == 429:
        raise LLMError("The provider rate limit or quota was hit (429). Try again later.")
    if resp.status_code >= 400:
        raise LLMError(f"Provider error {resp.status_code}.")
    data: dict[str, Any] = resp.json()
    return data


class AnthropicProvider:
    name = "anthropic"

    def complete(self, req: LLMRequest, api_key: str) -> LLMResponse:
        data = _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            {
                "model": req.model,
                "max_tokens": req.max_tokens,
                "temperature": req.temperature,
                "system": req.system,
                "messages": [{"role": "user", "content": req.user}],
            },
        )
        text = "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        )
        usage = data.get("usage", {})
        return LLMResponse(
            text, usage.get("input_tokens", 0), usage.get("output_tokens", 0), req.model
        )


class OpenAIProvider:
    name = "openai"

    def complete(self, req: LLMRequest, api_key: str) -> LLMResponse:
        data = _post(
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {api_key}"},
            {
                "model": req.model,
                "max_completion_tokens": req.max_tokens,
                "temperature": req.temperature,
                "messages": [
                    {"role": "system", "content": req.system},
                    {"role": "user", "content": req.user},
                ],
            },
        )
        choices = data.get("choices") or [{}]
        text = (choices[0].get("message") or {}).get("content") or ""
        usage = data.get("usage", {})
        return LLMResponse(
            text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), req.model
        )


class GeminiProvider:
    name = "gemini"

    def complete(self, req: LLMRequest, api_key: str) -> LLMResponse:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{req.model}:generateContent"
        data = _post(
            url,
            {"x-goog-api-key": api_key},
            {
                "systemInstruction": {"parts": [{"text": req.system}]},
                "contents": [{"role": "user", "parts": [{"text": req.user}]}],
                "generationConfig": {
                    "maxOutputTokens": req.max_tokens,
                    "temperature": req.temperature,
                },
            },
        )
        cands = data.get("candidates") or [{}]
        parts = (cands[0].get("content") or {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        usage = data.get("usageMetadata", {})
        return LLMResponse(
            text, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0), req.model
        )
