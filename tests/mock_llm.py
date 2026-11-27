"""Mock OpenAI-compatible chat endpoint with SSE streaming and scripted 'model' behaviour.

It validates every request the way a strict chat template would (role order, tool-call
pairing, tool schemas) and answers according to a scenario tag in the task text.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
COUNTERS: dict[str, int] = defaultdict(int)
REQUESTS: list[dict] = []
ERRORS: list[str] = []


def validate(body: dict) -> None:
    msgs = body["messages"]
    if msgs[0]["role"] not in ("system", "user"):
        raise ValueError("first message must be system or user")
    pending: set[str] = set()
    prev = None
    for m in msgs:
        role = m["role"]
        if role == "user" and prev == "user":
            raise ValueError("consecutive user messages")
        if role in ("user", "assistant") and pending:
            raise ValueError("turn started before all tool results were returned")
        if role == "assistant":
            if not m.get("content") and not m.get("tool_calls"):
                raise ValueError("assistant message with neither content nor tool calls")
            if "reasoning" in m and not isinstance(m["reasoning"], str):
                raise ValueError("returned reasoning must be a string")
            for tc in m.get("tool_calls") or []:
                if not tc.get("id"):
                    raise ValueError("tool call without id")
                pending.add(tc["id"])
        if role == "tool":
            if m.get("tool_call_id") not in pending:
                raise ValueError("tool result without a matching tool call")
            pending.discard(m["tool_call_id"])
            if not isinstance(m.get("content"), str):
                raise ValueError("tool content must be a string")
        prev = role
    if pending:
        raise ValueError("assistant tool calls left without results")
    if prev == "assistant":
        raise ValueError("conversation must not end on an assistant message")
    if "max_tokens" in body and (not isinstance(body["max_tokens"], int)
                                 or body["max_tokens"] < 1):
        raise ValueError("max_tokens must be a positive integer")
    for t in body.get("tools") or []:
        fn = t["function"]
        if not fn.get("name") or not fn.get("description"):
            raise ValueError("tool needs a name and a description")
        if fn.get("strict") and fn["parameters"].get("additionalProperties") is not False:
            raise ValueError(f"strict tool {fn['name']} must set additionalProperties false")


def last_tool_results(msgs: list[dict], n: int = 1) -> list[str]:
    return [m["content"] for m in msgs if m["role"] == "tool"][-n:]


def thinking_on(body: dict) -> bool:
    """The tests switch thinking the way Mistral Small 4 does: reasoning_effort."""
    return body.get("reasoning_effort") == "high"


def nudged(msgs: list[dict], opening: str) -> bool:
    """Did the harness add a follow-up user message that starts with this text?"""
    return any(m["role"] == "user" and m["content"].startswith(opening) for m in msgs[2:])


def policy(body: dict) -> dict:
    """Return {'text': str, 'calls': [(name, raw_args)], 'delay': float}."""
    msgs = body["messages"]
    first_user = next(m["content"] for m in msgs if m["role"] == "user")
    if first_user.startswith("Summarise this agent transcript"):
        return {"text": "SUMMARY: earlier files were written as planned.", "calls": []}
    task = re.split(r"\n\n\[(?:Current plan|Summary of your earlier work)\]", first_user)[0]
    tag = re.search(r"\[scenario:(\w+)\]", task)
    # untagged tasks (typed by a person in the UI demo) get a default script
    words = task.lower()
    default = "denied" if "delete" in words else "plan" if "report" in words else "basic"
    scenario = tag.group(1) if tag else default
    with LOCK:
        i = COUNTERS[task]
        COUNTERS[task] += 1
    last = last_tool_results(msgs)
    j = json.dumps
    acted = sum(1 for m in msgs if m["role"] == "assistant" and m.get("tool_calls"))
    reviewer = msgs[0]["content"].startswith("You are an independent reviewer")
    if reviewer and scenario != "review":
        return {"text": "PASS"}

    if scenario == "verify":          # high effort and above: one self-check before finishing
        if not acted:
            return {"calls": [("write_file", j({"path": "v.txt", "content": "v1"}))]}
        if not nudged(msgs, "Before this goes to the user"):
            return {"text": "first answer"}
        if "confirm" in task:
            return {"text": "CONFIRMED"}
        if msgs[-1]["role"] == "user":
            return {"calls": [("read_file", j({"path": "v.txt"}))]}
        return {"text": f"checked answer: {last[0]}"}
    if scenario == "review":          # xhigh and max: a fresh-context reviewer can reject
        if reviewer:
            if "unclear" in task:
                return {"text": "Looks fine to me."}
            if not last:
                return {"calls": [("read_file", j({"path": "r.txt"}))]}
            return {"text": "PASS" if last[0] == "right" else "FAIL\nr.txt holds the wrong text"}
        rejected = nudged(msgs, "An independent reviewer rejected")
        if not acted:
            return {"calls": [("write_file", j({"path": "r.txt", "content": "wrong"}))]}
        if rejected and "stubborn" in task:
            return {"text": "CONFIRMED"}
        if rejected and acted == 1:
            return {"calls": [("write_file", j({"path": "r.txt", "content": "right"}))]}
        return {"text": "answer two" if rejected else "answer one"}
    if scenario == "fanout":          # three workers asked for; the level decides how many run
        if not acted:
            prefix = re.search(r"prefix=(\w+)", task).group(1)
            return {"calls": [
                ("spawn_agent", j({"task": f"[scenario:sub] write {prefix}{n}.txt"}))
                for n in (1, 2, 3)]}
        return {"text": " | ".join(last_tool_results(msgs, 3))}
    if scenario == "blank":           # thinking used the whole reply: nothing came back
        return {"text": "" if thinking_on(body) else "answer after retry"}
    if scenario == "think":
        if not acted:
            return {"calls": [("think", j({"thought": "The file must exist before I read it."}))]}
        return {"text": f"think said: {last[0]}"}
    if scenario == "basic":
        if i == 0:
            return {"calls": [("write_file", j({"path": "notes/a.txt", "content": "hello"}))]}
        if i == 1:
            return {"calls": [("read_file", j({"path": "notes/a.txt"}))]}
        return {"text": f"DONE: {last[0]}"}
    if scenario == "badjson":
        if i == 0:
            return {"calls": [("write_file", '{"path": "b.txt", "content": ')]}
        if i == 1:
            assert last[0].startswith("ERROR: arguments are not valid JSON"), last
            return {"calls": [("write_file", j({"path": "b.txt", "content": "fixed"}))]}
        return {"text": "recovered"}
    if scenario == "unknown":
        if i == 0:
            return {"calls": [("delete_everything", "{}")]}
        return {"text": f"saw: {last[0]}"}
    if scenario == "loop":
        if last and "already run twice" in last[0]:
            return {"text": "gave up"}
        return {"calls": [("list_dir", j({"path": "."}))]}
    if scenario == "parallel":
        if i == 0:
            return {"calls": [("spawn_agent", j({"task": "[scenario:sub] write p1.txt"})),
                              ("spawn_agent", j({"task": "[scenario:sub] write p2.txt"}))]}
        return {"text": "REPORTS: " + " | ".join(last_tool_results(msgs, 2))}
    if scenario == "sub":
        name = re.search(r"write (\S+)", task).group(1)
        if i == 0:
            return {"calls": [("write_file", j({"path": name, "content": "from worker"}))],
                    "delay": 0.4}
        return {"text": f"report: {name} written", "delay": 0.4}
    if scenario == "compact":
        if i < 12:
            return {"calls": [("write_file", j({"path": f"c{i}.txt", "content": "x" * 3000}))]}
        return {"text": "finished compact"}
    if scenario == "steps":
        return {"calls": [("write_file", j({"path": f"s{i}.txt", "content": "x"}))]}
    if scenario == "denied":
        commands = ["rm -rf important", "ls; rm -rf important", "ls"]
        if i < 3:
            return {"calls": [("run_shell", j({"command": commands[i]}))]}
        return {"text": " || ".join(last_tool_results(msgs, 3))}
    if scenario == "jail":
        if i == 0:
            return {"calls": [("read_file", j({"path": "../../etc/passwd"}))]}
        return {"text": f"jail: {last[0]}"}
    if scenario == "mcp":
        if i == 0:
            return {"calls": [("demo__add", j({"a": 2, "b": 3}))]}
        return {"text": f"sum={last[0]}"}
    if scenario == "skill":
        if i == 0:
            return {"calls": [("load_skill", j({"name": "report-style"}))]}
        return {"text": f"skill said: {last[0][-40:]}"}
    if scenario == "plan":
        first = "[ ] write the file\n[ ] report back"
        second = "[x] write the file\n[ ] report back"
        if i == 0:
            return {"calls": [("update_plan", j({"plan": first}))]}
        if i == 1:
            ok = f"[Current plan]\n{first}" in first_user
            return {"calls": [("write_file", j({"path": "plan-seen.txt", "content": str(ok)}))]}
        if i == 2:
            return {"calls": [("update_plan", j({"plan": second}))]}
        ok = f"[Current plan]\n{second}" in first_user
        return {"text": "plan seen" if ok else "plan missing"}
    if scenario == "long":
        if i < 20:
            return {"calls": [("write_file", j({"path": f"l{i}.txt", "content": "x"}))]}
        return {"text": "all 20 written"}
    if scenario == "sequence":
        if i == 0:
            return {"calls": [
                ("write_file", j({"path": "q.txt", "content": "first"})),
                ("edit_file", j({"path": "q.txt", "old_text": "first", "new_text": "second"}))]}
        if i == 1:
            return {"calls": [("read_file", j({"path": "q.txt"}))]}
        return {"text": f"q={last[0]}"}
    raise ValueError(f"unknown scenario {scenario}")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):   # keep test output clean
        pass

    def _send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.headers.get("Authorization") != "Bearer test-key":
            return self._send_json(401, {"error": {"message": "bad api key"}})
        try:
            validate(body)
            plan = policy(body)
        except Exception as err:   # surface as HTTP 400, like a strict server would
            ERRORS.append(f"{type(err).__name__}: {err}")
            return self._send_json(400, {"error": {"message": str(err)}})
        with LOCK:
            REQUESTS.append(body)
        time.sleep(plan.get("delay", 0))
        if not body.get("stream"):                      # plain JSON reply
            calls = [{"id": f"call{i}plain", "type": "function",
                      "function": {"name": n, "arguments": a}}
                     for i, (n, a) in enumerate(plan.get("calls", []))]
            message = {"role": "assistant", "content": plan.get("text") or None}
            if calls:
                message["tool_calls"] = calls
            if thinking_on(body):
                message["reasoning"] = "Weighing the next step. Decided."
            return self._send_json(200, {
                "id": "chatcmpl-mock", "object": "chat.completion", "created": int(time.time()),
                "model": body["model"],
                "choices": [{"index": 0, "message": message,
                             "finish_reason": "tool_calls" if calls else "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def emit(payload) -> None:
            line = "data: " + (payload if isinstance(payload, str) else json.dumps(payload))
            data = (line + "\n\n").encode()
            self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
            self.wfile.flush()

        base = {"id": "chatcmpl-mock", "object": "chat.completion.chunk",
                "created": int(time.time()), "model": body["model"]}

        def chunk(delta: dict, finish=None) -> dict:
            return {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}

        emit(chunk({"role": "assistant", "content": ""}))
        if thinking_on(body):                           # reasoning arrives in its own field
            emit(chunk({"reasoning": "Weighing the next step. "}))
            emit(chunk({"reasoning": "Decided."}))
        text = plan.get("text", "")
        for k in range(0, len(text), 12):
            emit(chunk({"content": text[k:k + 12]}))
        calls = plan.get("calls", [])
        for idx, (name, raw) in enumerate(calls):
            cut = max(1, len(raw) // 2)
            emit(chunk({"tool_calls": [{"index": idx, "id": f"call{idx}x{len(REQUESTS):05d}",
                                        "type": "function",
                                        "function": {"name": name, "arguments": raw[:cut]}}]}))
            emit(chunk({"tool_calls": [{"index": idx, "function": {"arguments": raw[cut:]}}]}))
        emit(chunk({}, finish="tool_calls" if calls else "stop"))
        prompt_tokens = len(json.dumps(body["messages"])) // 4
        emit({**base, "choices": [], "usage": {"prompt_tokens": prompt_tokens,
                                                "completion_tokens": 10,
                                                "total_tokens": prompt_tokens + 10}})
        emit("[DONE]")
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()


class QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):   # clients closing keep-alive sockets
        pass


def start(port: int = 0) -> tuple[ThreadingHTTPServer, int]:
    server = QuietServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]
