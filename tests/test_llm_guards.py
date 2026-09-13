"""Guards on the model calls: retry policy, per-call limits, and the None
response that used to surface as an AttributeError in the database layer.

No network: the SDK's generate_content is replaced throughout.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend import classify, config
from shared import gemini


class SdkError(Exception):
    """Shaped like a Gemini SDK error: carries an HTTP status."""

    def __init__(self, code):
        self.code = code
        super().__init__(f"HTTP {code}")


def make_response(parsed="VERDICT", text="{}"):
    response = MagicMock()
    response.parsed = parsed
    response.text = text
    response.usage_metadata = MagicMock(
        prompt_token_count=1200, candidates_token_count=180, total_token_count=1380,
    )
    return response


@pytest.fixture
def finding():
    return MagicMock(
        company="Beema", category="news", title="T", summary="s", source_excerpt="e",
        source_url="https://x.test/a",
    )


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_BACKOFF_SECONDS", 0.001)


class TestRetryPolicy:
    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_transient_statuses_are_retried(self, finding, status):
        attempts = []

        def flaky(**kwargs):
            attempts.append(1)
            if len(attempts) < 2:
                raise SdkError(status)
            return make_response()

        with patch.object(classify.client.models, "generate_content", side_effect=flaky):
            verdict, _prompt, _raw, _usage = classify.classify(finding)
        assert verdict == "VERDICT"
        assert len(attempts) == 2

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
    def test_permanent_statuses_fail_on_the_first_attempt(self, finding, status):
        # Retrying these only delays the error and spends quota.
        attempts = []

        def always(**kwargs):
            attempts.append(1)
            raise SdkError(status)

        with patch.object(classify.client.models, "generate_content", side_effect=always):
            with pytest.raises(SdkError):
                classify.classify(finding)
        assert len(attempts) == 1

    def test_retries_are_capped(self, finding):
        attempts = []

        def always(**kwargs):
            attempts.append(1)
            raise SdkError(429)

        with patch.object(classify.client.models, "generate_content", side_effect=always):
            with pytest.raises(SdkError):
                classify.classify(finding)
        assert len(attempts) == config.GEMINI_MAX_ATTEMPTS


class TestNoneResponse:
    def test_unparseable_response_raises_a_named_error(self, finding):
        # `.parsed` is None when the response is blocked or truncated. Without
        # this the None travelled on and surfaced much later as an
        # AttributeError inside the database layer, blaming the wrong component.
        with patch.object(classify.client.models, "generate_content",
                          return_value=make_response(parsed=None, text="not json")):
            with pytest.raises(ValueError, match="no parseable classification"):
                classify.classify(finding)

    def test_the_error_includes_what_the_model_actually_said(self, finding):
        with patch.object(classify.client.models, "generate_content",
                          return_value=make_response(parsed=None, text="BLOCKED: safety")):
            with pytest.raises(ValueError, match="BLOCKED: safety"):
                classify.classify(finding)


class TestPerCallLimits:
    def test_output_thinking_and_timeout_are_all_bounded(self, finding):
        captured = {}

        def capture(**kwargs):
            captured.update(kwargs)
            return make_response()

        with patch.object(classify.client.models, "generate_content", side_effect=capture):
            classify.classify(finding)

        sent = captured["config"]
        assert sent.max_output_tokens == config.CLASSIFY_MAX_OUTPUT_TOKENS
        assert sent.thinking_config.thinking_budget == config.CLASSIFY_THINKING_BUDGET
        assert sent.http_options.timeout == config.CLASSIFY_TIMEOUT_MS

    def test_classify_timeout_is_below_the_crawler_delivery_timeout(self):
        # Innermost strictest, so a slow call surfaces as a real error to
        # whoever is waiting rather than as a guess on either side.
        from research_crawler import config as crawler_config
        assert config.CLASSIFY_TIMEOUT_MS / 1000 < crawler_config.BACKEND_TIMEOUT_SECONDS


class TestUsageAccounting:
    def test_token_counts_are_returned_for_storage(self, finding):
        with patch.object(classify.client.models, "generate_content",
                          return_value=make_response()):
            _v, _p, _r, usage = classify.classify(finding)
        assert usage == {"input_tokens": 1200, "output_tokens": 180, "total_tokens": 1380}

    def test_missing_usage_metadata_is_not_fatal(self, finding):
        response = make_response()
        response.usage_metadata = None
        with patch.object(classify.client.models, "generate_content", return_value=response):
            _v, _p, _r, usage = classify.classify(finding)
        assert usage == {}


class TestStatusExtraction:
    """One shared helper now, used by all three call sites."""

    def test_code_attribute_is_read(self):
        assert gemini.status_of(SdkError(503)) == 503

    def test_nested_response_status_is_read(self):
        exc = Exception("wrapped")
        exc.response = MagicMock(status_code=429)
        assert gemini.status_of(exc) == 429

    def test_a_plain_exception_has_no_status(self):
        assert gemini.status_of(ValueError("nope")) is None

    def test_retryable_statuses_are_transient_only(self):
        # A permanent status here would mean retrying a request that can never
        # succeed, spending quota to arrive at the same error.
        assert set(gemini.RETRYABLE_STATUSES) == {429, 500, 502, 503, 504}
