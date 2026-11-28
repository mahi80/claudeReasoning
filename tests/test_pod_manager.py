from __future__ import annotations

import http.client
import importlib.util
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("pod_manager_lifecycle_test", ROOT / "harness/pod_manager.py")
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)


class PodLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.multiple(pm, POD_ID="fixture", IDLE_SECONDS=10, START_TIMEOUT=2,
                                        POLL_SECONDS=1, STOP_SETTLE_SECONDS=300, _last_used=0,
                                        _stop_requested=False, _stop_requested_at=0.0,
                                        _start_unconfirmed=False))
        self.clock = self.enterContext(patch.object(pm.time, "time", return_value=100))
        self.sleep = self.enterContext(patch.object(pm.time, "sleep"))
        self.health = self.enterContext(patch.object(pm, "healthy", return_value=False))
        self.action = self.enterContext(patch.object(pm, "_action", return_value=(202, "{}")))
        self.enterContext(patch.object(pm.urllib.request, "urlopen",
                                       side_effect=AssertionError("No live network allowed")))

    def test_unmanaged_pod_does_not_start_or_stop(self):
        pm.POD_ID = ""
        pm.ensure_ready()
        self.assertFalse(pm.stop_if_idle(lambda: 0))
        self.health.assert_not_called()
        self.action.assert_not_called()

    def test_healthy_pod_is_reused(self):
        self.health.return_value = True
        pm.ensure_ready()
        self.action.assert_not_called()
        self.assertEqual(pm._last_used, 100)

    def test_accepted_start_waits_for_health(self):
        self.health.side_effect = [False, False, True]
        notify = Mock()
        pm.ensure_ready(notify)
        self.action.assert_called_once_with("start")
        self.sleep.assert_called_once_with(1)
        self.assertEqual(notify.call_args.args, ("Model server is ready.",))

    def test_rejected_start_fails_without_polling_or_response_body(self):
        self.sleep.side_effect = AssertionError("Rejected starts must not poll")
        for status in (401, 409, 429, 503):
            with self.subTest(status=status):
                self.action.return_value = (status, "private response body")
                self.health.reset_mock()
                self.sleep.reset_mock()
                with self.assertRaises(RuntimeError) as failure:
                    pm.ensure_ready()
                self.assertIn(str(status), str(failure.exception))
                self.assertNotIn("private response body", str(failure.exception))
                self.health.assert_called_once_with()
                self.sleep.assert_not_called()

    def test_start_transport_failure_propagates_without_polling(self):
        self.action.side_effect = urllib.error.URLError("fixture outage")
        with self.assertRaises(urllib.error.URLError):
            pm.ensure_ready()
        self.health.assert_called_once_with()
        self.sleep.assert_not_called()

    def test_accepted_start_timeout_leaves_pod_eligible_for_idle_stop(self):
        self.clock.side_effect = [0, 0, 1, 3]
        with self.assertRaisesRegex(TimeoutError, "GPU pod not healthy"):
            pm.ensure_ready()
        self.clock.side_effect = None
        self.assertTrue(pm.stop_if_idle(lambda: 0))
        self.assertEqual(self.action.call_args.args, ("stop",))

    def test_idle_unhealthy_pod_is_stopped_without_health_probe(self):
        self.assertTrue(pm.stop_if_idle(lambda: 0))
        self.action.assert_called_once_with("stop")
        self.health.assert_not_called()

    def test_active_or_recently_used_pod_is_not_stopped(self):
        self.assertFalse(pm.stop_if_idle(lambda: 1))
        pm.touch()
        self.assertFalse(pm.stop_if_idle(lambda: 0))
        self.action.assert_not_called()

    def test_activity_is_rechecked_under_lock(self):
        active = Mock(side_effect=[0, 1])
        self.assertFalse(pm.stop_if_idle(active))
        self.action.assert_not_called()

    def test_recent_touch_is_rechecked_under_lock(self):
        with patch.object(pm, "_lock") as lock:
            lock.__enter__.side_effect = pm.touch
            self.assertFalse(pm.stop_if_idle(lambda: 0))
        self.action.assert_not_called()

    def test_successful_stop_is_not_repeated_until_next_start(self):
        self.health.return_value = True
        self.assertTrue(pm.stop_if_idle(lambda: 0))
        self.assertFalse(pm.stop_if_idle(lambda: 0))
        pm.ensure_ready()
        pm._last_used = 0
        self.assertTrue(pm.stop_if_idle(lambda: 0))
        self.assertEqual([call.args for call in self.action.call_args_list],
                         [("stop",), ("start",), ("stop",)])

    def test_shutdown_request_is_not_mistaken_for_a_warm_pod(self):
        self.assertTrue(pm.stop_if_idle(lambda: 0))
        self.health.return_value = True
        pm.ensure_ready()
        self.assertEqual(self.action.call_args.args, ("start",))
        self.assertFalse(pm._stop_requested)

    def test_failed_restart_preserves_shutdown_state_for_next_request(self):
        for failure in ((503, "private response body"), urllib.error.URLError("fixture outage")):
            with self.subTest(failure=type(failure).__name__):
                pm._last_used = 0
                pm._stop_requested = False
                self.action.reset_mock()
                self.action.side_effect = [(202, "{}"), failure, (202, "{}")]
                self.health.return_value = True
                self.assertTrue(pm.stop_if_idle(lambda: 0))
                with self.assertRaises((RuntimeError, urllib.error.URLError)):
                    pm.ensure_ready()
                self.assertTrue(pm._stop_requested)
                pm.ensure_ready()
                self.assertFalse(pm._stop_requested)
                self.assertEqual([call.args for call in self.action.call_args_list],
                                 [("stop",), ("start",), ("start",)])

    def test_unconfirmed_restart_does_not_disable_idle_stop(self):
        # The idle stop is accepted; the next start's reply is lost after Runpod started the pod.
        self.action.side_effect = [(202, "{}"), urllib.error.URLError("reply lost"), (202, "{}")]
        self.assertTrue(pm.stop_if_idle(lambda: 0))
        with self.assertRaises(urllib.error.URLError):
            pm.ensure_ready()
        self.assertTrue(pm._stop_requested)
        self.health.return_value = True                # the pod is up after all
        self.clock.return_value = 100 + pm.STOP_SETTLE_SECONDS + pm.IDLE_SECONDS
        self.assertTrue(pm.stop_if_idle(lambda: 0))
        self.assertEqual([call.args for call in self.action.call_args_list],
                         [("stop",), ("start",), ("stop",)])

    def test_unconfirmed_restart_of_a_pod_that_never_answers_is_still_stopped(self):
        for failure in (urllib.error.URLError("reply lost"), (502, "gateway error")):
            with self.subTest(failure=type(failure).__name__):
                pm._last_used, pm._stop_requested, pm._start_unconfirmed = 0, False, False
                self.clock.return_value = 100
                self.action.reset_mock()
                self.action.side_effect = [(202, "{}"), failure, (202, "{}")]
                self.health.return_value = False           # the restarted model never comes up
                self.assertTrue(pm.stop_if_idle(lambda: 0))
                with self.assertRaises((RuntimeError, urllib.error.URLError)):
                    pm.ensure_ready()
                self.health.reset_mock()
                self.clock.return_value = 100 + pm.STOP_SETTLE_SECONDS + pm.IDLE_SECONDS
                self.assertTrue(pm.stop_if_idle(lambda: 0))
                self.health.assert_not_called()            # an unknown start is not judged by /health
                self.assertEqual([call.args for call in self.action.call_args_list],
                                 [("stop",), ("start",), ("stop",)])
                self.assertFalse(pm._start_unconfirmed)

    def test_rejected_start_does_not_force_a_stop(self):
        self.action.side_effect = [(202, "{}"), (401, "unauthorized")]
        self.assertTrue(pm.stop_if_idle(lambda: 0))
        with self.assertRaises(RuntimeError):
            pm.ensure_ready()
        self.assertFalse(pm._start_unconfirmed)           # Runpod refused: the pod stayed down
        self.clock.return_value = 100 + pm.STOP_SETTLE_SECONDS + pm.IDLE_SECONDS
        self.assertFalse(pm.stop_if_idle(lambda: 0))
        self.health.assert_called_once_with()
        self.assertEqual(self.action.call_count, 2)

    def test_activity_during_the_health_probe_prevents_the_stop(self):
        self.assertTrue(pm.stop_if_idle(lambda: 0))
        self.clock.return_value = 100 + pm.STOP_SETTLE_SECONDS + pm.IDLE_SECONDS
        pm._last_used = 0

        def probe():
            pm.touch()                                     # a request arrives while /health is asked
            return True
        self.health.side_effect = probe
        self.assertFalse(pm.stop_if_idle(lambda: 0))
        self.action.assert_called_once_with("stop")

    def test_stop_is_not_repeated_while_the_pod_is_settling_or_down(self):
        self.health.return_value = True                # a stopping pod may still answer
        self.assertTrue(pm.stop_if_idle(lambda: 0))
        self.clock.return_value = 100 + pm.STOP_SETTLE_SECONDS - 1
        self.assertFalse(pm.stop_if_idle(lambda: 0))
        self.health.assert_not_called()
        self.health.return_value = False               # settled and down, as requested
        self.clock.return_value = 100 + pm.STOP_SETTLE_SECONDS + 1
        self.assertFalse(pm.stop_if_idle(lambda: 0))
        self.health.assert_called_once_with()
        self.action.assert_called_once_with("stop")

    def test_pod_running_long_after_a_stop_is_reused_without_a_start(self):
        self.assertTrue(pm.stop_if_idle(lambda: 0))
        self.health.return_value = True                # started from the console, say
        self.clock.return_value = 100 + pm.STOP_SETTLE_SECONDS + 1
        pm.ensure_ready()
        self.assertFalse(pm._stop_requested)
        self.action.assert_called_once_with("stop")

    def test_failed_stop_can_be_retried(self):
        self.action.side_effect = [(503, "private response body"), (200, "{}")]
        with self.assertLogs(pm.__name__, "WARNING") as logs:
            self.assertFalse(pm.stop_if_idle(lambda: 0))
        self.assertIn("503", logs.output[0])
        self.assertNotIn("private response body", logs.output[0])
        self.assertTrue(pm.stop_if_idle(lambda: 0))
        self.assertEqual(self.action.call_count, 2)

    def test_stop_transport_failure_remains_retryable(self):
        self.action.side_effect = [urllib.error.URLError("fixture outage"), (202, "{}")]
        with self.assertRaises(urllib.error.URLError):
            pm.stop_if_idle(lambda: 0)
        self.assertFalse(pm._stop_requested)
        self.assertTrue(pm.stop_if_idle(lambda: 0))
        self.assertEqual(self.action.call_count, 2)

    def test_watchdog_survives_transport_failures(self):
        for error in (urllib.error.URLError("private fixture URL"), OSError("private fixture path"),
                      http.client.IncompleteRead(b"private fixture body"),
                      RuntimeError("private fixture: dictionary changed size during iteration")):
            with self.subTest(error=type(error).__name__):
                self.sleep.side_effect = [None, None, SystemExit]
                with patch.object(pm, "stop_if_idle", side_effect=[error, False]) as stop:
                    with patch.object(threading, "excepthook"), self.assertLogs(pm.__name__, "WARNING") as logs:
                        thread = pm.start_watchdog(lambda: 0, every=3)
                        thread.join(1)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual(stop.call_count, 2)
                    self.assertEqual(len(logs.output), 1)
                    self.assertNotIn("private fixture", logs.output[0])
                self.sleep.reset_mock()

    def test_concurrent_requests_share_one_start(self):
        ready = False
        barrier, failures = threading.Barrier(3), []
        second_caller, calls, count = threading.Event(), [], threading.Lock()

        def health():
            seen = ready                               # what this caller would act on
            with count:
                calls.append(seen)
                first = len(calls) == 1
            if first:
                second_caller.wait(0.5)                # without the lock a second caller gets here now
            else:
                second_caller.set()
            return seen

        self.health.side_effect = health

        def start(action):
            nonlocal ready
            ready = True
            return 202, "{}"

        def request():
            try:
                barrier.wait(timeout=1)
                pm.ensure_ready()
            except Exception as error:
                failures.append(error)

        self.action.side_effect = start
        threads = [threading.Thread(target=request) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=1)
        for thread in threads:
            thread.join(1)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.action.assert_called_once_with("start")


if __name__ == "__main__":
    unittest.main()
