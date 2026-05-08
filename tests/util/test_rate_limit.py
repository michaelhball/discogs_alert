import pytest

from discogs_alert.util.rate_limit import RateLimitGuard


def _guard(min_remaining=2, sleep_seconds=60):
    """Build a guard whose sleep is recorded into a list (instead of actually sleeping)."""

    sleeps = []
    guard = RateLimitGuard(min_remaining=min_remaining, sleep_seconds=sleep_seconds, sleep_fn=sleeps.append)
    return guard, sleeps


def test_init_validates_min_remaining():
    with pytest.raises(ValueError):
        RateLimitGuard(min_remaining=-1)


def test_init_validates_sleep_seconds():
    with pytest.raises(ValueError):
        RateLimitGuard(sleep_seconds=0)


def test_starts_with_no_known_state():
    guard, _ = _guard()
    assert guard.remaining is None
    assert guard.limit is None
    assert guard.used is None


def test_update_from_headers_parses_all_three():
    guard, _ = _guard()
    guard.update_from_headers(
        {
            "X-Discogs-Ratelimit": "60",
            "X-Discogs-Ratelimit-Used": "5",
            "X-Discogs-Ratelimit-Remaining": "55",
        }
    )
    assert guard.limit == 60
    assert guard.used == 5
    assert guard.remaining == 55


def test_update_from_headers_ignores_missing():
    guard, _ = _guard()
    guard.update_from_headers({"X-Discogs-Ratelimit": "60"})
    assert guard.limit == 60
    assert guard.used is None
    assert guard.remaining is None


def test_update_from_headers_ignores_malformed(caplog):
    guard, _ = _guard()
    guard.remaining = 50  # prior known state
    guard.update_from_headers({"X-Discogs-Ratelimit-Remaining": "not-a-number"})
    assert guard.remaining == 50  # untouched


def test_before_request_does_not_sleep_initially():
    guard, sleeps = _guard()
    guard.before_request()
    assert sleeps == []


def test_before_request_does_not_sleep_when_plenty_left():
    guard, sleeps = _guard()
    guard.update_from_headers({"X-Discogs-Ratelimit-Remaining": "30"})
    guard.before_request()
    assert sleeps == []


def test_before_request_sleeps_when_close_to_limit():
    guard, sleeps = _guard(min_remaining=2, sleep_seconds=60)
    guard.update_from_headers({"X-Discogs-Ratelimit-Remaining": "2"})
    guard.before_request()
    assert sleeps == [60]


def test_before_request_clears_remaining_after_sleep():
    """Once we've slept, the per-minute window has reset; we should not sleep
    on the next call without fresh header data.
    """

    guard, sleeps = _guard()
    guard.update_from_headers({"X-Discogs-Ratelimit-Remaining": "1"})
    guard.before_request()
    guard.before_request()
    assert sleeps == [60]  # only the first call slept


def test_min_remaining_threshold_is_inclusive():
    guard, sleeps = _guard(min_remaining=5)
    guard.update_from_headers({"X-Discogs-Ratelimit-Remaining": "5"})
    guard.before_request()
    assert sleeps == [60]
