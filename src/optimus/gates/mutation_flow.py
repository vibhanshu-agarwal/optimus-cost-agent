from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from optimus.gates.fitness import CompositeGateResult, FitnessCheck, FitnessGateRunner
from optimus.gates.shadow_workspace import ShadowWorkspace, promote_shadow_changes
from optimus.runtime.mutation import MutationKind, assert_mutation_allowed
from optimus.runtime.state import RuntimeContext


class ShadowWorkspaceMutationRunner:
    def __init__(
        self,
        *,
        checks_factory: Callable[[Path], tuple[FitnessCheck, ...]],
        ignore_patterns: tuple[str, ...] = (),
        fail_after_promoted_paths: int | None = None,
    ) -> None:
        self._checks_factory = checks_factory
        self._ignore_patterns = ignore_patterns
        self._fail_after_promoted_paths = fail_after_promoted_paths

    def run(
        self,
        *,
        context: RuntimeContext,
        workspace_root: str | Path,
        apply_candidate: Callable[[Path], object],
    ) -> CompositeGateResult:
        assert_mutation_allowed(context, MutationKind.WRITE_FILE)
        shadow = ShadowWorkspace(workspace_root=Path(workspace_root), ignore_patterns=self._ignore_patterns)
        try:
            apply_candidate(shadow.shadow_root)
            result = FitnessGateRunner(checks=self._checks_factory(shadow.shadow_root)).run()
            if result.passed:
                promote_shadow_changes(
                    shadow.promotion_plan(),
                    fail_after_promoted_paths=self._fail_after_promoted_paths,
                )
            return result
        finally:
            shadow.cleanup()
