"""Reuse normalized snapshots only inside one synchronous read operation."""

from contextvars import ContextVar
from functools import wraps


_read_cache = ContextVar('academic_snapshot_component_read_cache', default=None)


def current_component_read_cache():
    return _read_cache.get()


def snapshot_component_read_scope(method):
    @wraps(method)
    def read(*args, **kwargs):
        if _read_cache.get() is not None:
            return method(*args, **kwargs)
        token = _read_cache.set({})
        try:
            return method(*args, **kwargs)
        finally:
            _read_cache.reset(token)
    return read
