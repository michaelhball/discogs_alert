import functools
import time


def time_cache(seconds: int, maxsize=None, typed=False):
    """Least-recently-used cache decorator with time-based cache invalidation.

    The cache key is salted with `int(time.time() / seconds)`, so each `seconds`-long
    window produces a fresh cache key (and therefore a fresh call to `fn`). Old keys
    are evicted by the LRU policy when `maxsize` is set.

    Inspired by https://stackoverflow.com/a/63674816/16592116.

    The returned wrapper exposes `cache_clear()` and `cache_info()` (forwarded from
    the underlying `functools.lru_cache`), which is useful for tests and for forcing
    a refresh.

    Args:
        seconds: Time-to-live for cached results, in seconds. Must be positive.
        maxsize: Maximum cache size (see `functools.lru_cache`).
        typed: Cache on distinct input types (see `functools.lru_cache`).
    """

    if seconds <= 0:
        raise ValueError("`seconds` must be a positive integer")

    def _decorator(fn):
        @functools.lru_cache(maxsize=maxsize, typed=typed)
        def _new(*args, __time_salt, **kwargs):
            return fn(*args, **kwargs)

        @functools.wraps(fn)
        def _wrapped(*args, **kwargs):
            return _new(*args, **kwargs, __time_salt=int(time.time() / seconds))

        _wrapped.cache_clear = _new.cache_clear
        _wrapped.cache_info = _new.cache_info
        return _wrapped

    return _decorator
