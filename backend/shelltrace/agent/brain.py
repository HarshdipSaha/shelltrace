from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from ..models import Proposal
from .ports import ToolCallResult, ToolSpec


@dataclass(frozen=True)
class Action:
    kind: Literal["tool", "stop"]
    tool: str | None
    args: dict[str, Any]
    rationale: str
    probability: float | None


class BrainUnavailable(Exception):
    """The optional reasoning service could not produce a usable response."""


class Brain(Protocol):
    model_id: str

    async def next_action(
        self, view: dict[str, Any], tools: list[ToolSpec]
    ) -> Action: ...

    def observe(self, action: Action, result: ToolCallResult) -> None: ...

    async def propose(self, view: dict[str, Any]) -> Proposal: ...


class ScriptedBrain:
    model_id = "scripted"

    def __init__(
        self,
        actions,
        proposal: Proposal | None = None,
        fail_after: int | None = None,
    ):
        self._actions = list(actions)
        self._proposal = proposal
        self._fail_after = fail_after
        self._calls = 0
        self._index = 0
        self.observations: list[tuple[Action, ToolCallResult]] = []

    async def next_action(
        self, view: dict[str, Any], tools: list[ToolSpec]
    ) -> Action:
        del view, tools
        if self._fail_after is not None and self._calls >= self._fail_after:
            raise BrainUnavailable("scripted brain unavailable")
        self._calls += 1
        if self._index >= len(self._actions):
            return Action("stop", None, {}, "script exhausted", None)
        action = self._actions[self._index]
        self._index += 1
        return action

    def observe(self, action: Action, result: ToolCallResult) -> None:
        self.observations.append((action, result))

    async def propose(self, view: dict[str, Any]) -> Proposal:
        del view
        if self._proposal is None:
            raise BrainUnavailable("scripted proposal unavailable")
        return self._proposal