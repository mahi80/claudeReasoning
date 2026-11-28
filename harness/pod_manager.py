"""pod_manager.py - start the Runpod GPU pod on demand and stop it when idle.

This is plain code on purpose: the model cannot decide to start its own GPU, because the
model runs on that GPU. Leave RUNPOD_POD_ID unset to manage nothing (local or always-on).
"""
from __future__ import annotations

import logging
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
# After an accepted stop the pod may answer /health for a while on its way down, so for
# this long a healthy reply is not taken as proof that it is running again.
STOP_SETTLE_SECONDS = float(os.environ.get("POD_STOP_SETTLE_SECONDS", "300"))

_lock = threading.Lock()
_last_used = time.time()
_stop_requested = False
_stop_requested_at = 0.0
_start_unconfirmed = False      # a start's reply was lost or a gateway error: the pod may be up


def _settling() -> bool:
    """True shortly after an accepted stop, while /health cannot tell running from stopping."""
    return _stop_requested and time.time() - _stop_requested_at < STOP_SETTLE_SECONDS


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
    global _stop_requested, _start_unconfirmed
    if not POD_ID:
        return
    with _lock:                       # concurrent requests share one start
        touch()
        if _stop_requested and not _settling() and healthy():
            # Up long after our stop: a start whose reply was lost, or one from elsewhere.
            _stop_requested = _start_unconfirmed = False
            return
        restart = _stop_requested
        if not restart and healthy():
            return
        notify("Starting the GPU pod. Loading the model can take several minutes.")
        try:
            status, _ = _action("start")
        except Exception:
            _start_unconfirmed = True     # Runpod may have acted before the reply was lost
            raise
        if not 200 <= status < 300:
            _start_unconfirmed = _start_unconfirmed or status >= 500   # a gateway error can follow a start
            raise RuntimeError(
                f"Runpod rejected the pod start (HTTP {status}). "
                "Check credentials, pod status and GPU capacity.")
        _stop_requested = _start_unconfirmed = False
        deadline = time.time() + START_TIMEOUT
        while time.time() < deadline:
            if healthy():
                notify("Model server is ready.")
                touch()
                return
            time.sleep(POLL_SECONDS)
        raise TimeoutError(
            f"GPU pod not healthy after {START_TIMEOUT:.0f}s. Runpod accepted the start "
            f"(HTTP {status}). Check GPU capacity and the pod log.")


def stop_if_idle(active_runs: Callable[[], int]) -> bool:
    """Request shutdown after IDLE_SECONDS of inactivity. Return True if accepted."""
    global _stop_requested, _stop_requested_at, _start_unconfirmed
    if not POD_ID or active_runs() > 0 or time.time() - _last_used < IDLE_SECONDS:
        return False
    if _stop_requested and _settling() and not _start_unconfirmed:
        return False                  # still going down after the stop we sent
    # After a stop that was not followed by an unconfirmed start, /health tells whether the
    # pod came back. The probe can take seconds, so it runs before the lock and before the
    # activity check that decides last.
    probe = _stop_requested and not _start_unconfirmed
    back_up = healthy() if probe else False
    with _lock:
        if active_runs() > 0 or time.time() - _last_used < IDLE_SECONDS:
            return False
        if _stop_requested and not _start_unconfirmed and (_settling() or (probe and not back_up)):
            return False              # still stopping, or stopped as requested; a start with
                                      # an unknown outcome is stopped even while settling
        status, _ = _action("stop")
        if not 200 <= status < 300:
            logging.getLogger(__name__).warning("Runpod rejected idle pod shutdown (HTTP %s).", status)
            return False
        _stop_requested, _stop_requested_at, _start_unconfirmed = True, time.time(), False
        return True


def start_watchdog(active_runs: Callable[[], int], every: float = 60) -> threading.Thread:
    def loop() -> None:
        while True:
            time.sleep(every)
            try:
                stop_if_idle(active_runs)
            except Exception as error:    # one failed attempt must not end idle shutdown for good
                logging.getLogger(__name__).warning(
                    "Runpod idle shutdown failed; retrying at the next interval (%s).",
                    type(error).__name__)

    thread = threading.Thread(target=loop, daemon=True, name="pod-idle-watchdog")
    thread.start()
    return thread
