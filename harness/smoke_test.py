"""smoke_test.py - does the endpoint return a parsed, schema-valid tool call?

Usage:
  LLM_BASE_URL=https://<POD_ID>-8000.proxy.runpod.net/v1 LLM_API_KEY=... \
      python smoke_test.py
"""
import json
import os

from openai import OpenAI

client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"])
tools = [{"type": "function", "function": {
    "name": "write_file", "description": "Create a text file in the workspace.",
    "strict": True,
    "parameters": {"type": "object", "additionalProperties": False,
                   "required": ["path", "content"],
                   "properties": {"path": {"type": "string"},
                                  "content": {"type": "string"}}}}}]
prompt = os.environ.get("SMOKE_PROMPT",
                        "Save the text 'hello' in notes/a.txt with the tool.")
reply = client.chat.completions.create(
    model=os.environ.get("LLM_MODEL", "agent-model"), max_tokens=512,
    messages=[{"role": "user", "content": prompt}], tools=tools, tool_choice="auto")
message = reply.choices[0].message
calls = message.tool_calls or []
assert calls, f"no parsed tool call; raw content was: {message.content!r}"
args = json.loads(calls[0].function.arguments)
assert set(args) == {"path", "content"}, f"arguments do not match the schema: {args}"
print("OK", calls[0].function.name, args)
