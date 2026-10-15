import json
from dataclasses import replace

import httpx
import pytest

from shelltrace.agent.brain import BrainUnavailable
from shelltrace.agent.claude_brain import make_brain
from shelltrace.agent.ports import ToolSpec, ToolCallResult
from shelltrace.config import get_settings


def completion(message, finish="stop"):
    return {"choices": [{"message": message, "finish_reason": finish}]}


def brain_for(handler, **kwargs):
    from shelltrace.agent.groq_brain import GroqBrain

    return GroqBrain(
        "openai/gpt-oss-120b",
        ["first", "second"],
        transport=httpx.MockTransport(handler),
        **kwargs
    )


async def test_groq_tool_history_and_mcp_schema():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(
                200,
                json=completion(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "c1",
                                "type": "function",
                                "function": {
                                    "name": "case_history",
                                    "arguments": json.dumps(
                                        {
                                            "entity_id": "e",
                                            "rationale": "recall",
                                            "confidence": 0.8,
                                        }
                                    ),
                                },
                            }
                        ],
                    },
                    "tool_calls",
                ),
            )
        return httpx.Response(200, json=completion({"content": "done"}))

    brain = brain_for(handler)
    specs = [
        ToolSpec(
            "case_history",
            "recall",
            {"type": "object", "properties": {"entity_id": {"type": "string"}}},
        )
    ]
    action = await brain.next_action({"case": {}}, specs)
    assert action.args == {"entity_id": "e"}
    assert action.probability == 0.8
    brain.observe(action, ToolCallResult(True, {"cases": []}, None, 1))
    assert (await brain.next_action({"case": {}}, specs)).kind == "stop"
    assert calls[0]["parallel_tool_calls"] is False
    assert calls[0]["tools"][0]["function"]["name"] == "case_history"
    assert calls[1]["messages"][-1]["tool_call_id"] == "c1"


@pytest.mark.parametrize(
    "message,finish",
    [
        ({"content": None}, "stop"),
        ({"refusal": "no"}, "stop"),
        ({"content": "cut"}, "length"),
        (
            {
                "tool_calls": [
                    {"id": "x", "function": {"name": "delete_all", "arguments": "{}"}}
                ]
            },
            "tool_calls",
        ),
        (
            {
                "tool_calls": [
                    {
                        "id": "x",
                        "function": {"name": "case_history", "arguments": "bad"},
                    }
                ]
            },
            "tool_calls",
        ),
    ],
)
async def test_groq_invalid_action_abstains(message, finish):
    brain = brain_for(lambda _: httpx.Response(200, json=completion(message, finish)))
    with pytest.raises(BrainUnavailable):
        await brain.next_action({"case": {}}, [])


async def test_groq_rate_limit_rotates_keys_with_bounded_attempts():
    headers = []

    def handler(request):
        headers.append(request.headers["authorization"])
        return httpx.Response(429)

    brain = brain_for(handler, max_attempts=2)
    with pytest.raises(BrainUnavailable, match="rate_limited"):
        await brain.next_action({"case": {}}, [])
    assert headers == ["Bearer first", "Bearer second"]


async def test_groq_validates_proposal_and_structured_request():
    payload = {
        "disposition": "EXPOSED",
        "rationale": "proof",
        "confidence": 0.9,
        "evidence_keys": ["x"],
    }
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=completion({"content": json.dumps(payload)}))

    brain = brain_for(handler)
    assert (await brain.propose({})).disposition == "EXPOSED"
    assert calls[0]["response_format"]["type"] == "json_schema"
    payload["confidence"] = 5
    with pytest.raises(BrainUnavailable, match="invalid_proposal"):
        await brain.propose({})


def test_provider_factory_routes_groq_using_only_groq_credentials():
    from shelltrace.agent.groq_brain import GroqBrain

    settings = replace(
        get_settings(), llm_provider="groq", groq_api_keys=("a", "b"), groq_api_key="a"
    )
    assert isinstance(make_brain(settings), GroqBrain)
    assert settings.groq_keys == ("a", "b")
    assert make_brain(replace(settings, groq_api_keys=(), groq_api_key=None)) is None


def test_factory_distributes_case_starting_keys():
    settings = replace(
        get_settings(),
        llm_provider="groq",
        groq_api_keys=("a", "b", "c"),
        groq_api_key=None,
    )
    brains = [make_brain(settings) for _ in range(3)]
    assert (
        len({brain._keys[brain._key_index % len(brain._keys)] for brain in brains}) == 3
    )


async def test_groq_metadata_matches_model_tool_schema():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=completion(
                {
                    "tool_calls": [
                        {
                            "id": "x",
                            "function": {
                                "name": "case_history",
                                "arguments": json.dumps(
                                    {
                                        "rationale": "recall",
                                        "confidence": 0.9,
                                        "entity_id": "e",
                                    }
                                ),
                            },
                        }
                    ]
                },
                "tool_calls",
            ),
        )

    brain = brain_for(handler)
    action = await brain.next_action(
        {"case": {}},
        [
            ToolSpec(
                "case_history",
                "recall",
                {"type": "object", "properties": {"entity_id": {"type": "string"}}},
            )
        ],
    )
    properties = calls[0]["tools"][0]["function"]["parameters"]["properties"]
    assert "rationale" in properties and "_rationale" not in properties
    assert action.rationale == "recall"
    assert action.probability == 0.9
    assert action.args == {"entity_id": "e"}


@pytest.mark.parametrize(
    "confidence", [float("nan"), float("inf"), -1, 1.1, True, "high"]
)
async def test_groq_rejects_invalid_action_confidence(confidence):
    message = {
        "tool_calls": [
            {
                "id": "x",
                "function": {
                    "name": "finish_investigation",
                    "arguments": json.dumps(
                        {"rationale": "done", "confidence": confidence}
                    ),
                },
            }
        ]
    }
    brain = brain_for(
        lambda _: httpx.Response(200, json=completion(message, "tool_calls"))
    )
    with pytest.raises(BrainUnavailable, match="invalid_action"):
        await brain.next_action({"case": {}}, [])


async def test_groq_connection_failure_is_bounded():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ConnectError("unavailable", request=request)

    with pytest.raises(BrainUnavailable, match="connection"):
        await brain_for(handler).next_action({"case": {}}, [])
    assert len(calls) == 2


async def test_groq_parallel_calls_are_unavailable():
    call = {
        "id": "x",
        "function": {
            "name": "finish_investigation",
            "arguments": '{"rationale":"done","confidence":0.9}',
        },
    }
    brain = brain_for(
        lambda _: httpx.Response(
            200, json=completion({"tool_calls": [call, call]}, "tool_calls")
        )
    )
    with pytest.raises(BrainUnavailable, match="invalid_action"):
        await brain.next_action({"case": {}}, [])


async def test_physical_requests_share_budget_across_actions_and_proposal():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(429)

    brain = brain_for(handler, max_attempts=2, max_requests=3)
    with pytest.raises(BrainUnavailable, match="rate_limited"):
        await brain.next_action({"case": {}}, [])
    with pytest.raises(BrainUnavailable, match="request_budget_exhausted"):
        await brain.propose({})
    with pytest.raises(BrainUnavailable, match="request_budget_exhausted"):
        await brain.next_action({"case": {}}, [])
    assert len(requests) == len(brain.attempts) == 3
    assert all(attempt["status"] == 429 for attempt in brain.attempts)
    assert all(
        set(attempt) == {"attempt", "model", "status"} for attempt in brain.attempts
    )


def test_factory_passes_shared_request_budget():
    settings = replace(
        get_settings(),
        llm_provider="groq",
        groq_api_keys=("a",),
        groq_api_key=None,
        budget_model_calls=3,
    )
    assert make_brain(settings)._max_requests == 3
