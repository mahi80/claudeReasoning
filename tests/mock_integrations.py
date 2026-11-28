from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

CALLS: list[dict] = []
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle_request(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        token = self.headers.get("Authorization") or self.headers.get("PRIVATE-TOKEN")
        with LOCK:
            CALLS.append({"method": self.command, "path": self.path, "body": json.loads(body) if body else None,
                          "authenticated": token in {"Bearer fixture-token", "fixture-token"}})
        output = json.dumps({"ok": True, "number": 1, "issues": [], "isLast": True}).encode()
        self.send_response(200 if token in {"Bearer fixture-token", "fixture-token"} else 401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(output)))
        self.end_headers()
        self.wfile.write(output)

    do_GET = handle_request
    do_POST = handle_request
    do_PUT = handle_request
    do_PATCH = handle_request


def start():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_port


def configuration(port: int) -> dict:
    return {"services": {
        "github": {"url": f"http://127.0.0.1:{port}/github", "token_env": "FIXTURE_CONNECTOR_TOKEN",
                   "resources": ["team/repo"], "tools": ["list_issues", "create_request"]},
        "gitlab": {"url": f"http://127.0.0.1:{port}/gitlab", "token_env": "FIXTURE_CONNECTOR_TOKEN",
                   "resources": ["group/repo"], "tools": ["list_issues"]},
        "jira": {"url": f"http://127.0.0.1:{port}/jira", "token_env": "FIXTURE_CONNECTOR_TOKEN",
                 "resources": ["PROJ"], "tools": ["list_issues"]},
    }}
