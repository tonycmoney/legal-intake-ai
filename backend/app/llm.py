"""Thin wrapper over the Claude Messages API.

Kept behind a small protocol so the agent can be tested with a scripted fake
and the provider could be swapped without touching business logic.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class LLMResponse:
    content: list[dict[str, Any]]  # raw content blocks, replayed unchanged next turn
    stop_reason: str


class LLM(Protocol):
    def create(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResponse: ...


class LLMUnavailable(RuntimeError):
    pass


class AnthropicLLM:
    def __init__(self, api_key: str, model: str, effort: str, max_tokens: int) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=60)
        self._errors = anthropic.APIError
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    def create(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=messages,
                tools=tools,
                # Sonnet 5.5 rejects forced tool choice; strict tools + auto instead.
                tool_choice={"type": "auto"},
                extra_body={"output_config": {"effort": self.effort}},
            )
        except self._errors as exc:  # network, rate limit, overload, bad request
            raise LLMUnavailable(str(exc)) from exc
        return LLMResponse(
            content=[block.model_dump(exclude_none=True) for block in response.content],
            stop_reason=response.stop_reason or "end_turn",
        )
