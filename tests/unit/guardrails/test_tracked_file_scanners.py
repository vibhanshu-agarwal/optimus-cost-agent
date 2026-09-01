from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from tools.tracked_repository_files import tracked_repository_files

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class WalkerCall:
    key: str
    receiver_shape: str


class _WalkerVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.function_name = "<module>"
        self.calls: list[WalkerCall] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous = self.function_name
        self.function_name = node.name
        self.generic_visit(node)
        self.function_name = previous

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_Call(self, node: ast.Call) -> None:
        walker = _walker_name(node.func)
        if walker is not None:
            pattern = _literal_pattern(node)
            key = f"{self.relative_path}:{self.function_name}:{walker}:{pattern}"
            receiver = node.func.value if isinstance(node.func, ast.Attribute) else node.func
            self.calls.append(WalkerCall(key=key, receiver_shape=ast.dump(receiver)))
        self.generic_visit(node)


def _walker_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Attribute) and node.attr in {"glob", "iglob", "rglob"}:
        return node.attr
    if (
        isinstance(node, ast.Attribute)
        and node.attr == "walk"
        and not (isinstance(node.value, ast.Name) and node.value.id == "ast")
    ):
        return node.attr
    return None


def _literal_pattern(node: ast.Call) -> str:
    if not node.args:
        return "<none>"
    value = node.args[0]
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else "<dynamic>"


def _walker_calls_from_source(relative_path: str, source: str) -> tuple[WalkerCall, ...]:
    visitor = _WalkerVisitor(relative_path)
    visitor.visit(ast.parse(source))
    return tuple(visitor.calls)


def _tracked_python_files() -> tuple[Path, ...]:
    return tuple(
        path
        for path in tracked_repository_files(REPO_ROOT, pathspecs=("tests", "tools"))
        if path.suffix == ".py"
    )


def _repository_walker_inventory() -> tuple[WalkerCall, ...]:
    calls: list[WalkerCall] = []
    for path in _tracked_python_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        calls.extend(_walker_calls_from_source(relative, path.read_text(encoding="utf-8")))
    return tuple(calls)


def test_sweep_detects_local_alias_and_parameter_rooted_walkers() -> None:
    source = """
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]

def indirect():
    root = REPO_ROOT / "tests"
    return tuple(root.rglob("*"))

def parameter(project_root):
    return tuple((project_root / "src").rglob("*.py"))
"""

    calls = _walker_calls_from_source("synthetic.py", source)

    assert {call.key for call in calls} == {
        "synthetic.py:indirect:rglob:*",
        "synthetic.py:parameter:rglob:*.py",
    }


# Every surviving filesystem walk needs a reviewed reason. Repository-truth walkers
# have no place in this map: they must use tracked_repository_files instead.
ALLOWED_NON_REPOSITORY_WALKERS: dict[str, str] = {
    "tests/integration/evidence/test_acpx_capture_live.py:test_acpx_capture_streams_into_redaction_gate_without_raw_transcript:rglob:*": "Walks a tmp_path capture created by this test.",
    "tests/integration/evidence/test_collector_redaction_live.py:test_collector_redaction_live_os_keyring_and_public_gate:rglob:*": "Walks the test-created capture tree.",
    "tests/integration/evidence/test_collector_redaction_live.py:test_collector_redaction_live_os_keyring_and_public_gate:rglob:artifact": "Finds generated artifact directories in the test capture.",
    "tests/integration/evidence/test_collector_redaction_live.py:test_collector_redaction_live_os_keyring_and_public_gate:rglob:process_dump-*.bin": "Finds generated dump fixtures in the test capture.",
    "tests/integration/evidence/test_mixed_artifact_gate.py:test_mixed_artifact_dispositions:rglob:*": "Walks a tmp_path mixed-artifact fixture.",
    "tests/integration/evidence/test_mixed_artifact_gate.py:test_mixed_artifact_dispositions:rglob:artifact": "Finds generated artifact directories in a tmp_path fixture.",
    "tests/integration/evidence_handoff/test_authenticated_service.py:test_reviewer_append_success_and_implementer_rejection_live:rglob:*": "Checks files generated beneath the test control root.",
    "tests/integration/evidence_handoff/test_redaction_service.py:_scan_control_and_db:rglob:*": "Scans a live-test control root and database export, not repository source.",
    "tests/investigation/evidence/test_zed_user_data_live.py:_validate_user_data_root:rglob:*": "Validates an operator-supplied Zed user-data tree.",
    "tests/unit/acp/test_main_wiring.py:test_identity_unavailable_at_initial_resolution_never_constructs_store:rglob:debug-acp.ndjson": "Checks that a tmp_path run did not create a debug log.",
    "tests/unit/acp/test_main_wiring.py:test_identity_unavailable_at_initial_resolution_never_constructs_store:rglob:launch-audit.ndjson": "Checks that a tmp_path run did not create a launch audit.",
    "tests/unit/docs/test_plan_directory_hygiene.py:test_plan_archive_is_flat_and_contains_no_registered_live_plan:glob:*.md": "C-MP1 intentionally observes plan-root worktree state, including untracked files.",
    "tests/unit/docs/test_plan_directory_hygiene.py:test_plan_root_contains_only_governance_and_registered_live_plans:glob:*.md": "C-MP1 intentionally observes plan-root worktree state, including untracked files.",
    "tests/unit/docs/test_plan_directory_hygiene.py:test_separately_named_amendments_cannot_be_live_root_plans:glob:*.md": "C-MP1 intentionally observes plan-root worktree state, including untracked files.",
    "tests/unit/evidence/test_gate.py:test_screenshot_with_matching_approval_promotes:rglob:*.partial": "Checks a tmp_path promotion workspace for partial files.",
    "tests/unit/evidence/test_structured_ingress.py:_file_tree_text:rglob:*": "Reads a caller-supplied test fixture tree.",
    "tests/unit/evidence_handoff/test_auth.py:test_no_token_persisted_under_control_root:rglob:*": "Checks a tmp_path control root for leaked tokens.",
    "tests/unit/evidence_handoff/test_signing_key_custody_resolve.py:test_r4_durable_key_lives_in_keyring_not_chmod_file:rglob:*": "Checks a tmp_path custody root for key files.",
    "tests/unit/gates/test_mutation_flow.py:apply_candidate:rglob:*": "Applies mutations to a temporary candidate tree.",
    "tests/unit/tools/plan1126_runtime_audit/test_checkpoints.py:test_checkpoint_write_failure_preserves_prior_file_and_removes_temp:glob:<dynamic>": "Checks a tmp_path checkpoint directory for temporary files.",
    "tests/unit/tools/test_evidence_gather.py:test_redact_promotes_text_and_writes_report_then_inspect_is_body_free:rglob:artifact": "Finds generated artifact directories beneath tmp_path.",
    "tests/unit/tools/test_evidence_gather.py:test_unknown_adapter_fails_before_fixture_mutation:rglob:*": "Snapshots a test-created capture tree before and after failure.",
    "tests/unit/tools/test_probe_p11_zed_session_load.py:_scan_tree_for_canary:rglob:*": "Scans a caller-supplied isolated Zed fixture tree.",
    "tests/unit/tools/test_probe_p11_zed_session_load.py:fake_launch:glob:p1119-real-zed-*": "Discovers test-created throwaway workspaces.",
    "tests/unit/tools/test_probe_p11_zed_session_load.py:fake_launch_with_boundary_asserts:glob:p1119-real-zed-*": "Discovers test-created throwaway workspaces.",
    "tests/unit/tools/test_probe_p11_zed_session_load.py:test_prepare_probe_excludes_gitignored_secret_like_files:rglob:*": "Inspects an isolated temporary Git fixture including ignored files.",
    "tests/unit/tools/test_probe_p11_zed_session_load.py:test_real_zed_revoke_failure_retains_workspace_and_blocks_publish:glob:p1119-real-zed-*": "Discovers retained test workspaces after a simulated failure.",
    "tests/unit/tools/test_probe_p11_zed_session_load.py:test_real_zed_revoke_interrupt_retains_workspace_and_records_remediation:glob:p1119-real-zed-*": "Discovers retained test workspaces after a simulated interrupt.",
    "tests/unit/tools/test_probe_p11_zed_session_load.py:test_real_zed_sidecar_and_bundle_include_bounded_sanitized_child_stderr_excerpt:rglob:*": "Inspects generated files in an isolated probe workspace.",
    "tools/evidence_handoff_live_support/canary.py:scan_raw_canaries:rglob:*": "Scans an operator-selected evidence tree whose files are not repository assets.",
    "tools/probe_p11_zed_session_load.py:throwaway_tree_digest:rglob:*": "Digests a newly created throwaway Zed tree.",
    "tools/run_plan1126_runtime_audit.py:_path_fingerprint:rglob:*": "Handles explicitly supplied external harness directories; repository paths use tracked inventory.",
    "tools/run_redaction_gate_live_evidence.py:_promote_and_record:glob:<dynamic>": "Finds generated live-evidence artifacts selected by the operator.",
    "tools/run_redaction_gate_live_evidence.py:run_drive_acp_only:rglob:*": "Scans a generated ACP evidence workspace.",
    "tools/run_redaction_gate_live_evidence.py:run_inspect:rglob:*": "Inspects a generated live-evidence output tree.",
    "tools/run_redaction_gate_live_evidence.py:run_inspect:rglob:manifest.json": "Finds generated manifests in a live-evidence output tree.",
    "tools/run_redaction_gate_live_evidence.py:run_verify:rglob:*": "Verifies a generated live-evidence output tree.",
    "tools/verify_plan99_noneditable_install.py:select_wheel:glob:*.whl": "Selects a wheel generated in an isolated build directory.",
}


def test_every_filesystem_walker_is_migrated_or_has_a_reviewed_non_repository_reason() -> None:
    inventory = _repository_walker_inventory()
    actual = {call.key for call in inventory}

    assert actual == set(ALLOWED_NON_REPOSITORY_WALKERS), (
        "unreviewed filesystem walkers: "
        f"{sorted(actual - set(ALLOWED_NON_REPOSITORY_WALKERS))}; "
        "stale walker rationales: "
        f"{sorted(set(ALLOWED_NON_REPOSITORY_WALKERS) - actual)}"
    )
    assert all(reason.strip() for reason in ALLOWED_NON_REPOSITORY_WALKERS.values())
