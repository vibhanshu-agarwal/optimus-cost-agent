"""Deterministic fault injection for thread-lifetime races.

``pause_thread_on_return`` reproduces OS preemption at one exact point: when ``function_name``
returns on a thread named ``thread_name``, that thread sleeps for ``seconds`` before continuing.
It changes no production code, affects only threads started inside the ``with`` block, and
restores the previous thread profile on exit.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Iterator


@contextlib.contextmanager
def pause_thread_on_return(
    thread_name: str, function_name: str, seconds: float
) -> Iterator[list[threading.Thread]]:
    """Yield a list that records the paused thread once per injected pause, so a test can
    observe that exact thread by identity rather than by a process-wide name search."""
    paused: list[threading.Thread] = []
    previous = threading.getprofile()

    def _hook(frame, event, arg):  # type: ignore[no-untyped-def]
        if (
            event == "return"
            and frame.f_code.co_name == function_name
            and threading.current_thread().name == thread_name
        ):
            paused.append(threading.current_thread())
            time.sleep(seconds)

    threading.setprofile(_hook)
    try:
        yield paused
    finally:
        threading.setprofile(previous)
