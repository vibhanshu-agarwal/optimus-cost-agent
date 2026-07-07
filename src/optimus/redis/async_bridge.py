from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import TypeVar

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_loop_lock = threading.Lock()


def shutdown_background_loop() -> None:
    """Stop the dedicated Redis bridge loop (for test session teardown)."""
    global _loop, _loop_thread
    with _loop_lock:
        if _loop is None:
            return
        _loop.call_soon_threadsafe(_loop.stop)
        if _loop_thread is not None:
            _loop_thread.join(timeout=5.0)
        _loop = None
        _loop_thread = None


def _background_loop() -> asyncio.AbstractEventLoop:
    global _loop, _loop_thread
    with _loop_lock:
        if _loop is None:
            loop = asyncio.new_event_loop()

            def _run() -> None:
                asyncio.set_event_loop(loop)
                loop.run_forever()

            thread = threading.Thread(target=_run, name="optimus-redis-async", daemon=True)
            thread.start()
            _loop = loop
            _loop_thread = thread
        return _loop


def sync_await(coro: Coroutine[object, object, T]) -> T:
    """Run an async Redis coroutine from synchronous AgentRunner / harness code."""
    return asyncio.run_coroutine_threadsafe(coro, _background_loop()).result()
