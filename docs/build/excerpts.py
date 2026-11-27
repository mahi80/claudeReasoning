"""Cut named top-level definitions out of the tested source so the document quotes it exactly."""
import ast
import json
from pathlib import Path

Path("docs/build/out").mkdir(parents=True, exist_ok=True)

src_path = Path("harness/mini_harness.py")
src = src_path.read_text()
lines = src.splitlines()
tree = ast.parse(src)
spans = {}
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        spans[node.name] = (start, node.end_lineno)
    elif isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                spans[target.id] = (node.lineno, node.end_lineno)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        spans[node.target.id] = (node.lineno, node.end_lineno)


def cut(*names):
    out = []
    for i, name in enumerate(names):
        a, b = spans[name]
        if i:
            out.append("")
        out.extend(lines[a - 1:b])
    return out


excerpts = {
    "call_model": cut("Reply", "call_model"),
    "run_agent": cut("run_agent"),
    "registry": cut("Tool", "REGISTRY", "obj", "tool"),
    "edit_file": cut("edit_file"),
    "execute": cut("clip", "execute"),
    "subagents": cut("WORKER_TOOLS", "ORCHESTRATOR_TOOLS", "SPAWN_LOCK", "WORKER_SYSTEM",
                     "spawn_agent"),
    "orchestrator": cut("orchestrator_system"),
    "skills": cut("skills_index", "load_skill"),
    "context": cut("build_messages", "compact"),
    "guard": cut("inside_workspace", "READ_ONLY", "is_read_only", "no_operator", "unattended",
                 "UNATTENDED", "approved", "denial"),
    "trace": cut("trace"),
    "longtask": cut("update_plan", "checkpoint_file", "save_checkpoint"),
    "effort": cut("Effort", "EFFORTS", "LADDER", "GUIDANCE", "budgets", "thinking_mode"),
    "scaffolds": cut("think", "VERIFY_PROMPT", "REVIEWER_SYSTEM", "REJECTED", "review",
                     "run_escalating"),
}
# the preset table in the document is built from the same Effort(...) rows as the code
efforts = [[ast.literal_eval(arg) for arg in node.args] for node in ast.walk(tree)
           if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Effort"]
json.dump(efforts, open("docs/build/out/efforts.json", "w"))
excerpts["smoke"] = Path("harness/smoke_test.py").read_text().splitlines()


def cut_from(path, *names):
    text = Path(path).read_text()
    rows, out, found = text.splitlines(), [], {}
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            found[node.name] = (first, node.end_lineno)
    for i, name in enumerate(names):
        a, b = found[name]
        if i:
            out.append("")
        out.extend(rows[a - 1:b])
    return out


excerpts["pod"] = cut_from("harness/pod_manager.py", "ensure_ready", "stop_if_idle")
excerpts["chat"] = cut_from("app/server.py", "work", "chat")
for k, v in excerpts.items():
    print(f"{k:14s} {len(v):3d} lines, widest {max(len(x) for x in v)}")
print("total excerpt lines:", sum(len(v) for v in excerpts.values()), "of", len(lines))
json.dump(excerpts, open("docs/build/out/excerpts.json", "w"), indent=1)
