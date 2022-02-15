import functools
import time


def time_cache(seconds: int, maxsize=None, typed=False):
    """Least-recently-used cache decorator with time-based cache invalidation.
    Inspired by https://stackoverflow.com/a/63674816/16592116

    Args:
        max_age: Time to live for cached results (in seconds).
        maxsize: Maximum cache size (see `functools.lru_cache`).
        typed: Cache on distinct input types (see `functools.lru_cache`).
    """

    def _decorator(fn):
        @functools.lru_cache(maxsize=maxsize, typed=typed)
        def _new(*args, __time_salt, **kwargs):
            return fn(*args, **kwargs)

        @functools.wraps(fn)
        def _wrapped(*args, **kwargs):
            return _new(*args, **kwargs, __time_salt=int(time.time() / seconds))

        return _wrapped

    return _decorator
