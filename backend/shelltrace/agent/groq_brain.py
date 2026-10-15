from __future__ import annotations

import asyncio
import copy
import json
import math
from threading import Lock
from typing import Any

import httpx

from ..models import Proposal
from .brain import Action, BrainUnavailable
from .claude_brain import FINISH_TOOL, PROPOSAL_SCHEMA, to_claude_tool
from .ports import ToolCallResult, ToolSpec
from .prompts import PROPOSE, SYSTEM


_POOL_LOCK = Lock()
_POOL_START = 0


def make_groq_brain(settings):
    global _POOL_START
    with _POOL_LOCK:
        start = _POOL_START
        _POOL_START += 1
    return GroqBrain(
        settings.llm_model,
        settings.groq_keys,
        timeout_s=settings.llm_timeout_s,
        max_attempts=settings.llm_max_attempts,
        start_index=start,
        max_requests=settings.budget_model_calls,
    )


def _probability(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError("invalid confidence")
    return float(value)


class GroqBrain:
    """Bounded OpenAI-compatible adapter. The runner authorizes every tool call."""

    def __init__(
        self,
        model: str,
        keys,
        *,
        timeout_s=8.0,
        max_attempts=2,
        transport=None,
        start_index=0,
        max_requests=10,
    ):
        self.model_id = model
        self._keys = tuple(dict.fromkeys(k for k in keys if k))
        self._timeout = min(15.0, max(0.1, timeout_s))
        self._max_attempts = min(3, max(1, max_attempts))
        self._max_requests = max(0, int(max_requests))
        self._transport = transport
        self._key_index = start_index
        self._messages = []
        self._tools = None
        self._pending_id = None
        self.usage = []
        self.attempts = []

    async def _create(self, **payload):
        if not self._keys:
            raise BrainUnavailable("missing_credentials")
        reason = "connection"
        for attempt in range(self._max_attempts):
            if len(self.attempts) >= self._max_requests:
                raise BrainUnavailable("request_budget_exhausted")
            key = self._keys[self._key_index % len(self._keys)]
            attempt_record = {
                "attempt": len(self.attempts) + 1,
                "model": self.model_id,
                "status": "pending",
            }
            self.attempts.append(attempt_record)
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout, transport=self._transport
                ) as client:
                    async with asyncio.timeout(self._timeout):
                        response = await client.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers={"Authorization": f"Bearer {key}"},
                            json={"model": self.model_id, **payload},
                        )
                status = response.status_code
                attempt_record["status"] = status
                if status != 200:
                    reason = "rate_limited" if status == 429 else f"api_{status}"
                    if status in (401, 403, 429) or status >= 500:
                        self._key_index += 1
                        continue
                    raise BrainUnavailable(reason)
                data = response.json()
                choice = data["choices"][0]
                message = choice["message"]
                if message.get("refusal"):
                    raise BrainUnavailable("refusal")
                if choice.get("finish_reason") not in ("stop", "tool_calls"):
                    raise BrainUnavailable("incomplete_response")
                if not isinstance(message, dict):
                    raise ValueError("message")
                self.usage.append(data.get("usage", {}))
                return message
            except (httpx.RequestError, TimeoutError):
                attempt_record["status"] = "connection_or_timeout"
                reason = "connection"
            except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
                raise BrainUnavailable("invalid_response") from exc
        raise BrainUnavailable(reason)

    async def next_action(self, view: dict[str, Any], tools: list[ToolSpec]) -> Action:
        if self._tools is None:
            converted = [to_claude_tool(tool) for tool in tools] + [
                copy.deepcopy(FINISH_TOOL)
            ]
            for tool in converted[:-1]:
                schema = tool["input_schema"]
                for field in ("rationale", "confidence"):
                    schema["properties"][field] = schema["properties"].pop("_" + field)
                schema["required"] = [
                    key.lstrip("_") if key in ("_rationale", "_confidence") else key
                    for key in schema["required"]
                ]
            self._tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"],
                    },
                }
                for t in converted
            ]
            self._messages = [
                {
                    "role": "system",
                    "content": SYSTEM.replace("_rationale", "rationale").replace(
                        "_confidence", "confidence"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(view, sort_keys=True, default=str),
                },
            ]
        message = await self._create(
            messages=self._messages,
            tools=self._tools,
            tool_choice="auto",
            parallel_tool_calls=False,
            max_completion_tokens=4000,
            reasoning_effort="low",
        )
        try:
            uses = message.get("tool_calls") or []
            if not uses:
                text = message.get("content")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("empty action")
                return Action("stop", None, {}, text[:500], None)
            if len(uses) != 1:
                raise ValueError("parallel calls")
            use = uses[0]
            name = use["function"]["name"]
            if name not in {t["function"]["name"] for t in self._tools}:
                raise ValueError("unknown tool")
            args = json.loads(use["function"]["arguments"])
            if not isinstance(args, dict) or not isinstance(use["id"], str):
                raise ValueError("invalid arguments")
            finish = name == FINISH_TOOL["name"]
            rationale = args.get("rationale", "")
            confidence = args.get("confidence")
            if not isinstance(rationale, str):
                raise ValueError("rationale")
            probability = _probability(confidence) if confidence is not None else None
            self._pending_id = use["id"]
            self._messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": uses,
                }
            )
            return Action(
                "stop" if finish else "tool",
                None if finish else name,
                (
                    {}
                    if finish
                    else {
                        k: v
                        for k, v in args.items()
                        if k not in ("rationale", "confidence")
                    }
                ),
                rationale,
                probability,
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise BrainUnavailable("invalid_action") from exc

    def observe(self, action: Action, result: ToolCallResult) -> None:
        self._messages.append(
            {
                "role": "tool",
                "tool_call_id": self._pending_id,
                "content": json.dumps(
                    result.data if result.ok else {"error": result.error},
                    sort_keys=True,
                    default=str,
                )[:20_000],
            }
        )

    async def propose(self, view: dict[str, Any]) -> Proposal:
        message = await self._create(
            messages=[
                {"role": "system", "content": PROPOSE},
                {
                    "role": "user",
                    "content": json.dumps(view, sort_keys=True, default=str)[:60_000],
                },
            ],
            max_completion_tokens=2000,
            reasoning_effort="low",
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "proposal",
                    "strict": True,
                    "schema": PROPOSAL_SCHEMA,
                },
            },
        )
        try:
            proposal = Proposal.model_validate_json(message["content"])
            _probability(proposal.confidence)
            return proposal
        except (ValueError, KeyError, TypeError) as exc:
            raise BrainUnavailable("invalid_proposal") from exc
