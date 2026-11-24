"""Provider-agnostic LLM interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMRequest:
    system: str
    user: str
    model: str
    max_tokens: int
    temperature: float
    module_id: str = ""


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tokens_in: int
    tokens_out: int
    model: str


class LLMError(RuntimeError):
    """Provider call failed (network, auth, quota). Message is safe to show users."""

    def __init__(self, message: str, kind: str = "other") -> None:
        super().__init__(message)
        self.kind = kind  # auth | model | rate | temperature | network | other


class LLMProvider(Protocol):
    name: str

    def complete(self, req: LLMRequest, api_key: str) -> LLMResponse: ...


# Approximate list prices, USD per 1M tokens (input, output). Estimates only —
# update from each vendor's pricing page. Unknown models fall back to provider default.
PRICING: dict[str, tuple[float, float]] = {
    "anthropic": (1.00, 5.00),
    "openai": (0.10, 0.50),
    "gemini": (0.10, 0.40),
    "fake": (0.0, 0.0),
    "demo": (0.0, 0.0),
}


def estimate_cost(provider: str, tokens_in: int, tokens_out: int) -> float:
    p_in, p_out = PRICING.get(provider, (1.0, 5.0))
    return round((tokens_in * p_in + tokens_out * p_out) / 1_000_000, 6)
