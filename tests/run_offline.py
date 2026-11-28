"""run_offline.py - run the test scripts one by one and report one line per script.

    python tests/run_offline.py                    # every tests/test_*.py except the browser suite
    python tests/run_offline.py test_delivery      # only the named scripts
    python tests/run_offline.py --browser          # only the browser suite; a skip is a failure

Every script runs in its own process with this interpreter, so the mock servers,
environment variables and temporary folders of one script cannot leak into the next.
Scripts are found by name, so a new tests/test_*.py runs here and in CI without editing
this file or the workflow. Child processes get NO_PROXY and no_proxy set to the loopback
hosts, because every suite talks only to local mock servers, and no stdin, so nothing
can wait for an answer. In GitHub Actions each script's output is folded into a log
group, failures become annotations, and a table goes to the job summary.

Exit code 0 when every script passed, 1 when any failed, timed out, skipped where a
skip is not allowed, or when no script matched.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
BROWSER = "test_ui_browser.py"
LOOPBACK = "127.0.0.1,localhost"
TIMEOUT = float(os.environ.get("TEST_SCRIPT_TIMEOUT", "1200"))     # seconds per script
IN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"


def discover(names: list[str], browser: bool) -> list[Path]:
    """The scripts to run: the named ones, the browser suite, or every other test_*.py."""
    found = sorted(TESTS.glob("test_*.py"))
    if names:
        wanted = {n if n.endswith(".py") else f"{n}.py" for n in names}
        wanted = {n if n.startswith("test_") else f"test_{n}" for n in wanted}
        return [p for p in found if p.name in wanted]
    return [p for p in found if (p.name == BROWSER) == browser]


def tally(output: str) -> str:
    """'126/126' from a script's own summary line, its PASS and FAIL lines, or unittest's report."""
    totals = re.findall(r"^(\d+)/(\d+) [\w -]*checks? passed", output, re.MULTILINE)
    if totals:
        return f"{totals[-1][0]}/{totals[-1][1]}"
    passed = len(re.findall(r"^PASS ", output, re.MULTILINE))
    failed = len(re.findall(r"^FAIL ", output, re.MULTILINE))
    if passed or failed:
        return f"{passed}/{passed + failed}"
    ran = re.findall(r"^Ran (\d+) tests? in", output, re.MULTILINE)
    if ran:
        total = int(ran[-1])
        bad = sum(int(n) for n in re.findall(r"(?:failures|errors)=(\d+)", output.rsplit("Ran ", 1)[-1]))
        return f"{total - bad}/{total}"
    return "-"


def run(path: Path) -> dict:
    """Run one script, echoing its output as it comes, and return what happened."""
    env = {**os.environ, "NO_PROXY": LOOPBACK, "no_proxy": LOOPBACK, "PYTHONUNBUFFERED": "1"}
    started = time.monotonic()
    proc = subprocess.Popen([sys.executable, str(path)], cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines: list[str] = []

    def pump() -> None:
        for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace")
            lines.append(line)
            sys.stdout.write(line)
            sys.stdout.flush()

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    try:
        code = proc.wait(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        code = None
    reader.join(timeout=10)
    output = "".join(lines)
    return {"name": path.name, "code": code, "seconds": time.monotonic() - started, "output": output,
            "skipped": output.lstrip().startswith("SKIP"), "tally": tally(output)}


def verdict(result: dict, skip_allowed: bool) -> str:
    if result["code"] is None:
        return f"timed out after {TIMEOUT:.0f} s"
    if result["code"] != 0:
        return f"failed (exit {result['code']})"
    if result["skipped"]:
        reason = result["output"].strip().splitlines()[0]
        return "skipped" if skip_allowed else f"skipped, which counts as a failure here: {reason}"
    return "passed"


def summary(results: list[dict], skip_allowed: bool) -> tuple[str, str, bool]:
    """A plain table for the console, a Markdown table for the job summary, and the overall result."""
    rows = [(r["name"], verdict(r, skip_allowed), r["tally"], f"{r['seconds']:.1f}") for r in results]
    ok = bool(results) and all(v in ("passed", "skipped") for _, v, _, _ in rows)
    width = max([len(name) for name, *_ in rows] + [6])
    plain = [f"{'script':<{width}}  {'checks':>8}  {'seconds':>8}  result"]
    plain += [f"{name:<{width}}  {checks:>8}  {secs:>8}  {v}" for name, v, checks, secs in rows]
    md = ["| Script | Result | Checks | Seconds |", "|---|---|---:|---:|"]
    md += [f"| `{name}` | {v} | {checks} | {secs} |" for name, v, checks, secs in rows]
    passed = sum(1 for _, v, _, _ in rows if v == "passed")
    plain.append(f"\n{passed}/{len(rows)} scripts passed")
    md.append(f"\n**{passed}/{len(rows)} scripts passed** with Python {sys.version.split()[0]} on {sys.platform}.")
    return "\n".join(plain), "\n".join(md), ok


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description="Run the test scripts one by one.")
    cli.add_argument("names", nargs="*", help="scripts to run, for example test_delivery or delivery")
    cli.add_argument("--browser", action="store_true", help="run only the browser suite; a skip fails")
    args = cli.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")         # a console that cannot show a character
    except (AttributeError, ValueError):
        pass
    paths = discover(args.names, args.browser)
    if not paths:
        print(f"no test script matched {args.names or ('the browser suite' if args.browser else 'tests/test_*.py')}")
        return 1
    skip_allowed = not args.browser and not args.names
    results = []
    for path in paths:
        print(f"::group::{path.name}" if IN_ACTIONS else f"\n===== {path.name} =====", flush=True)
        result = run(path)
        if IN_ACTIONS:
            print("::endgroup::", flush=True)
        state = verdict(result, skip_allowed)
        if state not in ("passed", "skipped"):
            print(f"::error title={path.name}::{state}" if IN_ACTIONS else f"!! {path.name}: {state}", flush=True)
        results.append(result)
    plain, markdown, ok = summary(results, skip_allowed)
    print("\n" + plain)
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
