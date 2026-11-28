"""Frozen dataclass exceptions that still behave as exceptions (#685).

``@dataclass(frozen=True)`` writes a ``__setattr__`` into the class that refuses every assignment. The interpreter and
the standard library assign exception state as ordinary attributes: ``contextlib`` sets ``__traceback__`` when an
exception leaves a ``@contextmanager``, ``add_note`` creates ``__notes__``, and re-raising code restores ``__cause__``
and ``__context__``. On a frozen exception each of those raised ``FrozenInstanceError``, which then replaced the
exception. A base class cannot fix this, because the dataclass-generated method is set on each class itself, so this
decorator wraps that method once per class: exception state goes through, and the fields stay frozen.
"""

from __future__ import annotations

from typing import Any, TypeVar

_EXCEPTION_STATE = frozenset({"__traceback__", "__cause__", "__context__", "__suppress_context__", "__notes__"})

_E = TypeVar("_E", bound=type[BaseException])


def frozen_exception(cls: _E) -> _E:
    """Apply above ``@dataclass(frozen=True)`` on an exception class."""
    frozen_setattr = cls.__setattr__

    def __setattr__(self: BaseException, name: str, value: Any) -> None:
        if name in _EXCEPTION_STATE:
            object.__setattr__(self, name, value)
        else:
            frozen_setattr(self, name, value)

    cls.__setattr__ = __setattr__  # type: ignore[method-assign, assignment]
    return cls
