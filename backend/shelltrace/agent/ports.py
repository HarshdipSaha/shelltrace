from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from typing import Any, Protocol

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.memory import create_connected_server_and_client_session


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCallResult:
    ok: bool
    data: dict[str, Any] | None
    error: str | None
    latency_ms: int


class ToolPort(Protocol):
    async def list_tools(self) -> list[ToolSpec]: ...

    async def call(self, name: str, args: dict[str, Any]) -> ToolCallResult: ...


class _SessionPort:
    _s: ClientSession

    async def list_tools(self) -> list[ToolSpec]:
        response = await self._s.list_tools()
        return [
            ToolSpec(tool.name, tool.description or "", tool.inputSchema)
            for tool in response.tools
        ]

    async def call(self, name: str, args: dict[str, Any]) -> ToolCallResult:
        started = time.monotonic()
        try:
            response = await self._s.call_tool(name, args)
            latency_ms = int((time.monotonic() - started) * 1000)
            if response.isError:
                error = " ".join(
                    getattr(content, "text", "") for content in response.content
                )[:500]
                return ToolCallResult(False, None, error, latency_ms)
            return ToolCallResult(
                True,
                response.structuredContent or {},
                None,
                latency_ms,
            )
        except Exception as exc:
            return ToolCallResult(
                False,
                None,
                f"{type(exc).__name__}: {exc}"[:500],
                int((time.monotonic() - started) * 1000),
            )


class McpMemoryToolPort(_SessionPort):
    def __init__(self, server):
        self._server = server

    async def __aenter__(self) -> McpMemoryToolPort:
        self._cm = create_connected_server_and_client_session(
            self._server._mcp_server
        )
        self._s = await self._cm.__aenter__()
        return self

    async def __aexit__(self, *exc):
        return await self._cm.__aexit__(*exc)


class McpHttpToolPort(_SessionPort):
    def __init__(self, url: str, api_key: str | None = None):
        self._url = url
        self._key = api_key

    async def __aenter__(self) -> McpHttpToolPort:
        self._stack = contextlib.AsyncExitStack()
        try:
            headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
            read, write, _ = await self._stack.enter_async_context(
                streamablehttp_client(self._url, headers=headers)
            )
            self._s = await self._stack.enter_async_context(
                ClientSession(read, write)
            )
            await self._s.initialize()
            return self
        except BaseException:
            await self._stack.aclose()
            raise

    async def __aexit__(self, *exc):
        return await self._stack.aclose()