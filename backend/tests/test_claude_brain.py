import copy
import json
from dataclasses import replace
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from shelltrace.agent.brain import Action, BrainUnavailable
from shelltrace.agent.claude_brain import (
    BETAS,
    FINISH_TOOL,
    PROPOSAL_SCHEMA,
    ClaudeBrain,
    make_brain,
    to_claude_tool,
)
from shelltrace.agent.ports import McpMemoryToolPort, ToolCallResult
from shelltrace.config import get_settings
from shelltrace.mcp_server import TOOL_NAMES, build_mcp
from shelltrace.models import Proposal


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _client(messages):
    return SimpleNamespace(beta=SimpleNamespace(messages=messages))


def _response(content, stop_reason="tool_use"):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def _tool_use(name, input_data, tool_use_id="tool-1"):
    return SimpleNamespace(type="tool_use", id=tool_use_id, name=name, input=input_data)


def _text(value):
    return SimpleNamespace(type="text", text=value)


def _assert_strict_schema(node):
    if isinstance(node, dict):
        assert "title" not in node
        assert "default" not in node
        if node.get("type") == "object" and "properties" in node:
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
        for value in node.values():
            _assert_strict_schema(value)
    elif isinstance(node, list):
        for value in node:
            _assert_strict_schema(value)


@pytest.mark.asyncio
async def test_to_claude_tool_is_strict(store):
    async with McpMemoryToolPort(build_mcp(store)) as port:
        specs = await port.list_tools()

    assert [spec.name for spec in specs] == list(TOOL_NAMES)
    tools = [to_claude_tool(spec) for spec in specs]
    assert [tool["name"] for tool in tools] == list(TOOL_NAMES)
    for tool in [*tools, FINISH_TOOL]:
        assert tool["strict"] is True
        assert "_rationale" in tool["input_schema"]["required"] or tool is FINISH_TOOL
        if tool is not FINISH_TOOL:
            assert "_confidence" in tool["input_schema"]["required"]
        _assert_strict_schema(tool["input_schema"])


@pytest.mark.asyncio
async def test_tool_use_becomes_action_without_private_fields():
    messages = FakeMessages(
        [
            _response(
                [
                    _tool_use(
                        "rulepack_evaluate",
                        {
                            "workspace": "demo",
                            "entity_id": "c_nordharbor",
                            "_rationale": "check OFAC first",
                            "_confidence": 0.7,
                        },
                    )
                ]
            )
        ]
    )
    brain = ClaudeBrain("claude-opus-5", _client(messages))

    action = await brain.next_action({"case": {"entity_id": "c_nordharbor"}}, [])

    assert action == Action(
        "tool",
        "rulepack_evaluate",
        {"workspace": "demo", "entity_id": "c_nordharbor"},
        "check OFAC first",
        0.7,
    )


@pytest.mark.asyncio
async def test_finish_and_text_become_stop_actions():
    finish_brain = ClaudeBrain(
        "claude-opus-5",
        _client(
            FakeMessages(
                [
                    _response(
                        [_tool_use("finish_investigation", {"rationale": "done", "confidence": 0.9})]
                    )
                ]
            )
        ),
    )
    finished = await finish_brain.next_action({"case": {}}, [])
    assert finished == Action("stop", None, {}, "done", 0.9)

    text_brain = ClaudeBrain(
        "claude-opus-5",
        _client(FakeMessages([_response([_text("No further tool can change the result.")], "end_turn")])),
    )
    text_action = await text_brain.next_action({"case": {}}, [])
    assert text_action == Action("stop", None, {}, "No further tool can change the result.", None)


@pytest.mark.asyncio
async def test_refusal_and_api_errors_raise_unavailable():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    rate_limit = anthropic.RateLimitError(
        "rate limited", response=httpx.Response(429, request=request), body={}
    )
    connection = anthropic.APIConnectionError(request=request)
    api_error = anthropic.APIStatusError(
        "server error", response=httpx.Response(503, request=request), body={}
    )

    cases = [
        ("refusal", "refusal"),
        (rate_limit, "rate_limited"),
        (connection, "connection"),
        (api_error, "api_503"),
    ]
    for response, expected in cases:
        messages = FakeMessages(
            [
                _response([_text("refused")], "refusal")
                if response == "refusal"
                else response
            ]
        )
        brain = ClaudeBrain("claude-opus-5", _client(messages))
        with pytest.raises(BrainUnavailable, match=expected):
            await brain.next_action({"case": {}}, [])


@pytest.mark.asyncio
async def test_request_shape_and_append_only_history(store):
    async with McpMemoryToolPort(build_mcp(store)) as port:
        specs = await port.list_tools()
    responses = [
        _response([_tool_use("case_history", {"workspace": "demo", "entity_id": "c_nordharbor"})]),
        _response([_tool_use("finish_investigation", {"rationale": "enough", "confidence": 0.8})]),
    ]
    messages = FakeMessages(responses)
    brain = ClaudeBrain("claude-opus-5", _client(messages))
    view = {"case": {"entity_id": "c_nordharbor", "as_of": "2024-01-01"}}

    action = await brain.next_action(view, specs)
    brain.observe(action, ToolCallResult(True, {"prior_cases": []}, None, 1))
    await brain.next_action(view, specs)

    first, second = messages.calls
    assert first["model"] == "claude-opus-5"
    assert first["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert first["betas"] == BETAS == ["server-side-fallback-2026-07-01"]
    assert first["fallbacks"] == "default"
    assert first["output_config"]["effort"] == "low"
    assert first["cache_control"] == {"type": "ephemeral"}
    assert [tool["name"] for tool in first["tools"]] == [*TOOL_NAMES, "finish_investigation"]
    assert second["messages"][: len(first["messages"])] == first["messages"]


@pytest.mark.asyncio
async def test_propose_uses_structured_output_without_citations():
    payload = {
        "disposition": "EXPOSED",
        "rationale": "OFAC proof supports exposure.",
        "confidence": 0.9,
        "evidence_keys": ["syn:G1-1"],
    }
    messages = FakeMessages([_response([_text(json.dumps(payload))], "end_turn")])
    brain = ClaudeBrain("claude-opus-5", _client(messages))

    proposal = await brain.propose({"case": {"entity_id": "c_nordharbor"}})

    assert proposal == Proposal.model_validate(payload)
    request = messages.calls[0]
    assert request["output_config"]["format"] == {
        "type": "json_schema",
        "schema": PROPOSAL_SCHEMA,
    }
    assert "citations" not in json.dumps(request)


def test_make_brain_only_when_enabled():
    settings = get_settings()
    assert make_brain(replace(settings, llm_provider="none", anthropic_api_key="test-key")) is None

    brain = make_brain(
        replace(settings, llm_provider="anthropic", anthropic_api_key="test-key")
    )
    assert isinstance(brain, ClaudeBrain)
