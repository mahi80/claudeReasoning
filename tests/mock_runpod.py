"""Mock of the two things pod_manager talks to: Runpod's pod start/stop API and /health.

After a start call the 'pod' needs a few health polls before it reports healthy,
which stands in for container start and model loading.
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"running": False, "polls_left": 0, "starts": 0, "stops": 0, "bad_auth": 0,
         "warm_polls": 3}
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, status: int, body: bytes = b"{}") -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        with LOCK:
            if self.path == "/health":
                if STATE["running"] and STATE["polls_left"] > 0:
                    STATE["polls_left"] -= 1
                    return self._reply(503)
                return self._reply(200 if STATE["running"] else 503)
        self._reply(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        with LOCK:
            if self.headers.get("Authorization") != "Bearer rp-key":
                STATE["bad_auth"] += 1
                return self._reply(401, b'{"error": "unauthorized"}')
            if self.path == "/v1/pods/pod123/start":
                STATE["starts"] += 1
                STATE["running"], STATE["polls_left"] = True, STATE["warm_polls"]
                return self._reply(200, b'{"desiredStatus": "RUNNING"}')
            if self.path == "/v1/pods/pod123/stop":
                STATE["stops"] += 1
                STATE["running"] = False
                return self._reply(200, b'{"desiredStatus": "EXITED"}')
        self._reply(404)


class QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass


def start() -> tuple[ThreadingHTTPServer, int]:
    server = QuietServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]
