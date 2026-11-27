"""mcp_bridge.py - expose an MCP server's tools as harness tools (mcp SDK 2.x)."""
from __future__ import annotations

import asyncio
import threading

from mcp import Client

from mini_harness import REGISTRY, Tool

_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()
_sessions: list[tuple[asyncio.Event, asyncio.Task]] = []


def _run(coro):
    """Run a coroutine on the bridge's event loop from synchronous code."""
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout=120)


async def _session(server, ready: asyncio.Future, stop: asyncio.Event) -> None:
    """Own one MCP connection for its whole life inside a single task."""
    try:
        async with Client(server) as client:
            ready.set_result((client, (await client.list_tools()).tools))
            await stop.wait()
    except Exception as err:
        if not ready.done():
            ready.set_exception(err)


def connect(prefix: str, server) -> list[str]:
    """Register every tool of one MCP server.

    server is a URL string (Streamable HTTP) or StdioServerParameters (local process).
    Tools are registered as <prefix>__<tool> so names from different servers never clash.
    """
    async def _open():
        ready, stop = _loop.create_future(), asyncio.Event()
        task = asyncio.create_task(_session(server, ready, stop))
        client, tools = await ready
        _sessions.append((stop, task))
        return client, tools

    client, tools = _run(_open())

    def caller(tool_name: str):
        def call(**args) -> str:
            result = _run(client.call_tool(tool_name, args))
            blocks = result.content
            text = "\n".join(getattr(block, "text", str(block)) for block in blocks)
            return f"ERROR: {text}" if result.is_error else text
        return call

    names = []
    for spec in tools:
        name = f"{prefix}__{spec.name}"
        REGISTRY[name] = Tool(name, spec.description or "", spec.input_schema,
                              caller(spec.name), strict=False)   # third-party schemas
        names.append(name)                                       # are rarely strict-style
    return names


def close() -> None:
    """Shut every MCP connection down from the task that opened it."""
    async def _close():
        for stop, _ in _sessions:
            stop.set()
        await asyncio.gather(*(task for _, task in _sessions), return_exceptions=True)
        _sessions.clear()

    _run(_close())
