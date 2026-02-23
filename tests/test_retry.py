"""Tests for retry callback factories."""

from __future__ import annotations

import io
import json
from unittest.mock import patch

from guten_morgen.retry import make_agent_retry_callback, make_human_retry_callback


class TestAgentRetryCallback:
    def test_emits_json_to_stderr(self) -> None:
        """Agent callback writes compact JSON to stderr and sleeps."""
        buf = io.StringIO()
        with patch("time.sleep") as mock_sleep, patch("sys.stderr", buf):
            cb = make_agent_retry_callback()
            cb(15, 1, 2)
        output = json.loads(buf.getvalue().strip())
        assert output == {"retry": {"wait": 15, "attempt": 1, "max": 2}}
        mock_sleep.assert_called_once_with(15)

    def test_multiple_retries_emit_multiple_lines(self) -> None:
        """Each retry emits a separate JSON line."""
        buf = io.StringIO()
        with patch("time.sleep"), patch("sys.stderr", buf):
            cb = make_agent_retry_callback()
            cb(10, 1, 2)
            cb(10, 2, 2)
        lines = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
        assert len(lines) == 2
        assert lines[0]["retry"]["attempt"] == 1
        assert lines[1]["retry"]["attempt"] == 2


class TestHumanRetryCallback:
    def test_sleeps_for_wait_seconds(self) -> None:
        """Human callback sleeps in 1-second ticks totaling wait time."""
        sleep_total = {"t": 0.0}

        def fake_sleep(s: float) -> None:
            sleep_total["t"] += s

        with patch("time.sleep", side_effect=fake_sleep):
            cb = make_human_retry_callback()
            cb(3, 1, 2)
        assert sleep_total["t"] == 3.0

    def test_does_not_crash_without_terminal(self) -> None:
        """Callback works even if rich can't detect a terminal."""
        with patch("time.sleep"):
            cb = make_human_retry_callback()
            cb(1, 1, 2)  # should not raise
