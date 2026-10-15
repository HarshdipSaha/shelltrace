from __future__ import annotations

import copy
import json
from typing import Any

import anthropic

from ..models import Proposal
from .brain import Action, BrainUnavailable
from .prompts import PROPOSE, SYSTEM
from .ports import ToolCallResult, ToolSpec

BETAS = ["server-side-fallback-2026-07-01"]

FINISH_TOOL = {
    "name": "finish_investigation",
    "description": "Stop exploring; further calls would not change the outcome.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["rationale", "confidence"],
        "properties": {
            "rationale": {"type": "string"},
            "confidence": {"type": "number"},
        },
    },
}

PROPOSAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["disposition", "rationale", "confidence", "evidence_keys"],
    "properties": {
        "disposition": {
            "type": "string",
            "enum": ["EXPOSED", "ESCALATE", "CLEAR_WITHIN_BOUNDS"],
        },
        "rationale": {"type": "string"},
        "confidence": {"type": "number"},
        "evidence_keys": {"type": "array", "items": {"type": "string"}},
    },
}


def _strictify(node: Any) -> Any:
    if isinstance(node, dict):
        node.pop("title", None)
        node.pop("default", None)
        if node.get("type") == "object":
            node["additionalProperties"] = False
            if "properties" in node:
                node["required"] = list(node["properties"])
        for value in list(node.values()):
            _strictify(value)
    elif isinstance(node, list):
        for value in node:
            _strictify(value)
    return node


def to_claude_tool(spec: ToolSpec) -> dict[str, Any]:
    schema = _strictify(copy.deepcopy(spec.input_schema))
    properties = schema.setdefault("properties", {})
    properties["_rationale"] = {"type": "string"}
    properties["_confidence"] = {"type": "number"}
    schema["additionalProperties"] = False
    schema["required"] = list(properties)
    return {
        "name": spec.name,
        "description": spec.description[:1024],
        "strict": True,
        "input_schema": schema,
    }


class ClaudeBrain:
    def __init__(self, model: str, client: anthropic.AsyncAnthropic):
        self.model_id = model
        self._client = client
        self._messages: list[dict[str, Any]] = []
        self._tools: list[dict[str, Any]] | None = None
        self._pending_id: str | None = None
        self.usage: list[Any] = []

    async def _create(self, **kwargs):
        try:
            response = await self._client.beta.messages.create(
                model=self.model_id,
                betas=BETAS,
                fallbacks="default",
                **kwargs,
            )
        except anthropic.RateLimitError as exc:
            raise BrainUnavailable("rate_limited") from exc
        except anthropic.APIConnectionError as exc:
            raise BrainUnavailable("connection") from exc
        except anthropic.APIStatusError as exc:
            raise BrainUnavailable(f"api_{exc.status_code}") from exc
        if response.stop_reason == "refusal":
            raise BrainUnavailable("refusal")
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.usage.append(usage)
        return response

    async def next_action(
        self, view: dict[str, Any], tools: list[ToolSpec]
    ) -> Action:
        if self._tools is None:
            self._tools = [to_claude_tool(tool) for tool in tools] + [FINISH_TOOL]
            self._messages.append(
                {"role": "user", "content": json.dumps(view["case"], sort_keys=True)}
            )

        response = await self._create(
            max_tokens=4000,
            system=SYSTEM,
            tools=self._tools,
            tool_choice={"type": "auto", "disable_parallel_tool_use": True},
            output_config={"effort": "low"},
            cache_control={"type": "ephemeral"},
            messages=self._messages,
        )
        self._messages.append({"role": "assistant", "content": response.content})
        use = next((block for block in response.content if block.type == "tool_use"), None)
        if use is None:
            rationale = " ".join(
                block.text for block in response.content if block.type == "text"
            )[:500] or "done"
            return Action("stop", None, {}, rationale, None)

        self._pending_id = use.id
        if use.name == FINISH_TOOL["name"]:
            return Action(
                "stop",
                None,
                {},
                use.input.get("rationale", ""),
                use.input.get("confidence"),
            )

        return Action(
            "tool",
            use.name,
            {key: value for key, value in use.input.items() if not key.startswith("_")},
            use.input.get("_rationale", ""),
            use.input.get("_confidence"),
        )

    def observe(self, action: Action, result: ToolCallResult) -> None:
        del action
        content = json.dumps(
            result.data if result.ok else {"error": result.error},
            sort_keys=True,
            default=str,
        )[:20_000]
        self._messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": self._pending_id,
                        "content": content,
                        "is_error": not result.ok,
                    }
                ],
            }
        )

    async def propose(self, view: dict[str, Any]) -> Proposal:
        response = await self._create(
            max_tokens=2000,
            system=PROPOSE,
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": PROPOSAL_SCHEMA},
            },
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(view, sort_keys=True, default=str)[:60_000],
                }
            ],
        )
        text = next(
            (block.text for block in response.content if block.type == "text"), None
        )
        if text is None:
            raise BrainUnavailable("invalid_proposal")
        return Proposal.model_validate_json(text)


def make_brain(settings):
    if not settings.llm_enabled:
        return None
    if settings.llm_provider == "groq":
        from .groq_brain import make_groq_brain
        return make_groq_brain(settings)
    return ClaudeBrain(
        settings.llm_model,
        anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key),
    )
