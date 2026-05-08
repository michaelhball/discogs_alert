import time

import pytest

from discogs_alert.util import system as da_system


def test_time_cache_caches_within_window():
    calls = {"n": 0}

    @da_system.time_cache(seconds=3600)
    def fn(x):
        calls["n"] += 1
        return x * 2

    assert fn(3) == 6
    assert fn(3) == 6
    assert fn(3) == 6
    assert calls["n"] == 1


def test_time_cache_distinguishes_args():
    calls = {"n": 0}

    @da_system.time_cache(seconds=3600)
    def fn(x):
        calls["n"] += 1
        return x

    fn(1)
    fn(2)
    fn(2)
    assert calls["n"] == 2


def test_time_cache_invalidates_after_window(monkeypatch: pytest.MonkeyPatch):
    """Forcing `time.time` forward by more than `seconds` should evict the cached value."""

    calls = {"n": 0}
    fake_now = [1_000_000.0]

    def fake_time():
        return fake_now[0]

    monkeypatch.setattr(time, "time", fake_time)

    @da_system.time_cache(seconds=10)
    def fn():
        calls["n"] += 1
        return calls["n"]

    assert fn() == 1
    fake_now[0] += 1  # same window
    assert fn() == 1
    fake_now[0] += 100  # well past the window
    assert fn() == 2


def test_time_cache_exposes_cache_clear():
    calls = {"n": 0}

    @da_system.time_cache(seconds=3600)
    def fn():
        calls["n"] += 1
        return calls["n"]

    fn()
    fn()
    assert calls["n"] == 1
    fn.cache_clear()
    fn()
    assert calls["n"] == 2


def test_time_cache_exposes_cache_info():
    @da_system.time_cache(seconds=3600)
    def fn(x):
        return x

    fn(1)
    fn(1)
    info = fn.cache_info()
    assert info.hits >= 1
    assert info.misses >= 1


def test_time_cache_rejects_non_positive_seconds():
    with pytest.raises(ValueError):
        da_system.time_cache(seconds=0)
    with pytest.raises(ValueError):
        da_system.time_cache(seconds=-5)
