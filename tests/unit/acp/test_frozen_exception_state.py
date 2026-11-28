"""#685 class fix: every frozen dataclass exception in `src` accepts the state the interpreter and the standard library
set on any exception (`__traceback__`, `__cause__`, `__context__`, `__suppress_context__`, `__notes__`), so passing
through a `@contextmanager`, getting a note, or being selected by `cleanup_failure` never replaces it with
`FrozenInstanceError`. Its own fields stay frozen; equality, hashing, and copy/pickle behaviour are unchanged."""

from __future__ import annotations

import ast
import copy
import dataclasses
import importlib
import pickle
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from optimus.acp.process_lifecycle import ProcessLifecycle, cleanup_failure, signal_handlers
from tests.unit.acp.test_raise_preserving_failure import FAILURES
from tools.tracked_repository_files import tracked_repository_files
from tools.verify_exception_site_disposition import discover

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src"
FROZEN = sorted(name for name in FAILURES if dataclasses.is_dataclass(FAILURES[name]()))


def _frozen_exception_classes_in_src() -> set[str]:
    found: set[str] = set()
    for path in (p for p in tracked_repository_files(_REPO_ROOT, pathspecs=("src",)) if p.suffix == ".py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef) and node.bases and any(
                isinstance(d, ast.Call) and getattr(d.func, "id", getattr(d.func, "attr", "")) == "dataclass"
                and any(k.arg == "frozen" and getattr(k.value, "value", False) for k in d.keywords)
                for d in node.decorator_list
            ):
                module = ".".join(path.relative_to(_SRC).with_suffix("").parts).removesuffix(".__init__")
                cls = getattr(importlib.import_module(module), node.name, None)
                if isinstance(cls, type) and issubclass(cls, BaseException):
                    found.add(f"{cls.__module__}.{cls.__qualname__}")
    return found


def test_the_sweep_covers_every_frozen_exception_in_src() -> None:
    # A new frozen dataclass exception must be added to FAILURES, so every test below covers it.
    # Qualified names, so a second class of the same name elsewhere cannot hide behind the first.
    expected = {f"{type(e).__module__}.{type(e).__qualname__}" for e in (FAILURES[kind]() for kind in FROZEN)}
    assert _frozen_exception_classes_in_src() == expected


@contextmanager
def _context() -> Iterator[None]:
    yield


@pytest.mark.parametrize("kind", FROZEN)
def test_a_frozen_exception_passes_through_a_context_manager_unchanged(kind: str) -> None:
    failure = FAILURES[kind]()
    with pytest.raises(BaseException) as raised:  # noqa: PT011 - the assertion is identity, below
        with _context():
            raise failure
    assert raised.value is failure


def test_a_frozen_refusal_passes_through_the_cli_signal_handlers_unchanged() -> None:
    failure = FAILURES["LocalInfrastructureError"]()
    with pytest.raises(BaseException) as raised:  # noqa: PT011 - the assertion is identity, below
        with signal_handlers(ProcessLifecycle()):
            raise failure
    assert raised.value is failure


@pytest.mark.parametrize("kind", FROZEN)
def test_a_frozen_exception_takes_a_note(kind: str) -> None:
    failure = FAILURES[kind]()
    failure.add_note("synthetic note")
    assert failure.__notes__ == ["synthetic note"]


def test_cleanup_failure_keeps_its_stage_note_on_a_frozen_primary() -> None:
    primary = FAILURES["LocalInfrastructureError"]()
    assert cleanup_failure([("startup", primary), ("gateway", OSError("synthetic stop"))]) is primary
    assert primary.__notes__ == ["optimus cleanup stages: gateway; count=1"]


@pytest.mark.parametrize("kind", FROZEN)
def test_fields_stay_frozen_and_equality_hashing_copying_are_unchanged(kind: str) -> None:
    first, second = FAILURES[kind](), FAILURES[kind]()
    for field in dataclasses.fields(first):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(first, field.name, getattr(first, field.name))
        with pytest.raises(dataclasses.FrozenInstanceError):
            delattr(first, field.name)
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.unrelated = 1  # type: ignore[attr-defined]
    assert first == second and first is not second
    assert hash(first) == hash(second)
    first.add_note("synthetic")  # exception state is not a field: equality and hashing ignore it
    first.__traceback__ = None
    assert first == second
    # No caller copies or pickles these; the dataclass __init__ leaves `args` empty, so both already fail. Unchanged.
    for clone in (copy.copy, copy.deepcopy, lambda e: pickle.loads(pickle.dumps(e))):
        with pytest.raises(TypeError):
            clone(first)


def test_frozen_exception_returns_the_class_it_decorates():
    # The exception-site verifier trusts this decorator as class-preserving; a wrapper here would silently widen that gate.
    from optimus.runtime.frozen_exception import frozen_exception

    @dataclasses.dataclass(frozen=True)
    class Sample(Exception):
        reason: str

    assert frozen_exception(Sample) is Sample


def test_frozen_exception_module_binds_its_export_once_by_its_def():
    # The exception-site verifier also requires this module to bind frozen_exception only by its def, statically.
    source = (_SRC / "optimus" / "runtime" / "frozen_exception.py").read_text(encoding="utf-8")
    assert "untrusted_decorators" not in discover({"src/optimus/runtime/frozen_exception.py": source})
    tree = ast.parse(source)
    assert [node.name for node in tree.body if isinstance(node, ast.FunctionDef)].count("frozen_exception") == 1
