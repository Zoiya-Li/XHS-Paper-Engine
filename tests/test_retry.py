"""Tests for the retry helper (base_delay=0 so tests stay fast)."""

import pytest

from dp_core.retry import call_api_with_retry


def test_succeeds_first_try():
    calls = {"n": 0}

    def ok():
        calls["n"] += 1
        return "ok"

    assert call_api_with_retry(ok, max_retries=3, base_delay=0) == "ok"
    assert calls["n"] == 1


def test_retries_then_succeeds():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("boom")
        return "recovered"

    assert call_api_with_retry(flaky, max_retries=3, base_delay=0) == "recovered"
    assert calls["n"] == 3


def test_raises_after_exhausting_retries():
    def always_fail():
        raise TimeoutError("nope")

    with pytest.raises(TimeoutError):
        call_api_with_retry(always_fail, max_retries=2, base_delay=0)


def test_non_retryable_raises_immediately():
    calls = {"n": 0}

    def bad():
        calls["n"] += 1
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        call_api_with_retry(bad, max_retries=3, base_delay=0)
    assert calls["n"] == 1  # never retried
