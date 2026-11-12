"""One background worker for analytics refreshes inside the API process.

Heavy work (retraining a model, recomputing a snapshot) must never compete
with requests for the CPU. All refreshes go through a single worker thread,
and each key refreshes at most once per ``min_interval`` seconds, however many
orders arrive. Requests keep getting the last result instantly meanwhile.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger('shopsense.refresher')
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix='analytics-refresh')
_LOCK = threading.Lock()
_IN_FLIGHT: set[str] = set()
_LAST_START: dict[str, float] = {}


def submit(key: str, fn, min_interval: float) -> bool:
    """Queue ``fn()`` unless the key is already queued or ran too recently."""
    now = time.time()
    with _LOCK:
        if key in _IN_FLIGHT or now - _LAST_START.get(key, 0) < min_interval:
            return False
        _IN_FLIGHT.add(key)
        _LAST_START[key] = now

    def run():
        try:
            fn()
        except Exception:  # a failed refresh keeps serving the previous result
            log.exception('background refresh %s failed', key)
        finally:
            with _LOCK:
                _IN_FLIGHT.discard(key)
    _EXECUTOR.submit(run)
    return True


def reset():
    with _LOCK:
        _IN_FLIGHT.clear()
        _LAST_START.clear()
