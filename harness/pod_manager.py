"""pod_manager.py - start the Runpod GPU pod on demand and stop it when idle.

This is plain code on purpose: the model cannot decide to start its own GPU, because the
model runs on that GPU. Leave RUNPOD_POD_ID unset to manage nothing (local or always-on).
"""
from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.request
from typing import Callable

API = os.environ.get("RUNPOD_API", "https://rest.runpod.io/v1")
POD_ID = os.environ.get("RUNPOD_POD_ID", "")
RUNPOD_KEY = os.environ.get("RUNPOD_API_KEY", "")
HEALTH_URL = (os.environ.get("LLM_HEALTH_URL")
              or f"https://{POD_ID}-8000.proxy.runpod.net/health")
START_TIMEOUT = float(os.environ.get("POD_START_TIMEOUT", "1500"))   # seconds
IDLE_SECONDS = float(os.environ.get("POD_IDLE_SECONDS", "900"))      # stop after this
POLL_SECONDS = float(os.environ.get("POD_POLL_SECONDS", "10"))

_lock = threading.Lock()
_last_used = time.time()


def healthy() -> bool:
    """True when the model server answers its health check."""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=5) as reply:
            return reply.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _action(action: str) -> tuple[int, str]:
    """POST /pods/{id}/start or /stop on the Runpod REST API."""
    request = urllib.request.Request(
        f"{API}/pods/{POD_ID}/{action}", method="POST", data=b"",
        headers={"Authorization": f"Bearer {RUNPOD_KEY}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as reply:
            return reply.status, reply.read().decode(errors="replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode(errors="replace")


def touch() -> None:
    """Record activity so the idle watchdog leaves the pod alone."""
    global _last_used
    _last_used = time.time()


def ensure_ready(notify: Callable[[str], None] = lambda text: None) -> None:
    """Return once the model server is healthy, starting the pod first if needed."""
    if not POD_ID:
        return
    with _lock:                       # concurrent requests share one start
        touch()
        if healthy():
            return
        notify("Starting the GPU pod. Loading the model can take several minutes.")
        status, body = _action("start")
        deadline = time.time() + START_TIMEOUT
        while time.time() < deadline:
            if healthy():
                notify("Model server is ready.")
                touch()
                return
            time.sleep(POLL_SECONDS)
        raise TimeoutError(
            f"GPU pod not healthy after {START_TIMEOUT:.0f}s. Runpod start call returned "
            f"{status}: {body[:200]}. Check GPU capacity and the pod log.")


def stop_if_idle(active_runs: Callable[[], int]) -> bool:
    """Stop the pod when nothing has used it for IDLE_SECONDS. Returns True if stopped."""
    if not POD_ID or active_runs() > 0 or time.time() - _last_used < IDLE_SECONDS:
        return False
    with _lock:
        if active_runs() > 0 or not healthy():
            return False
        status, _ = _action("stop")
        return status < 300


def start_watchdog(active_runs: Callable[[], int], every: float = 60) -> threading.Thread:
    def loop() -> None:
        while True:
            time.sleep(every)
            stop_if_idle(active_runs)

    thread = threading.Thread(target=loop, daemon=True, name="pod-idle-watchdog")
    thread.start()
    return thread
