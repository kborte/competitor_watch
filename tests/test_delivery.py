"""Delivery outcomes.

HTTP 200 means "received and processed", not "everything succeeded" — the body
carries a per-payload error count, and discarding it is what made a stranded
finding invisible in the run summary.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from research_crawler import crawler
from research_crawler.schemas import IngestPayload


@pytest.fixture
def payload():
    now = datetime.now(UTC)
    return IngestPayload(
        routine_run_id="run-1", run_started_at=now, run_completed_at=now,
        keywords=["Beema"], findings=[],
    )


def response(status, body=None, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.ok = 200 <= status < 300
    resp.text = text
    if body is None:
        resp.json.side_effect = ValueError("not json")
    else:
        resp.json.return_value = body
    return resp


class TestDeliveryOutcomes:
    def test_clean_success(self, payload):
        with patch.object(crawler.requests, "post",
                          return_value=response(200, {"status": "processed", "errors": 0})):
            result = crawler.deliver(payload)
        assert result.stored is True
        assert result.classify_errors == 0
        assert bool(result) is True

    def test_stored_but_unclassified_is_not_a_clean_success(self, payload):
        # The case the old code reported as a plain success.
        with patch.object(crawler.requests, "post",
                          return_value=response(200, {"status": "processed", "errors": 2})):
            result = crawler.deliver(payload)
        assert result.stored is True
        assert result.classify_errors == 2

    def test_already_processed_counts_as_stored(self, payload):
        # A replayed delivery is a no-op, not a failure.
        with patch.object(crawler.requests, "post",
                          return_value=response(200, {"status": "already processed"})):
            assert crawler.deliver(payload).stored is True

    def test_unreadable_body_does_not_lose_the_delivery(self, payload):
        with patch.object(crawler.requests, "post", return_value=response(200, None, "<html>")):
            result = crawler.deliver(payload)
        assert result.stored is True
        assert result.classify_errors == 0

    @pytest.mark.parametrize("status", [500, 502, 503, 422])
    def test_error_statuses_are_failures(self, payload, status):
        with patch.object(crawler.requests, "post", return_value=response(status, None, "boom")):
            assert crawler.deliver(payload).stored is False

    def test_network_error_is_a_failure_not_a_crash(self, payload):
        with patch.object(crawler.requests, "post",
                          side_effect=requests.ConnectionError("refused")):
            assert crawler.deliver(payload).stored is False


class TestFailFastOnAuth:
    @pytest.mark.parametrize("status", [401, 403])
    def test_credential_failures_abort_the_run(self, payload, status):
        # A secret mismatch will hit every later delivery too. Treating it like
        # a transient 503 produced a whole run of quiet failures.
        with patch.object(crawler.requests, "post", return_value=response(status, None, "no")):
            with pytest.raises(crawler.FatalDeliveryError, match="credentials"):
                crawler.deliver(payload)

    def test_transient_failure_does_not_abort_the_run(self, payload):
        with patch.object(crawler.requests, "post", return_value=response(503, None, "later")):
            crawler.deliver(payload)  # must not raise


class TestDeliveryTimeout:
    def test_timeout_is_taken_from_config(self, payload):
        captured = {}

        def capture(*args, **kwargs):
            captured.update(kwargs)
            return response(200, {"errors": 0})

        with patch.object(crawler.requests, "post", side_effect=capture):
            crawler.deliver(payload)
        assert captured["timeout"] == crawler.config.BACKEND_TIMEOUT_SECONDS


class TestKillSwitch:
    def test_disabled_crawl_makes_no_calls_and_exits_clean(self, monkeypatch):
        monkeypatch.setattr(crawler.config, "CRAWL_ENABLED", False)
        with patch.object(crawler, "_run_company") as ran:
            assert crawler.run() == 0
        ran.assert_not_called()

    @pytest.mark.parametrize("value,expected", [
        ("true", True), ("TRUE", True), ("yes", True), ("1", True), ("", True),
        ("false", False), ("False", False), ("no", False), ("0", False), ("off", False),
    ])
    def test_kill_switch_parsing(self, value, expected, monkeypatch):
        # Stated positively so the variable reads the way it behaves; the unset
        # and empty cases must both mean "enabled", or a missing variable would
        # silently stop the crawl.
        monkeypatch.setenv("CRAWL_ENABLED", value)
        import importlib

        from research_crawler import config as crawler_config
        assert importlib.reload(crawler_config).CRAWL_ENABLED is expected


class TestRunCaps:
    def test_config_caps_are_positive_and_ordered(self):
        cfg = crawler.config
        assert cfg.MAX_SOURCES_PER_KEYWORD > 0
        assert cfg.MAX_FINDINGS_PER_KEYWORD > 0
        assert cfg.MAX_FINDINGS_PER_CRAWL >= cfg.MAX_FINDINGS_PER_KEYWORD
        assert cfg.MAX_SUMMARY_CHARS > 0
