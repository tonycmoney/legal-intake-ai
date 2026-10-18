"""Scripted stand in for the Claude API, used only in tests."""

from typing import Any

from app.llm import LLMResponse


def text(t: str) -> dict:
    return {"type": "text", "text": t}


def tool(name: str, data: dict, call_id: str = "toolu_1") -> dict:
    return {"type": "tool_use", "id": call_id, "name": name, "input": data}


def details(**kw) -> dict:
    base = {
        "client_name": "", "phone": "", "email": "", "practice_area": "unknown",
        "county": "", "in_custody": "unknown", "deadline": "", "urgency": "normal",
        "adverse_parties": [], "key_facts": [],
    }  # fmt: skip
    base.update(kw)
    return base


class FakeLLM:
    def __init__(self, responses: list[LLMResponse]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, *, system, messages, tools):
        # Deep enough copy to inspect what was sent on each call.
        self.calls.append({"system": system, "messages": [dict(m) for m in messages]})
        if not self.responses:
            raise AssertionError("FakeLLM ran out of scripted responses")
        return self.responses.pop(0)


def resp(*blocks: dict, stop: str | None = None) -> LLMResponse:
    if stop is None:
        stop = "tool_use" if any(b["type"] == "tool_use" for b in blocks) else "end_turn"
    return LLMResponse(content=list(blocks), stop_reason=stop)
