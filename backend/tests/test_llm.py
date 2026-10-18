"""Exercise the real Anthropic SDK against a mock HTTP transport.

Verifies the exact request we send (model, tools, tool_choice, effort, no
sampling params) and that response blocks survive the round trip.
"""

import json

import httpx2 as httpx
import pytest

from app.agent import TOOLS
from app.llm import AnthropicLLM, LLMUnavailable

API_RESPONSE = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-5-5",
    "stop_reason": "tool_use",
    "stop_sequence": None,
    "usage": {"input_tokens": 10, "output_tokens": 5},
    "content": [
        {"type": "thinking", "thinking": "", "signature": "sig-abc"},
        {"type": "text", "text": "Let me note that."},
        {
            "type": "tool_use",
            "id": "toolu_9",
            "name": "complete_intake",
            "input": {"summary": "s", "recommended_next_step": "n"},
        },
    ],
}


def make_llm(handler) -> AnthropicLLM:
    llm = AnthropicLLM(api_key="test-key", model="claude-sonnet-5-5", effort="low", max_tokens=99)
    import anthropic

    llm._client = anthropic.Anthropic(
        api_key="test-key",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return llm


def test_request_shape_and_response_round_trip():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=API_RESPONSE)

    out = make_llm(handler).create(
        system="sys", messages=[{"role": "user", "content": "hi"}], tools=TOOLS
    )

    body = seen["body"]
    assert seen["url"].endswith("/v1/messages")
    assert body["model"] == "claude-sonnet-5-5"
    assert body["max_tokens"] == 99
    assert body["tool_choice"] == {"type": "auto"}
    assert body["output_config"] == {"effort": "low"}
    assert all(t["strict"] for t in body["tools"])
    for param in ("temperature", "top_p", "top_k"):
        assert param not in body

    assert out.stop_reason == "tool_use"
    assert out.content[0] == {"type": "thinking", "thinking": "", "signature": "sig-abc"}
    assert out.content[2]["input"]["summary"] == "s"


def test_api_errors_become_llm_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(529, json={"type": "error", "error": {"type": "overloaded_error"}})

    with pytest.raises(LLMUnavailable):
        make_llm(handler).create(system="s", messages=[], tools=[])
