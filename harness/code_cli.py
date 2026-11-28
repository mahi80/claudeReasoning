from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import sys
import uuid

import coding
import delivery_tools
import integrations
import mini_harness as h
import pod_manager

EXIT = {"accepted": 0, "rejected": 1, "stopped": 2, "failed": 3}


def progress(record: dict) -> None:
    event = record["event"]
    if event == "coding_stage":
        print(f"Coding: {record['stage']}", file=sys.stderr, flush=True)
    elif event == "check":
        print(f"Check {record['name']}: exit={record['exit']}", file=sys.stderr, flush=True)
    elif event == "coding_review":
        print("Review: " + ("passed" if record["passed"] else "rejected"), file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verified coding tasks using the configured DeepSeek/OpenAI-compatible endpoint.")
    parser.add_argument("task", nargs="*")
    parser.add_argument("--interactive", action="store_true", help="read successive tasks; /exit quits")
    parser.add_argument("--config", default=os.environ.get("AGENT_DELIVERY_CONFIG", ""), help="operator-owned checks config outside the workspace")
    parser.add_argument("--effort", choices=h.LADDER, default="high")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--result", default="", help="write the latest structured result outside the editable workspace")
    args = parser.parse_args(argv)
    initial = " ".join(args.task).strip()
    if not args.config:
        parser.error("--config or AGENT_DELIVERY_CONFIG is required")
    if not initial and not args.interactive:
        parser.error("a task or --interactive is required")
    if args.run_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.run_id):
        parser.error("--run-id must contain 1-64 letters, digits, underscores or hyphens")
    if args.resume and (not args.run_id or args.interactive):
        parser.error("--resume requires --run-id and a one-shot task")
    if args.interactive and args.run_id:
        parser.error("interactive tasks get separate run IDs; --run-id is one-shot only")
    result_path = Path(args.result).resolve() if args.result else None
    if result_path and (result_path.is_relative_to(h.WORKSPACE.resolve()) or not result_path.parent.is_dir()):
        parser.error("--result must have an existing parent outside the workspace")

    def approve(name: str, arguments: dict) -> bool:
        if not args.interactive and not sys.stdin.isatty():
            return False
        print(f"Approval requested: {name}\n{json.dumps(arguments, ensure_ascii=True)}", file=sys.stderr, flush=True)
        try:
            return input("Type yes to approve; anything else denies: ").strip().lower() == "yes"
        except EOFError:
            return False

    old_operator = h.ask_operator
    tools = []
    h.ask_operator = approve
    h.LISTENERS.append(progress)
    status = 0
    try:
        h.WORKSPACE.mkdir(parents=True, exist_ok=True)
        coding.configure(args.config)
        if h.MCP_CONFIG:
            import mcp_bridge
            tools.extend(mcp_bridge.load_config(h.MCP_CONFIG))
        config = os.environ.get("AGENT_INTEGRATIONS_CONFIG", "")
        if config:
            tools.extend(integrations.load_config(config))
        message = initial
        while True:
            if not message:
                if not args.interactive:
                    break
                try:
                    message = input("coding> ").strip()
                except EOFError:
                    break
                if message in {"/exit", "/quit"}:
                    break
                if not message:
                    continue
            token = h.RUN_ID.set(args.run_id or uuid.uuid4().hex[:12])
            try:
                pod_manager.ensure_ready(lambda text: print(text, file=sys.stderr, flush=True))
                result = coding.run(message, effort=args.effort, resume=args.resume, extra_tools=tuple(tools))
                print(f"{result.status.upper()} [{h.RUN_ID.get()}]\n{result.answer}", flush=True)
                for row in result.checks:
                    print(f"Check {row['name']}: exit={row['exit']} ({row['seconds']}s)", flush=True)
                if result.review:
                    print("Independent review:\n" + h.clip(result.review, 2000), flush=True)
                if result_path:
                    result_path.write_text(json.dumps({"run": h.RUN_ID.get(), "effort": args.effort,
                                                       **asdict(result)}, indent=2, ensure_ascii=True), encoding="utf-8")
                status = EXIT[result.status]
            finally:
                pod_manager.touch()
                h.RUN_ID.reset(token)
            if not args.interactive:
                break
            message = ""
        return status
    except KeyboardInterrupt:
        print("Interrupted; inspect workspace changes and the checkpoint before resuming.", file=sys.stderr)
        return 130
    except Exception as err:
        print(f"Coding client failed: {type(err).__name__}", file=sys.stderr)
        return 3
    finally:
        h.ask_operator = old_operator
        h.LISTENERS.remove(progress)
        integrations.close()
        delivery_tools.close()
        if h.MCP_CONFIG:
            import mcp_bridge
            mcp_bridge.close()
        h.client.close()


if __name__ == "__main__":
    sys.exit(main())
