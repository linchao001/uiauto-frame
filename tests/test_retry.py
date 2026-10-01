"""retry_action / is_retryable：只重试瞬态失败，定位类错误立即失败。"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from pilot.core.retry import action_timeout_ms, is_retryable, retry_action


def test_is_retryable_timeout() -> None:
    assert is_retryable(PlaywrightTimeoutError("Timeout 5000ms exceeded."))


def test_is_retryable_detached_and_unstable() -> None:
    assert is_retryable(PlaywrightError("Element is not attached to the DOM"))
    assert is_retryable(PlaywrightError("element was detached from the DOM"))
    assert is_retryable(PlaywrightError("<div> intercepts pointer events"))
    assert is_retryable(PlaywrightError("element is not stable"))


def test_is_retryable_rejects_strict_and_generic() -> None:
    assert not is_retryable(
        PlaywrightError("strict mode violation: get_by_role('button') resolved to 2 elements")
    )
    assert not is_retryable(PlaywrightError("Unexpected token"))
    assert not is_retryable(ValueError("not playwright"))


def test_retry_action_does_not_retry_strict() -> None:
    calls = 0

    def _fn() -> None:
        nonlocal calls
        calls += 1
        raise PlaywrightError("strict mode violation: resolved to 2 elements")

    with pytest.raises(PlaywrightError, match="strict mode"):
        retry_action(_fn, retries=2, delay_ms=0)

    assert calls == 1


def test_retry_action_retries_timeout_then_succeeds() -> None:
    calls = 0

    def _fn() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise PlaywrightTimeoutError("Timeout 100ms exceeded.")
        return "ok"

    assert retry_action(_fn, retries=2, delay_ms=0) == "ok"
    assert calls == 3


def test_retry_action_exhausts_retries_on_timeout() -> None:
    calls = 0

    def _fn() -> None:
        nonlocal calls
        calls += 1
        raise PlaywrightTimeoutError("Timeout 100ms exceeded.")

    with pytest.raises(PlaywrightTimeoutError):
        retry_action(_fn, retries=2, delay_ms=0)

    assert calls == 3  # 1 次初始 + 2 次重试


def test_action_timeout_ms_full_then_half() -> None:
    assert action_timeout_ms(15_000, 0) == 15_000
    assert action_timeout_ms(15_000, 1) == 7_500
    assert action_timeout_ms(15_000, 2) == 7_500
    assert action_timeout_ms(1_000, 1) == 500
