from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TypeVar

from optimus.runtime.mutation import MutationKind, assert_mutation_allowed
from optimus.runtime.state import RuntimeContext

ShellResult = TypeVar("ShellResult")
PatchResult = TypeVar("PatchResult")


def write_file(path: str | Path, content: str, *, context: RuntimeContext) -> None:
    assert_mutation_allowed(context, MutationKind.WRITE_FILE)
    Path(path).write_text(content, encoding="utf-8")


def shell_exec(
    command: Sequence[str],
    *,
    context: RuntimeContext,
    runner: Callable[[list[str]], ShellResult] | None = None,
) -> ShellResult | subprocess.CompletedProcess[str]:
    assert_mutation_allowed(context, MutationKind.SHELL_EXEC)
    if runner is not None:
        return runner(list(command))
    return subprocess.run(list(command), check=False, text=True, capture_output=True)


def shadow_apply(
    patch_text: str,
    *,
    context: RuntimeContext,
    applier: Callable[[str], PatchResult],
) -> PatchResult:
    assert_mutation_allowed(context, MutationKind.SHADOW_APPLY)
    return applier(patch_text)
