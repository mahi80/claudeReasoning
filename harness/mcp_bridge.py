"""mcp_bridge.py - expose an MCP server's tools as harness tools (mcp SDK 2.x)."""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from concurrent.futures import TimeoutError
from pathlib import Path
from urllib.parse import urlparse

from mcp import Client, StdioServerParameters

from mini_harness import REGISTRY, Tool, time_left

_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()
_sessions: list[tuple[asyncio.Event, asyncio.Task]] = []
_registered: set[str] = set()


def _run(coro):
    """Run a coroutine on the bridge's event loop from synchronous code."""
    try:
        timeout = time_left(120)
    except Exception:
        coro.close()
        raise
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        future.cancel()
        time_left(120)
        raise


async def _session(server, ready: asyncio.Future, stop: asyncio.Event) -> None:
    """Own one MCP connection for its whole life inside a single task."""
    try:
        async with Client(server) as client:
            ready.set_result((client, (await client.list_tools()).tools))
            await stop.wait()
    except Exception as err:
        if not ready.done():
            ready.set_exception(err)


def connect(prefix: str, server, allowed_tools: list[str] | None = None) -> list[str]:
    """Register every tool of one MCP server.

    server is a URL string (Streamable HTTP) or StdioServerParameters (local process).
    Tools are registered as <prefix>__<tool> and require operator approval.
    """
    async def _open():
        ready, stop = _loop.create_future(), asyncio.Event()
        task = asyncio.create_task(_session(server, ready, stop))
        try:
            client, tools = await ready
        except BaseException:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        _sessions.append((stop, task))
        return client, tools

    client, tools = _run(_open())
    if allowed_tools is not None:
        missing = set(allowed_tools) - {spec.name for spec in tools}
        if missing:
            raise ValueError(f"MCP server {prefix} has no tools: {', '.join(sorted(missing))}")
        tools = [spec for spec in tools if spec.name in allowed_tools]
    for spec in tools:
        name = f"{prefix}__{spec.name}"
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name) or name in REGISTRY:
            raise ValueError(f"Invalid or duplicate MCP tool name: {name}")

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
                              caller(spec.name), needs_approval=True, strict=False)
        names.append(name)
        _registered.add(name)
    return names


def load_config(path: str) -> list[str]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict) or set(config) != {"servers"} or not isinstance(config["servers"], dict):
        raise ValueError("MCP config must contain a servers object")
    servers = []
    for prefix, spec in config["servers"].items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", prefix) or not isinstance(spec, dict):
            raise ValueError("MCP server names and definitions are invalid")
        tools = spec.get("tools")
        if (not isinstance(tools, list) or not tools
                or any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name)
                       for name in tools) or len(set(tools)) != len(tools)):
            raise ValueError(f"MCP server {prefix} needs an explicit non-empty tool allowlist")
        if "url" in spec:
            url = spec["url"]
            if (set(spec) - {"url", "tools"} or not isinstance(url, str)
                    or urlparse(url).scheme not in {"http", "https"} or not urlparse(url).netloc):
                raise ValueError(f"MCP server {prefix} needs an HTTP(S) URL and tool allowlist")
            server = url
        else:
            command, args, env = spec.get("command"), spec.get("args", []), spec.get("env", [])
            if (set(spec) - {"command", "args", "env", "tools"}
                    or not isinstance(command, str) or not command
                    or not isinstance(args, list) or any(not isinstance(arg, str) for arg in args)
                    or not isinstance(env, list)
                    or any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
                           or name not in os.environ for name in env)):
                raise ValueError(f"MCP server {prefix} has invalid command, args or environment names")
            server = StdioServerParameters(command=command, args=args,
                                           env={name: os.environ[name] for name in env})
        servers.append((prefix, server, tools))
    names = []
    try:
        for prefix, server, tools in servers:
            names += connect(prefix, server, tools)
        return names
    except Exception:
        close()
        raise


def close() -> None:
    """Shut every MCP connection down from the task that opened it."""
    async def _close():
        for stop, _ in _sessions:
            stop.set()
        await asyncio.gather(*(task for _, task in _sessions), return_exceptions=True)
        _sessions.clear()
    for name in _registered:
        REGISTRY.pop(name, None)
    _registered.clear()

    _run(_close())
