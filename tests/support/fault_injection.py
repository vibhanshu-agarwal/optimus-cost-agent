"""Deterministic fault injection for thread- and process-lifetime races.

``pause_thread_on_return`` reproduces OS preemption at one exact point: when ``function_name``
returns on a thread named ``thread_name``, that thread sleeps for ``seconds`` before continuing.
It changes no production code, affects only threads started inside the ``with`` block, and
restores the previous thread profile on exit.

``descendant_tree`` builds a child whose descendants a snapshot tree kill cannot reach.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Iterator
from pathlib import Path

from tests.support.concurrency import announce_pid_code

TREE_SHAPES = ("parent-alive", "parent-exited", "middle-exited")


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


def descendant_tree(directory: Path | str, shape: str, *, then: str = "", sleep_seconds: float = 30.0) -> tuple[str, tuple[str, ...]]:
    """``python -c`` code for a child that forms a process tree, and the roles it announces.

    Every member announces its pid in ``directory`` (``announce_pid_code``) as it starts.

    * ``parent-alive``: the child starts a grandchild; both sleep.
    * ``parent-exited``: the child starts a grandchild and exits, orphaning it.
    * ``middle-exited``: the child sleeps; a middle process starts the grandchild and exits, so
      no walk of parent pids from the child reaches the grandchild.

    A snapshot tree kill (``taskkill /T``) misses the grandchild in the last two shapes every
    time. ``then`` runs in the child once its descendants are started.
    """
    if shape not in TREE_SHAPES:
        raise ValueError(f"unknown tree shape {shape!r}")
    sleep = f"import time; time.sleep({sleep_seconds!r})"
    grandchild = announce_pid_code(directory, "grandchild") + "; " + sleep
    spawn = "import subprocess, sys; subprocess.Popen([sys.executable, '-c', {!r}])"
    if shape == "middle-exited":
        middle = announce_pid_code(directory, "middle") + "; " + spawn.format(grandchild)
        start, roles = spawn.format(middle), ("child", "middle", "grandchild")
    else:
        start, roles = spawn.format(grandchild), ("child", "grandchild")
    tail = "pass" if shape == "parent-exited" else sleep
    parts = [announce_pid_code(directory, "child"), start, then, tail]
    return "; ".join(part for part in parts if part), roles
