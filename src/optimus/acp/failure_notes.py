"""Attach a secondary failure to an exception that is already propagating -- safely.

Seam 2, checkpoint B (round 2, R4). ``BaseException.add_note`` creates the ``__notes__``
attribute through ordinary attribute assignment on first use. Several startup failures in
the serving composition path are frozen dataclasses (``PreflightFailure``,
``StartupConfigurationError``, ``SubprocessEnvConfigurationError``), whose ``__setattr__``
refuses that assignment: ``add_note`` then raises ``FrozenInstanceError`` and REPLACES the
failure the operator needed to see with an attribute error from the cleanup annotation.

This helper records the note where ``add_note`` would have put it, through the base-class
setattr, and never raises: a note that cannot be attached must not skip the remaining
cleanup or substitute itself for the primary failure.
"""

from __future__ import annotations


def attach_failure_note(failure: BaseException, note: str) -> None:
    """``add_note`` for any exception, including frozen-dataclass ones; never raises."""
    try:
        failure.add_note(note)
        return
    except AttributeError:
        # FrozenInstanceError is an AttributeError: the dataclass refused `__notes__`.
        pass
    except Exception:  # noqa: BLE001 - a note is diagnostic; it must never become the failure
        return
    try:
        notes = list(getattr(failure, "__notes__", None) or ())
        notes.append(note)
        object.__setattr__(failure, "__notes__", notes)
    except Exception:  # noqa: BLE001 - see above
        return
