"""agent_cases.py - the agent eval set: 18 tasks that need care, not just a tool call.

Each case is a task, the files it starts from, and a check written in Python. The check
runs in the workspace with the agent's final answer on stdin and exits 0 for a pass.
Every expected value is computed here from the case's own data, and every case has a
reference solution, so tests/test_eval_cases.py can prove that each check passes on a
correct result and fails on the untouched files.

The agent needs no shell command that changes anything: the file tools and the
read-only commands are enough. The checks do run code the agent edited, so run the set
in a throwaway workspace.

    python evals/agent_cases.py        # rewrite evals/tasks.agent.jsonl from this file
"""
from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

CASES: list[dict] = []

PRELUDE = '''import csv, hashlib, io, json, pathlib, subprocess, sys


def text(path):
    p = pathlib.Path(path)
    if not p.is_file():
        sys.exit(f"missing {path}")
    return p.read_text()


def lines(path):
    return [line.rstrip() for line in text(path).strip().splitlines()]


def number(raw):
    return float(str(raw).strip().replace(",", "").lstrip("$"))


def unchanged(path, digest):
    if hashlib.sha256(text(path).encode()).hexdigest() != digest:
        sys.exit(f"{path} was edited")

'''


def sha(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def case(name: str, task: str, files: dict[str, str], check: str,
         solve: Callable[[Path], str]) -> None:
    CASES.append({"id": name, "task": task, "files": files, "check_py": PRELUDE + check,
                  "solve": solve})


def put(root: Path, path: str, content: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def writes(path: str, content: str) -> Callable[[Path], str]:
    """A reference solution that only has to write one file."""
    def solve(root: Path) -> str:
        put(root, path, content)
        return "done"
    return solve


def run_files(files: dict[str, str], script: str) -> str:
    """Output of one of the case's own scripts, used as the expected value."""
    with tempfile.TemporaryDirectory() as tmp:
        for path, content in files.items():
            put(Path(tmp), path, content)
        return subprocess.run([sys.executable, script], cwd=tmp, capture_output=True,
                              text=True, check=True, timeout=60).stdout


# ---------------------------------------------------------------- 1. arithmetic on a filter
SALES = [(1, "north", 1240.50), (2, "south", 310.00), (3, "north", 89.99),
         (4, "east", 1500.00), (5, "north", 402.10), (6, "west", 77.25),
         (7, "north", 2310.00), (8, "south", 45.60), (9, "north", 18.41),
         (10, "east", 960.00), (11, "north", 755.00), (12, "west", 1200.00),
         (13, "north", 64.35), (14, "south", 980.10)]
NORTH = round(sum(amount for _, region, amount in SALES if region == "north"), 2)
case("sum-region",
     "sales.csv lists sales by region. Work out the total amount for the region north and "
     "write only that number, with two decimals, to out/north_total.txt.",
     {"sales.csv": "id,region,amount\n" + "".join(f"{i},{r},{a:.2f}\n" for i, r, a in SALES)},
     f'''got = number(text("out/north_total.txt"))
if abs(got - {NORTH!r}) > 0.005:
    sys.exit(f"total is {{got}}")
''',
     writes("out/north_total.txt", f"{NORTH:.2f}\n"))

# ---------------------------------------------------------------- 2. a running balance
LEDGER = [(1, "credit", 1200.00), (2, "debit", 349.99), (3, "debit", 75.50),
          (4, "credit", 89.25), (5, "debit", 1410.00), (6, "debit", 12.75),
          (7, "credit", 640.10), (8, "debit", 990.40), (9, "credit", 15.00),
          (10, "debit", 1409.99), (11, "credit", 2300.00), (12, "debit", 208.30),
          (13, "debit", 66.66), (14, "credit", 410.05)]
OPENING = 2500.00
CLOSING = round(OPENING + sum(a if kind == "credit" else -a for _, kind, a in LEDGER), 2)
BIGGEST = max((a, i) for i, kind, a in LEDGER if kind == "debit")[1]
case("ledger",
     "ledger.csv has one transaction per line. The opening balance is 2500.00. Write "
     "out/ledger.json with two keys: closing, the closing balance as a number, and "
     "largest_debit_id, the id of the largest single debit.",
     {"ledger.csv": "id,type,amount\n" + "".join(f"{i},{k},{a:.2f}\n" for i, k, a in LEDGER)},
     f'''got = json.loads(text("out/ledger.json"))
if abs(number(got["closing"]) - {CLOSING!r}) > 0.005:
    sys.exit(f"closing is {{got['closing']}}")
if str(got["largest_debit_id"]).strip() != "{BIGGEST}":
    sys.exit(f"largest debit is {{got['largest_debit_id']}}")
''',
     writes("out/ledger.json", json.dumps(
         {"closing": CLOSING, "largest_debit_id": BIGGEST})))

# ---------------------------------------------------------------- 3. two bugs, tests given
STATS_BUGGY = '''def moving_average(values, window):
    """Return the average of each run of `window` consecutive values."""
    if window <= 0:
        raise ValueError("window must be positive")
    out = []
    for i in range(len(values) - window):
        chunk = values[i:i + window]
        out.append(sum(chunk) / window)
    return out


def median(values):
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid] + ordered[mid + 1]) / 2
'''
STATS_FIXED = (STATS_BUGGY.replace("range(len(values) - window)", "range(len(values) - window + 1)")
               .replace("(ordered[mid] + ordered[mid + 1]) / 2",
                        "(ordered[mid - 1] + ordered[mid]) / 2"))
STATS_TEST = '''from stats import median, moving_average


def test_moving_average():
    assert moving_average([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]
    assert moving_average([5, 5, 5], 3) == [5.0]
    assert moving_average([1, 2], 3) == []


def test_median():
    assert median([3, 1, 2]) == 2
    assert median([4, 1, 3, 2]) == 2.5
    assert median([7]) == 7
    assert median([10, 2, 8, 4, 6, 12]) == 7.0


if __name__ == "__main__":
    test_moving_average()
    test_median()
    print("all tests passed")
'''
case("fix-stats",
     "test_stats.py fails. Fix stats.py so that every test passes. Do not edit "
     "test_stats.py.",
     {"stats.py": STATS_BUGGY, "test_stats.py": STATS_TEST},
     f'''unchanged("test_stats.py", "{sha(STATS_TEST)}")
run = subprocess.run([sys.executable, "test_stats.py"], capture_output=True, text=True, timeout=60)
if run.returncode:
    sys.exit(run.stderr[-300:])
''',
     writes("stats.py", STATS_FIXED))


# ---------------------------------------------------------------- 4. implement to a spec
def slugify(title: str, max_length: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not slug:
        return "untitled"
    if len(slug) <= max_length:
        return slug
    cut = slug.rfind("-", 0, max_length + 1)
    return slug[:cut] if cut > 0 else slug[:max_length]


SLUG_STUB = '''def slugify(title, max_length=40):
    """Turn a title into a URL slug.

    Rules:
    1. Lower-case everything.
    2. Every run of characters that are not a-z or 0-9 becomes one hyphen.
    3. No hyphen at the start or at the end.
    4. If the slug is longer than max_length, cut it at the last hyphen that keeps it
       within max_length, so that no word is cut in half. If the first word alone is
       longer than max_length, cut that word to max_length characters.
    5. A title with no letters or digits gives the string "untitled".
    """
    raise NotImplementedError
'''
SLUG_SOLUTION = '''import re


def slugify(title, max_length=40):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not slug:
        return "untitled"
    if len(slug) <= max_length:
        return slug
    cut = slug.rfind("-", 0, max_length + 1)
    return slug[:cut] if cut > 0 else slug[:max_length]
'''
SLUG_INPUTS = [("Hello, World!",), ("  Leading and trailing  ",), ("Cafe au lait & more",),
               ("A" * 50,), ("The quick brown fox jumps over the lazy dog again",),
               ("!!!",), ("",), ("Version 2.0 -- Release Notes",),
               ("one two three four five six seven eight nine ten",),
               ("x" * 40 + " tail",), ("alpha beta gamma", 10), ("alphabet soup", 5)]
SLUG_WANT = [[list(args), slugify(*args)] for args in SLUG_INPUTS]
case("slugify",
     "textutil.py contains a function that is not written yet. Implement slugify so that "
     "it follows every rule in its docstring. Keep the function name and its arguments.",
     {"textutil.py": SLUG_STUB},
     f'''sys.path.insert(0, ".")
try:
    from textutil import slugify
except Exception as err:
    sys.exit(f"import failed: {{err}}")
for args, want in {SLUG_WANT!r}:
    try:
        got = slugify(*args)
    except Exception as err:
        sys.exit(f"slugify{{tuple(args)}} raised {{type(err).__name__}}")
    if got != want:
        sys.exit(f"slugify{{tuple(args)}} gave {{got!r}}, expected {{want!r}}")
''',
     writes("textutil.py", SLUG_SOLUTION))

# ---------------------------------------------------------------- 5. a rename across files
RENAME = {
    "pricing.py": '''"""Price helpers."""

TAX_RATES = {"standard": 0.2, "reduced": 0.05}


def calc_total(items, tax_rate):
    """Sum quantity * unit price for every item, then add tax."""
    net = sum(qty * price for qty, price in items)
    return round(net * (1 + tax_rate), 2)
''',
    "cart.py": '''from pricing import TAX_RATES, calc_total


class Cart:
    def __init__(self):
        self.items = []

    def add(self, qty, price):
        self.items.append((qty, price))

    def total(self, band="standard"):
        # calc_total already rounds to cents
        return calc_total(self.items, TAX_RATES[band])
''',
    "report.py": '''import pricing


def line(label, items, band):
    total = pricing.calc_total(items, pricing.TAX_RATES[band])
    return f"{label}: {total:.2f}"
''',
    "main.py": '''from cart import Cart
from report import line

cart = Cart()
cart.add(2, 9.99)
cart.add(1, 24.50)
print(cart.total())
print(cart.total("reduced"))
print(line("bulk", [(10, 3.2), (4, 12.75)], "standard"))
''',
}
RENAME_OUTPUT = run_files(RENAME, "main.py")


def solve_rename(root: Path) -> str:
    for path, content in RENAME.items():
        put(root, path, content.replace("calc_total", "compute_total"))
    return "renamed"


case("rename-function",
     "Rename the function calc_total to compute_total everywhere in the Python files, "
     "comments included. The program's behaviour must not change.",
     RENAME,
     f'''for path in sorted(pathlib.Path(".").glob("*.py")):
    if "calc_total" in path.read_text():
        sys.exit(f"{{path}} still mentions calc_total")
if "def compute_total(" not in text("pricing.py"):
    sys.exit("pricing.py does not define compute_total")
run = subprocess.run([sys.executable, "main.py"], capture_output=True, text=True, timeout=60)
if run.returncode or run.stdout != {RENAME_OUTPUT!r}:
    sys.exit("main.py output changed: " + (run.stderr[-200:] or run.stdout))
''',
     solve_rename)


# ---------------------------------------------------------------- 6. merge by written rules
def merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if value is None:
            out.pop(key, None)
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        elif isinstance(value, list) and isinstance(out.get(key), list):
            out[key] = out[key] + [v for v in value if v not in out[key]]
        else:
            out[key] = value
    return out


BASE = {"service": {"name": "billing", "port": 8080,
                    "tls": {"enabled": False, "cert": "/etc/certs/old.pem"},
                    "tags": ["core", "payments"]},
        "retries": 3, "regions": ["eu-west", "us-east"], "debug": True, "owners": ["ana"]}
OVERRIDE = {"service": {"port": 9090, "tls": {"enabled": True, "cert": None},
                        "tags": ["payments", "pci"]},
            "retries": None, "regions": ["us-east", "ap-south"], "timeout_s": 30,
            "owners": ["raj", "ana", "li"]}
MERGED = merge(BASE, OVERRIDE)
case("config-merge",
     "Merge override.json into base.json by the rules in MERGE_RULES.md and write the "
     "result to merged.json.",
     {"base.json": json.dumps(BASE, indent=2) + "\n",
      "override.json": json.dumps(OVERRIDE, indent=2) + "\n",
      "MERGE_RULES.md": "# Merge rules\n\n"
                        "1. A key in the override replaces the same key in the base.\n"
                        "2. When both values are objects, merge them key by key with these "
                        "same rules.\n"
                        "3. When both values are lists, keep the base items in order, then "
                        "add each override item that is not already in the list.\n"
                        "4. A key whose override value is null is removed from the result.\n"
                        "5. Keys that only the base has are kept.\n"},
     f'''got = json.loads(text("merged.json"))
want = json.loads({json.dumps(MERGED)!r})
if got != want:
    wrong = sorted(k for k in set(got) | set(want) if got.get(k) != want.get(k))
    sys.exit(f"merged.json differs at: {{wrong}}")
''',
     writes("merged.json", json.dumps(MERGED, indent=2)))

# ---------------------------------------------------------------- 7. counting in a log
_rng = random.Random(7)
_paths = ["/api/orders", "/api/users", "/api/cart", "/api/search", "/health"]
_weights = {"/api/orders": [200] * 9 + [500, 503, 404],
            "/api/users": [200] * 10 + [502, 404, 401],
            "/api/cart": [200] * 7 + [500, 500, 503, 502, 404],
            "/api/search": [200] * 11 + [500, 429],
            "/health": [200] * 12}
LOG_ROWS = []
for n in range(170):
    path = _rng.choice(_paths)
    LOG_ROWS.append((f"2026-11-20T10:{n // 60:02d}:{n % 60:02d}Z", _rng.choice(["GET", "POST"]),
                     path, _rng.choice(_weights[path]), _rng.randint(4, 900)))
_errors: dict[str, int] = {}
for _, _, path, status, _ in LOG_ROWS:
    if status >= 500:
        _errors[path] = _errors.get(path, 0) + 1
_ranked = sorted(_errors.items(), key=lambda item: -item[1])
assert _ranked[0][1] > _ranked[1][1], "the busiest path must be unique"
LOG_ANSWER = f"{_ranked[0][0]} {_ranked[0][1]}"
case("log-errors",
     "access.log has one request per line: time, method, path, status, duration. Which "
     "path has the most responses with a 5xx status, and how many? Write the path and "
     "the count, separated by one space, to out/answer.txt.",
     {"access.log": "".join(f"{t} {m} {p} {s} {d}ms\n" for t, m, p, s, d in LOG_ROWS)},
     f'''got = " ".join(text("out/answer.txt").split())
if got != {LOG_ANSWER!r}:
    sys.exit(f"answer is {{got!r}}")
''',
     writes("out/answer.txt", LOG_ANSWER + "\n"))

# ---------------------------------------------------------------- 8. an order that respects needs
NEEDS = {"deploy": ["package", "migrate"], "package": ["build", "test"],
         "build": ["compile", "assets"], "compile": ["fetch"], "assets": ["fetch"],
         "test": ["compile", "fixtures"], "fixtures": ["fetch"], "migrate": ["backup"],
         "backup": [], "fetch": [], "notify": ["deploy"], "docs": ["build"]}
_listing = ["notify", "docs", "deploy", "test", "package", "assets", "migrate", "build",
            "fixtures", "compile", "backup", "fetch"]
_order = ["fetch", "backup", "compile", "assets", "fixtures", "build", "test", "migrate",
          "package", "docs", "deploy", "notify"]
case("build-order",
     "tasks.txt lists build tasks. Each line is a task, a colon, then the tasks it needs "
     "first. Write an order in which all of them can run to out/order.txt, one task per "
     "line, every task exactly once, each after everything it needs.",
     {"tasks.txt": "".join(f"{t}: {', '.join(NEEDS[t])}".rstrip() + "\n" for t in _listing)},
     f'''needs = {NEEDS!r}
order = [line.strip() for line in lines("out/order.txt") if line.strip()]
if sorted(order) != sorted(needs):
    sys.exit("the order does not list every task exactly once")
for i, task in enumerate(order):
    late = [n for n in needs[task] if order.index(n) > i]
    if late:
        sys.exit(f"{{task}} runs before {{late}}")
''',
     writes("out/order.txt", "\n".join(_order) + "\n"))

# ---------------------------------------------------------------- 9. a small scheduling puzzle
SLOTS = ["09:00", "10:00", "11:00", "12:00", "13:00"]
TALKS = ["A", "B", "C", "D", "E"]


def schedule_ok(plan: dict) -> bool:
    try:
        at = {t: SLOTS.index(plan[t]) for t in TALKS}
    except (KeyError, ValueError):
        return False
    return (sorted(at.values()) == [0, 1, 2, 3, 4] and at["A"] < at["C"]
            and at["D"] == at["B"] + 1 and at["E"] in (2, 3) and at["B"] != 0
            and at["C"] != 4)


_plans = [dict(zip(TALKS, (SLOTS[i] for i in p))) for p in itertools.permutations(range(5))]
_plans = [p for p in _plans if schedule_ok(p)]
assert _plans, "the puzzle must have a solution"
case("schedule",
     "Five talks, A to E, each need one of five slots: 09:00, 10:00, 11:00, 12:00 and "
     "13:00, one talk per slot. A is earlier than C. D is in the slot directly after B. "
     "E is at 11:00 or 12:00. B is not at 09:00. C is not at 13:00. Write a schedule "
     'that meets every rule to schedule.json, as an object such as {"A": "09:00", ...}.',
     {},
     f'''slots, talks = {SLOTS!r}, {TALKS!r}
plan = json.loads(text("schedule.json"))
try:
    at = {{t: slots.index(str(plan[t]).strip()) for t in talks}}
except (KeyError, ValueError) as err:
    sys.exit(f"bad schedule: {{err}}")
rules = {{"one talk per slot": sorted(at.values()) == [0, 1, 2, 3, 4],
         "A before C": at["A"] < at["C"], "D directly after B": at["D"] == at["B"] + 1,
         "E at 11:00 or 12:00": at["E"] in (2, 3), "B not at 09:00": at["B"] != 0,
         "C not at 13:00": at["C"] != 4}}
broken = [name for name, ok in rules.items() if not ok]
if broken:
    sys.exit(f"rules broken: {{broken}}")
''',
     writes("schedule.json", json.dumps(_plans[0])))

# ---------------------------------------------------------------- 10. dates in four formats
PEOPLE = [("Asha Rao", "05/03/2024", "2024-03-05", "platform"),
          ("Ben Ortiz", "5 March 2024", "2024-03-05", "data"),
          ("Chen Wei", "2023.11.09", "2023-11-09", "platform"),
          ("Dara Singh", "Mar 17 2022", "2022-03-17", "design"),
          ("Emeka Obi", "12/01/2022", "2022-01-12", "data"),
          ("Farah Khan", "1 December 2021", "2021-12-01", "support"),
          ("Goran Ilic", "2024.02.29", "2024-02-29", "design"),
          ("Hana Sato", "Jul 4 2023", "2023-07-04", "platform"),
          ("Ivo Marek", "03/04/2023", "2023-04-03", "support"),
          ("Jaya Nair", "30 June 2020", "2020-06-30", "data")]
PEOPLE_CLEAN = [["name", "joined", "team"]] + [[n, iso, team] for n, _, iso, team in PEOPLE]


def as_csv(rows: list[list[str]]) -> str:
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(rows)
    return out.getvalue()


case("clean-dates",
     "people.csv has a joined column written in four ways: DD/MM/YYYY, such as "
     "05/03/2024 for 5 March 2024; 5 March 2024; 2024.03.05; and Mar 5 2024. Write "
     "people_clean.csv with the same rows in the same order and every date as "
     "YYYY-MM-DD. Change nothing else.",
     {"people.csv": as_csv([["name", "joined", "team"]]
                           + [[n, raw, team] for n, raw, _, team in PEOPLE])},
     f'''table = csv.reader(io.StringIO(text("people_clean.csv")))
rows = [[cell.strip() for cell in row] for row in table if row]
want = {PEOPLE_CLEAN!r}
if rows != want:
    bad = [r for r, w in zip(rows, want) if r != w][:3]
    sys.exit(f"{{len(rows)}} rows, first differences: {{bad}}")
''',
     writes("people_clean.csv", as_csv(PEOPLE_CLEAN)))

# ---------------------------------------------------------------- 11. six precise edits
CONF = """# service configuration
name = orders-api
port = 8080
workers = 4
log_level = info
timeout_s = 30
cache = redis
cache_ttl_s = 300
# feature flags
flag_new_checkout = off
flag_bulk_export = off
max_upload_mb = 25
region = eu-west
"""
CONF_WANT = """# service configuration
name = orders-api
port = 8080
workers = 8
log_level = info
request_timeout_s = 30
cache = redis
# feature flags
flag_new_checkout = on
flag_bulk_export = off
flag_audit_log = on
max_upload_mb = 25
# moved 2026-11-27
region = ap-south
"""
case("apply-changes",
     "Apply every change listed in CHANGES.md to service.conf. Leave all other lines as "
     "they are.",
     {"service.conf": CONF,
      "CHANGES.md": "# Changes for this release\n\n"
                    "1. Set workers to 8.\n"
                    "2. Rename the key timeout_s to request_timeout_s. Keep its value.\n"
                    "3. Delete the line for cache_ttl_s.\n"
                    "4. Turn flag_new_checkout on.\n"
                    "5. Add the line `flag_audit_log = on` directly after the "
                    "flag_bulk_export line.\n"
                    "6. Change region to ap-south, and add the comment line "
                    "`# moved 2026-11-27` directly above it.\n"},
     f'''got, want = lines("service.conf"), {CONF_WANT.strip().splitlines()!r}
if got != want:
    extra = [line for line in got if line not in want]
    lost = [line for line in want if line not in got]
    sys.exit(f"unexpected lines {{extra}}, missing lines {{lost}}")
''',
     writes("service.conf", CONF_WANT))

# ---------------------------------------------------------------- 12. facts among look-alikes
OFFICES = {"Lisbon": (46, 140, 36, 10, "R. Almeida"), "Pune": (31, 95, 30, 14, "S. Kulkarni"),
           "Austin": (58, 210, 36, 7, "J. Whitfield"), "Osaka": (52, 175, 24, 21, "K. Tanaka"),
           "Leeds": (44, 160, 30, 10, "M. Okafor"), "Turin": (47, 150, 42, 12, "G. Ferraro")}
HANDBOOK = "# Travel and equipment handbook\n\nRates are per person. Amounts are in euros.\n"
for _office, (_meal, _hotel, _laptop, _notice, _who) in OFFICES.items():
    HANDBOOK += (
        f"\n## {_office} office\n\n"
        f"### Travel\n"
        f"- Daily meal allowance: {_meal}\n"
        f"- Hotel cap per night: {_hotel}\n"
        f"- A stay above the hotel cap needs written approval from {_who}.\n"
        f"- Book at least {_notice + 4} days ahead for flights.\n\n"
        f"### Equipment\n"
        f"- Laptops are refreshed every {_laptop} months.\n"
        f"- Monitors are refreshed every {_laptop + 24} months.\n\n"
        f"### Leave\n"
        f"- Give {_notice} working days of notice for planned leave.\n"
        f"- Leave of more than {_notice + 1} days needs approval from the office lead.\n")
_top = max(OFFICES, key=lambda office: OFFICES[office][1])
HANDBOOK_ANSWERS = {"q1": OFFICES["Osaka"][0], "q2": OFFICES["Leeds"][4],
                    "q3": OFFICES["Pune"][2], "q4": _top}
case("handbook",
     "Answer the four questions in questions.txt from handbook.md. Write answers.json "
     "with the keys q1, q2, q3 and q4. Give numbers as numbers and names exactly as the "
     "handbook writes them.",
     {"handbook.md": HANDBOOK,
      "questions.txt": "q1: What is the daily meal allowance for the Osaka office?\n"
                       "q2: Who approves a stay above the hotel cap for the Leeds office?\n"
                       "q3: After how many months are laptops refreshed in the Pune office?\n"
                       "q4: Which office has the highest hotel cap per night?\n"},
     f'''got, want = json.loads(text("answers.json")), {HANDBOOK_ANSWERS!r}
plain = lambda value: str(value).strip().lower().removesuffix(" office")   # "Austin office" is fine
wrong = [f"{{k}}={{got.get(k)!r}}" for k in want if plain(got.get(k, "")) != plain(want[k])]
if wrong:
    sys.exit(f"wrong answers: {{wrong}}")
''',
     writes("answers.json", json.dumps(HANDBOOK_ANSWERS)))

# ---------------------------------------------------------------- 13. two files that disagree
ORDERS = [(1001, "A-1", 5), (1002, "B-2", 12), (1003, "C-3", 1), (1004, "A-1", 20),
          (1005, "D-4", 7), (1006, "B-2", 3), (1007, "E-5", 40), (1008, "C-3", 9)]
SHIPMENTS = [("S1", 1001, 5), ("S2", 1002, 6), ("S3", 1004, 10), ("S4", 1007, 20),
             ("S5", 1005, 7), ("S6", 1002, 6), ("S7", 1006, 3), ("S8", 1010, 2),
             ("S9", 1007, 10), ("S10", 1004, 5), ("S11", 1006, 1), ("S12", 1008, 9),
             ("S13", 1007, 10)]
_shipped = {order: sum(q for _, o, q in SHIPMENTS if o == order) for order, _, _ in ORDERS}
MISMATCH = [str(order) for order, _, qty in ORDERS if _shipped[order] != qty]
case("order-mismatch",
     "orders.csv lists what was ordered and shipments.csv what was shipped; one order can "
     "ship in several parts. List every order_id whose total shipped quantity differs "
     "from the quantity ordered. An order with no shipment counts as different. Ignore "
     "shipments for an order_id that is not in orders.csv. Write the ids in ascending "
     "order, one per line, to out/mismatch.txt.",
     {"orders.csv": "order_id,sku,qty\n" + "".join(f"{o},{s},{q}\n" for o, s, q in ORDERS),
      "shipments.csv": "shipment_id,order_id,qty\n"
                       + "".join(f"{s},{o},{q}\n" for s, o, q in SHIPMENTS)},
     f'''got = [line.strip() for line in lines("out/mismatch.txt") if line.strip()]
if got != {MISMATCH!r}:
    sys.exit(f"listed {{got}}")
''',
     writes("out/mismatch.txt", "\n".join(MISMATCH) + "\n"))

# ---------------------------------------------------------------- 14. run a program in your head
PROGRAM = '''def step(n):
    return n // 2 if n % 2 == 0 else 3 * n + 1


def chain(n):
    length = 1
    while n != 1:
        n = step(n)
        length += 1
    return length


words = ["delta", "alpha", "charlie", "bravo", "echo"]
score = {}
for i, w in enumerate(sorted(words)):
    score[w] = chain(len(w) + i) + w.count("a")

best = max(score, key=lambda w: (score[w], w))
print(best)
print(sum(score.values()))
print(",".join(w[0] for w in sorted(score, key=score.get)))
'''
PROGRAM_OUTPUT = run_files({"program.py": PROGRAM}, "program.py")
case("trace-program",
     "Work out what program.py prints when it runs, without changing the file. Write "
     "the exact output, line for line, to out/output.txt.",
     {"program.py": PROGRAM},
     f'''unchanged("program.py", "{sha(PROGRAM)}")
want = subprocess.run([sys.executable, "program.py"], capture_output=True, text=True,
                      timeout=60).stdout.strip().splitlines()
got = lines("out/output.txt")
if got != want:
    sys.exit(f"wrote {{got}}")
''',
     writes("out/output.txt", PROGRAM_OUTPUT))

# ---------------------------------------------------------------- 15. three files, three workers
MEETINGS = {
    "alpha.md": ["Move the invoice export to the nightly batch",
                 "Keep the old report layout until March",
                 "Ask finance to confirm the rounding rule"],
    "beta.md": ["Freeze the schema on Friday", "Drop support for the v1 endpoint",
                "Give the mobile team read access", "Review the alert thresholds monthly"],
    "gamma.md": ["Hire one more support engineer", "Publish the status page in two languages"],
}
_filler = ["Notes from the weekly sync.", "Attendees joined late because of a clash.",
           "There was a long discussion about priorities.", "Several options were compared.",
           "Action items will be tracked in the usual board.", "Someone asked about the budget.",
           "The demo was postponed.", "Open question: who owns the migration?",
           "A decision on tooling was deferred to next week."]
MEETING_FILES = {}
for _name, _decisions in MEETINGS.items():
    _body = [f"# Meeting notes: {_name[:-3]}", ""]
    for _n, _decision in enumerate(_decisions):
        _body += [_filler[(_n * 2 + len(_name)) % len(_filler)],
                  _filler[(_n * 2 + 1 + len(_name)) % len(_filler)],
                  f"Decision: {_decision}", ""]
    _body += [_filler[len(_decisions) % len(_filler)]]
    MEETING_FILES[f"notes/{_name}"] = "\n".join(_body) + "\n"
INDEX = [f"{name}: {len(decisions)}" for name, decisions in MEETINGS.items()]


def solve_meetings(root: Path) -> str:
    for name, decisions in MEETINGS.items():
        put(root, f"summaries/{name}", "\n".join(decisions) + "\n")
    put(root, "summaries/index.md", "\n".join(INDEX) + "\n")
    return "summarised"


case("meeting-decisions",
     "Each file in notes/ records a meeting. For each one, write summaries/<same file "
     "name> with only the decisions from that file, one per line, in the order they "
     "appear, without the word Decision. Then write summaries/index.md with one line per "
     "notes file in the form <file name>: <number of decisions>.",
     MEETING_FILES,
     f'''for name, want in {MEETINGS!r}.items():
    got = [line.lstrip("-* ").strip() for line in lines(f"summaries/{{name}}") if line.strip()]
    if got != want:
        sys.exit(f"summaries/{{name}} has {{got}}")
index = sorted(line.lstrip("-* ").strip() for line in lines("summaries/index.md") if line.strip())
if index != {sorted(INDEX)!r}:
    sys.exit(f"index has {{index}}")
''',
     solve_meetings)

# ---------------------------------------------------------------- 16. insert, touch nothing else
CHANGELOG = """# Changelog

All notable changes to this project are listed here.

## 1.3.2 - 2026-10-30
- Fix crash when the cart is empty
- Update the tax table

## 1.3.1 - 2026-10-02
- Correct rounding of totals
"""
CHANGELOG_WANT = CHANGELOG.replace(
    "## 1.3.2 - 2026-10-30",
    "## 1.4.0 - 2026-11-27\n- Add bulk export of invoices\n- Speed up the search endpoint\n\n"
    "## 1.3.2 - 2026-10-30")
case("changelog",
     "Add version 1.4.0, dated 2026-11-27, to CHANGELOG.md as the newest entry, in the "
     "same format as the existing entries, with the two items from notes.txt. Leave "
     "everything else in the file exactly as it is.",
     {"CHANGELOG.md": CHANGELOG,
      "notes.txt": "release 1.4.0\nitems:\n  Add bulk export of invoices\n"
                   "  Speed up the search endpoint\n"},
     f'''got = [line for line in lines("CHANGELOG.md") if line]
want = {[line for line in CHANGELOG_WANT.splitlines() if line]!r}
if got != want:
    sys.exit(f"changelog lines: {{got[:8]}}")
''',
     writes("CHANGELOG.md", CHANGELOG_WANT))

# ---------------------------------------------------------------- 17. units, rounding, sorting
PARCELS = [("P1", 2.5, "kg"), ("P2", 750, "g"), ("P3", 3, "lb"), ("P4", 1200, "g"),
           ("P5", 0.9, "kg"), ("P6", 10, "lb"), ("P7", 48, "g"), ("P8", 5.25, "lb")]
_factor = {"kg": 1.0, "g": 0.001, "lb": 0.45359237}
WEIGHTS = sorted(((pid, round(w * _factor[u], 2)) for pid, w, u in PARCELS),
                 key=lambda row: -row[1])
assert len({kg for _, kg in WEIGHTS}) == len(WEIGHTS), "no ties after rounding"
assert all(abs(w * _factor[u] * 100 % 1 - 0.5) > 0.02 for _, w, u in PARCELS), \
    "no value may sit on a rounding edge"
case("parcel-weights",
     "parcels.csv gives each parcel's weight in kg, g or lb. Convert every weight to "
     "kilograms (1 lb = 0.45359237 kg), round to two decimals, and write out/weights.csv "
     "with the header id,kg and one row per parcel, heaviest first.",
     {"parcels.csv": "id,weight,unit\n" + "".join(f"{p},{w},{u}\n" for p, w, u in PARCELS)},
     f'''table = csv.reader(io.StringIO(text("out/weights.csv")))
rows = [[cell.strip() for cell in row] for row in table if row]
want = {WEIGHTS!r}
if [c.lower() for c in rows[0]] != ["id", "kg"] or len(rows) != len(want) + 1:
    sys.exit(f"header or row count is wrong: {{rows[:2]}}")
for (pid, kg), (want_id, want_kg) in zip(rows[1:], want):
    if pid != want_id or abs(number(kg) - want_kg) > 0.011:
        sys.exit(f"row {{pid}},{{kg}} should be {{want_id}},{{want_kg}}")
''',
     writes("out/weights.csv", "id,kg\n" + "".join(
         f"{pid},{kg:.2f}\n" for pid, kg in WEIGHTS)))

# ---------------------------------------------------------------- 18. join, filter, rank
CUSTOMERS = [(1, "Northwind"), (2, "Globex"), (3, "Initech"), (4, "Umbrella"), (5, "Hooli"),
             (6, "Stark")]
PURCHASES = [(501, 1, 420.00, "completed"), (502, 2, 1310.50, "completed"),
             (503, 3, 88.20, "completed"), (504, 1, 975.25, "cancelled"),
             (505, 4, 640.00, "completed"), (506, 2, 99.99, "cancelled"),
             (507, 5, 1500.00, "completed"), (508, 3, 1220.80, "completed"),
             (509, 1, 310.40, "completed"), (510, 6, 2400.00, "cancelled"),
             (511, 4, 705.30, "completed"), (512, 5, 12.00, "completed"),
             (513, 3, 45.00, "completed"), (514, 1, 598.60, "completed"),
             (515, 6, 300.00, "completed"), (516, 2, 20.00, "completed")]
_spend = {name: round(sum(a for _, c, a, s in PURCHASES if c == cid and s == "completed"), 2)
          for cid, name in CUSTOMERS}
TOP3 = sorted(_spend.items(), key=lambda item: -item[1])[:3]
assert TOP3[2][1] > sorted(_spend.values(), reverse=True)[3], "third place must be clear"
case("top-customers",
     "customers.csv and orders.csv belong together through customer_id. Total the "
     "amounts of the completed orders for each customer, leaving cancelled orders out. "
     "Write the three customers with the highest totals to out/top3.csv with the header "
     "name,total, the highest first, totals with two decimals.",
     {"customers.csv": "customer_id,name\n" + "".join(f"{c},{n}\n" for c, n in CUSTOMERS),
      "orders.csv": "order_id,customer_id,amount,status\n"
                    + "".join(f"{o},{c},{a:.2f},{s}\n" for o, c, a, s in PURCHASES)},
     f'''table = csv.reader(io.StringIO(text("out/top3.csv")))
rows = [[cell.strip() for cell in row] for row in table if row]
want = {TOP3!r}
if [c.lower() for c in rows[0]] != ["name", "total"] or len(rows) != 4:
    sys.exit(f"header or row count is wrong: {{rows[:2]}}")
for (name, total), (want_name, want_total) in zip(rows[1:], want):
    if name != want_name or abs(number(total) - want_total) > 0.005:
        sys.exit(f"row {{name}},{{total}} should be {{want_name}},{{want_total}}")
''',
     writes("out/top3.csv", "name,total\n" + "".join(
         f"{name},{total:.2f}\n" for name, total in TOP3)))


def export() -> str:
    """The set as JSON Lines, without the reference solutions."""
    return "".join(json.dumps({k: c[k] for k in ("id", "task", "files", "check_py")}) + "\n"
                   for c in CASES)


if __name__ == "__main__":
    target = Path(__file__).with_name("tasks.agent.jsonl")
    target.write_text(export())
    print(f"wrote {len(CASES)} cases to {target}")
