#!/usr/bin/env python3
"""Re-probe ACP ``session/load`` with independent acpx, without launching Zed.

The one required argument is a parent directory for a throwaway workspace. The
probe creates and removes only a unique child of that directory. It asks the
operator to approve that exact temporary workspace through ``optimus-trust``,
then revokes and verifies removal of that approval before deleting the child.
It queries ``Zed --version`` for point-in-time context but never starts Zed,
changes Zed settings, or touches an existing Zed profile.

acpx is the ACP client for all protocol traffic.  The probe makes a session in
one isolated acpx home, exports it, imports it into a second isolated home, and
uses a non-prompt configuration operation to force acpx's saved-session
reconnect.  acpx invokes ``session/resume`` when advertised and ``session/load``
only when its live capability payload advertises it; otherwise the probe records
the agent-side capability gate as indeterminate.  No prompt, Gateway request,
origin-A fixture, or correlation launch is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PureWindowsPath
from typing import Any

from optimus.acp.framing import FramingError, parse_content_length
from optimus_security.sanitization import EVIDENCE_REDACTION_POLICY, sanitize_for_persistence

PLAN1119_SCHEMA = "plan-11-19-zed-session-load-reprobe-v1"
PLAN1119_RUN_ID = "plan1119-zed-reprobe"
_ISOLATED_LAUNCHER_NAME = "isolated_optimus_agent.py"


class Finding(StrEnum):
    """The only verdicts this reachability probe can emit."""

    REACHABLE = "REACHABLE"
    UNREACHABLE = "UNREACHABLE"
    INDETERMINATE = "INDETERMINATE"


class IndeterminateReason(StrEnum):
    """Why a non-verdict must not be misread as an observation about Zed."""

    PRECONDITION_UNMET = "PRECONDITION_UNMET"
    INTERNAL_CAPABILITY_UNAVAILABLE = "INTERNAL_CAPABILITY_UNAVAILABLE"
    OBSERVATION_INCOMPLETE = "OBSERVATION_INCOMPLETE"
    CLEANUP_UNVERIFIED = "CLEANUP_UNVERIFIED"
    HERMETIC_INVOCATION_UNAVAILABLE = "HERMETIC_INVOCATION_UNAVAILABLE"
    ALREADY_RUNNING_ZED = "ALREADY_RUNNING_ZED"
    RELAY_FAILURE = "RELAY_FAILURE"
    ISOLATION_PREDICATE_FAILED = "ISOLATION_PREDICATE_FAILED"
    LIVE_LAUNCH_UNAUTHORIZED = "LIVE_LAUNCH_UNAUTHORIZED"


@dataclass(frozen=True)
class SessionLoadEvaluation:
    """Classified live exchange while retaining its exact safe protocol payloads."""

    finding: Finding
    capability_payload: dict[str, Any] | None
    load_exchange: dict[str, Any] | None


@dataclass(frozen=True)
class CommandResult:
    """Captured command details from an independent acpx invocation."""

    command: list[str]
    returncode: int
    stdout: str
    stderr: str


class ProbeError(RuntimeError):
    """A bounded precondition or execution failure that leaves the verdict indeterminate."""

    def __init__(self, stage: str, message: str, command_result: CommandResult | None = None) -> None:
        self.stage = stage
        self.command_result = command_result
        super().__init__(message)


ALLOWED_PROBE_SEMANTICS = {
    "initialize.agentCapabilities.loadSession": True,
    "request.session/load.response.result": {},
}
ALLOWED_PROBE_CHANGED_PATHS = ("src/optimus/acp/spec.py",)
_INITIALIZE_NO_LOAD_SESSION = (
    '            # session/load remains P11-FEAT-ZED-RESUME; do not advertise loadSession.\n'
    '            "sessionCapabilities": {},\n'
)
_INITIALIZE_TEMPORARY_LOAD_SESSION = '            "loadSession": True,\n            "sessionCapabilities": {},\n'
_SESSION_PROMPT_BRANCH = (
    '        if method == "session/prompt":\n'
    "            return await self._handle_session_prompt(request)\n"
)
_SESSION_LOAD_BRANCH = (
    '        if method == "session/prompt":\n'
    "            return await self._handle_session_prompt(request)\n"
    '        if method == "session/load":\n'
    '            return success_response(request_id=request.get("id"), result={})\n'
)


@dataclass(frozen=True)
class ProbePatchPlan:
    """Allowlisted semantic patch applied only to the throwaway isolated source tree."""

    changed_paths: tuple[str, ...]
    capability_patch: Mapping[str, Any]
    load_response: Mapping[str, Any]


@dataclass(frozen=True)
class RelayExchange:
    """Sanitized post-run classification of one captured ACP request/response pair."""

    request: Mapping[str, Any]
    response: Mapping[str, Any]


@dataclass(frozen=True)
class IsolationEvidence:
    """Four normal-operation isolation predicates plus cleanup dry-run/observed removal."""

    normal_agent_load_session_advertised: bool
    isolated_probe_load_session_advertised: bool
    normal_source_sha256_before: str
    normal_source_sha256_after: str
    isolated_source_root: str
    isolated_build_root: str
    hermetic_zed_root: str
    cleanup_dry_run_verified: bool
    cleanup_verified: bool

    @property
    def prelaunch_predicates_pass(self) -> bool:
        return (
            not self.normal_agent_load_session_advertised
            and self.isolated_probe_load_session_advertised
            and bool(self.normal_source_sha256_before)
            and bool(self.normal_source_sha256_after)
            and self.normal_source_sha256_before == self.normal_source_sha256_after
            and self.cleanup_dry_run_verified
        )

    @property
    def all_four_predicates_pass(self) -> bool:
        return self.prelaunch_predicates_pass and self.cleanup_verified


@dataclass(frozen=True)
class ProbePreparation:
    """Throwaway isolated source/build locations plus the pre-launch normal digest."""

    isolated_source_root: str
    isolated_build_root: str
    hermetic_zed_root: str
    normal_root: str
    normal_commit: str | None
    normal_source_sha256_before: str
    patch_plan: ProbePatchPlan
    cleanup_dry_run_verified: bool


DEFAULT_PROBE_PATCH_PLAN = ProbePatchPlan(
    changed_paths=ALLOWED_PROBE_CHANGED_PATHS,
    capability_patch={"loadSession": True},
    load_response={},
)


def validate_probe_patch_plan(plan: ProbePatchPlan) -> None:
    """Reject any patch surface beyond the temporary initialize capability and empty load result."""
    if (
        plan.changed_paths != ALLOWED_PROBE_CHANGED_PATHS
        or dict(plan.capability_patch) != {"loadSession": True}
        or dict(plan.load_response) != {}
    ):
        raise ProbeError("validate_probe_patch_plan", "unexpected patch surface")
    if ALLOWED_PROBE_SEMANTICS["initialize.agentCapabilities.loadSession"] is not True:
        raise ProbeError("validate_probe_patch_plan", "unexpected patch surface")
    if ALLOWED_PROBE_SEMANTICS["request.session/load.response.result"] != {}:
        raise ProbeError("validate_probe_patch_plan", "unexpected patch surface")


def validate_isolation_evidence(evidence: IsolationEvidence, *, require_cleanup: bool = True) -> None:
    """Fail closed when any isolation predicate or required digest/cleanup field is missing."""
    if evidence.normal_agent_load_session_advertised:
        raise ProbeError("validate_isolation_evidence", "normal capability payload contains loadSession")
    if not evidence.isolated_probe_load_session_advertised:
        raise ProbeError("validate_isolation_evidence", "isolated probe must advertise loadSession")
    if not evidence.normal_source_sha256_before or not evidence.normal_source_sha256_after:
        raise ProbeError("validate_isolation_evidence", "source digest is missing")
    if evidence.normal_source_sha256_before != evidence.normal_source_sha256_after:
        raise ProbeError("validate_isolation_evidence", "source digest drifted")
    if not evidence.cleanup_dry_run_verified:
        raise ProbeError("validate_isolation_evidence", "cleanup dry-run not verified")
    if require_cleanup and not evidence.cleanup_verified:
        raise ProbeError("validate_isolation_evidence", "unremoved scratch roots remain")


def classify_real_zed_result(exchange: RelayExchange | None, isolation: IsolationEvidence) -> Finding:
    """Classify only after all four isolation predicates pass; otherwise stay indeterminate."""
    if not isolation.all_four_predicates_pass:
        return Finding.INDETERMINATE
    if exchange is None:
        return Finding.INDETERMINATE
    request = exchange.request if isinstance(exchange.request, Mapping) else {}
    response = exchange.response if isinstance(exchange.response, Mapping) else {}
    if request.get("method") == "session/load" and response.get("result") == {}:
        return Finding.REACHABLE
    if isinstance(response.get("error"), Mapping):
        return Finding.UNREACHABLE
    return Finding.INDETERMINATE


RELAY_EXTRACT_SOURCE = "opaque-relay-post-run"
REPORTS_ROOT = Path(__file__).resolve().parents[1] / "reports"
DEFAULT_ZED_LAUNCH_TIMEOUT_SECONDS = 180.0
MIN_ZED_LAUNCH_TIMEOUT_SECONDS = 60.0
MAX_ZED_LAUNCH_TIMEOUT_SECONDS = 900.0
_USER_DATA_HELP_LINE = re.compile(r"user[\s_-]*data", re.I)
_HELP_FLAG = re.compile(r"(--[A-Za-z0-9][A-Za-z0-9-]*)")
_RELAY_SCRIPT = Path(__file__).resolve().parent / "plan117_custody_relay.py"


@dataclass(frozen=True)
class ZedInvocation:
    """Current-version hermetic Zed launch descriptor discovered from this install, not a historical flag."""

    argv: tuple[str, ...]
    user_data_root: str | None
    discovered_from: str
    version: str = ""
    executable_sha256: str = ""
    environment_bind: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ZedInvocationEvidence:
    """Recorded no-launch discovery of the installed Zed binary and hermetic bind."""

    invocation: ZedInvocation
    executable: str
    help_sha256: str
    hermetic_root: str
    already_running_zed: bool = False
    zed_to_agent_sha256: str | None = None
    agent_to_zed_sha256: str | None = None


@dataclass(frozen=True)
class AcpxBaselineEvidence:
    """Independent acpx confirmation of the isolated probe advertisement; not a Zed finding."""

    acpx_version: str
    acpx_executable: str
    acpx_sha256: str
    capability_payload: Mapping[str, Any]
    origin_a_launches: int
    session_load_exchange: Mapping[str, Any] | None = None


def _ambient_profile_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    for key in ("APPDATA", "LOCALAPPDATA", "USERPROFILE"):
        raw = os.environ.get(key, "").strip()
        if raw:
            roots.append(Path(raw))
            roots.append(Path(raw) / "Zed")
    return tuple(roots)


def validate_zed_invocation(
    invocation: ZedInvocation,
    *,
    hermetic_root: Path,
    ambient_profile_roots: Sequence[Path] | None = None,
) -> None:
    """Reject missing discovery, ambient profiles, and user-data paths outside the hermetic root."""
    if not invocation.discovered_from.strip() or invocation.user_data_root is None:
        raise ProbeError("zed_invocation", "current-version hermetic invocation descriptor is missing")
    user_resolved = Path(invocation.user_data_root).resolve()
    hermetic = hermetic_root.resolve()
    ambient = tuple(path.resolve() for path in (ambient_profile_roots or _ambient_profile_roots()))
    for profile in ambient:
        if user_resolved == profile:
            raise ProbeError(
                "zed_invocation",
                "current-version hermetic invocation must not use ambient profile",
            )
        # Default Zed data lives under AppData\Zed; a nested hermetic copy there is still ambient.
        if profile.name.casefold() == "zed" and (user_resolved == profile or user_resolved.is_relative_to(profile)):
            raise ProbeError(
                "zed_invocation",
                "current-version hermetic invocation must not use ambient profile",
            )
    if user_resolved != hermetic and not user_resolved.is_relative_to(hermetic):
        raise ProbeError("zed_invocation", "user-data path is outside the hermetic root")


def _discover_user_data_flag(help_output: str) -> str | None:
    for line in help_output.splitlines():
        if _USER_DATA_HELP_LINE.search(line):
            match = _HELP_FLAG.search(line)
            if match:
                return match.group(1)
    return None


def discover_hermetic_zed_invocation(
    *,
    executable: Path,
    version_output: str,
    help_output: str,
    executable_sha256: str,
    hermetic_root: Path,
) -> ZedInvocation:
    """Bind Zed to a new hermetic root using a flag found in this version's help text.

    Hermetic isolation is the ``--user-data-dir`` (or discovered equivalent) argument only.
    Do not rewrite USERPROFILE/APPDATA for the GUI process: that prevents a normal window
    on Windows while still satisfying the ambient-profile prohibition.

    Launch argv[0] must be the editor app binary when discoverable. The Windows CLI under
    ``bin\\Zed.exe`` often exits after an IPC handoff and never shows a window.
    """
    hermetic = hermetic_root.resolve()
    flag = _discover_user_data_flag(help_output)
    if flag is None:
        raise ProbeError("zed_discovery", "current-version hermetic invocation flag was not discovered")
    launch_binary = _parse_zed_app_path(version_output) or _sibling_zed_app_binary(executable) or executable
    return ZedInvocation(
        argv=(str(launch_binary), flag, str(hermetic)),
        user_data_root=str(hermetic),
        discovered_from="zed --help",
        version=version_output.strip(),
        executable_sha256=executable_sha256,
        environment_bind=(),
    )


def build_real_zed_launch_argv(
    invocation: ZedInvocation,
    *,
    workspace: Path,
    launch_help: str,
) -> tuple[str, ...]:
    """Compose the live argv from the *launch* binary's help, not the CLI's help.

    Windows ships ``bin\\Zed.exe`` (CLI: ``--new``/``--wait``/``--foreground``) and
    ``Zed.exe`` (app: ``--user-data-dir`` + paths). Appending CLI-only flags to the app
    binary exits non-zero with no window (Plan 11.19 shot 2, returncode 2).
    """
    argv = list(invocation.argv)
    for flag in ("--foreground", "--new", "--wait"):
        if _help_lists_long_flag(launch_help, flag):
            argv.append(flag)
    argv.append(str(workspace))
    return tuple(argv)


def _help_lists_long_flag(help_output: str, flag: str) -> bool:
    """Return True when ``help_output`` documents ``flag`` as a long option token."""
    pattern = re.compile(rf"(?m)(?:^|\s){re.escape(flag)}(?:\s|,|=|$)")
    return pattern.search(help_output) is not None


def _parse_zed_app_path(version_output: str) -> Path | None:
    """Extract the GUI binary path from ``zed --version`` when present."""
    marker = " – "
    if marker not in version_output:
        marker = " - "
    if marker not in version_output:
        return None
    raw = version_output.rsplit(marker, 1)[-1].strip()
    raw = raw.removeprefix("\\\\?\\").removeprefix("\\\\?/")
    candidate = Path(raw)
    return candidate if candidate.is_file() else None


def _sibling_zed_app_binary(cli_or_app: Path) -> Path | None:
    """Prefer ``…/Zed/Zed.exe`` when the resolved path is ``…/Zed/bin/Zed.exe``."""
    resolved = cli_or_app.resolve()
    if resolved.name.lower() != "zed.exe":
        return None
    if resolved.parent.name.lower() != "bin":
        return None
    sibling = resolved.parent.parent / "Zed.exe"
    return sibling if sibling.is_file() else None


def exchange_from_relay_extract(extract: Mapping[str, Any]) -> RelayExchange | None:
    """Classify captured traffic only from a sanitized post-run opaque-relay extract."""
    if extract.get("source") != RELAY_EXTRACT_SOURCE:
        raise ProbeError("relay_extract", "classification requires a sanitized post-run relay extract")
    for key in ("zed_to_agent_sha256", "agent_to_zed_sha256"):
        digest = extract.get(key)
        if not isinstance(digest, str) or len(digest) != 64:
            raise ProbeError("relay_extract", "classification requires a sanitized post-run relay extract")
    request = extract.get("request")
    response = extract.get("response")
    if request is None and response is None:
        return None
    if not isinstance(request, Mapping) or not isinstance(response, Mapping):
        raise ProbeError("relay_extract", "classification requires a sanitized post-run relay extract")
    return RelayExchange(request=dict(request), response=dict(response))


def classify_live_zed_observation(
    exchange: RelayExchange | None,
    isolation: IsolationEvidence,
    invocation: ZedInvocation,
    *,
    already_running_zed: bool,
    relay_failed: bool,
    cleanup_roots_empty: bool,
) -> Finding:
    """Fail closed to INDETERMINATE when hermetic/relay/cleanup gates do not pass."""
    try:
        validate_zed_invocation(invocation, hermetic_root=Path(isolation.hermetic_zed_root))
    except ProbeError:
        return Finding.INDETERMINATE
    if already_running_zed or relay_failed or not cleanup_roots_empty:
        return Finding.INDETERMINATE
    return classify_real_zed_result(exchange, isolation)


def zed_target_already_running(process_names: Sequence[str]) -> bool:
    """True when a Zed process name is already present; callers supply the process list."""
    names = {name.casefold() for name in process_names}
    return "zed.exe" in names or "zed" in names


def build_opaque_relay_command(
    *,
    capture_root: Path,
    run_id: str,
    child_executable: Path,
    invocation: ZedInvocation,
    child_args: Sequence[str] | None = None,
) -> list[str]:
    """Build the Plan 11.7 opaque relay argv; byte interpretation stays out of the relay process."""
    if invocation.user_data_root is None:
        raise ProbeError("zed_invocation", "current-version hermetic invocation descriptor is missing")
    validate_zed_invocation(invocation, hermetic_root=Path(invocation.user_data_root))
    after = [str(item) for item in (child_args if child_args is not None else (child_executable,))]
    return [
        sys.executable,
        str(_RELAY_SCRIPT),
        "--capture-root",
        str(capture_root),
        "--run-id",
        run_id,
        "--child-executable",
        str(child_executable),
        "--",
        *after,
    ]


def validate_acpx_baseline(evidence: AcpxBaselineEvidence) -> None:
    """Require the isolated initialize payload to advertise loadSession; forbid origin-A."""
    if evidence.origin_a_launches != 0:
        raise ProbeError("acpx_baseline", "origin-A launches are forbidden")
    if dict(evidence.capability_payload).get("loadSession") is not True:
        raise ProbeError("acpx_baseline", "isolated probe must advertise loadSession")
    if ALLOWED_PROBE_SEMANTICS["request.session/load.response.result"] != {}:
        raise ProbeError("acpx_baseline", "isolated probe must answer session/load with {}")
    if evidence.session_load_exchange is not None:
        response = evidence.session_load_exchange.get("response")
        if not isinstance(response, Mapping) or response.get("result") != {}:
            raise ProbeError("acpx_baseline", "isolated probe must answer session/load with {}")


def _is_outside_normal_workspace(candidate: Path, normal_root: Path) -> bool:
    candidate = candidate.resolve()
    normal = normal_root.resolve()
    if candidate == normal:
        return False
    if candidate.is_relative_to(normal):
        return False
    if normal.is_relative_to(candidate):
        return False
    return True


def normal_workspace_source_paths(root: Path) -> tuple[str, ...]:
    """Return tracked plus untracked-non-ignored paths; gitignored secrets stay out."""
    root = root.resolve()
    try:
        completed = subprocess.run(  # noqa: S603
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError("source_digest", f"{type(exc).__name__}: {exc}") from exc
    if completed.returncode != 0:
        raise ProbeError("source_digest", f"git ls-files exit={completed.returncode}")
    return tuple(sorted(item.replace("\\", "/") for item in completed.stdout.split("\0") if item))


def normal_workspace_source_digest(root: Path, paths: Sequence[str] | None = None) -> str:
    """Hash tracked files plus untracked non-ignored files so a stray path cannot hide."""
    root = root.resolve()
    hasher = hashlib.sha256()
    for relative in paths if paths is not None else normal_workspace_source_paths(root):
        hasher.update(relative.encode("utf-8"))
        hasher.update(b"\0")
        file_path = root.joinpath(*relative.split("/"))
        if file_path.is_file():
            hasher.update(file_path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def throwaway_tree_digest(root: Path) -> str:
    """Hash every file under a non-git throwaway tree (isolated probe copies have no .git)."""
    root = root.resolve()
    if not root.is_dir():
        raise ProbeError("source_digest", "throwaway tree is missing")
    hasher = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        hasher.update(relative.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def _copy_normal_workspace_sources(normal: Path, isolated: Path, paths: Sequence[str]) -> None:
    """Copy exactly the digest file set so gitignored credentials cannot enter the probe tree."""
    isolated.mkdir(parents=True)
    for relative in paths:
        source = normal.joinpath(*relative.split("/"))
        if not source.is_file():
            continue
        destination = isolated.joinpath(*relative.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _advertises_top_level_load_session(source_root: Path) -> bool:
    spec = source_root / "src" / "optimus" / "acp" / "spec.py"
    try:
        text = spec.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProbeError("isolation_inspect", f"{type(exc).__name__}: {exc}") from exc
    return '"loadSession": True' in text


def _apply_isolated_probe_patch(spec_path: Path) -> None:
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProbeError("apply_probe_patch", f"{type(exc).__name__}: {exc}") from exc
    if _INITIALIZE_NO_LOAD_SESSION not in text or _SESSION_PROMPT_BRANCH not in text:
        raise ProbeError("apply_probe_patch", "unexpected patch surface: initialize/load markers missing")
    patched = text.replace(_INITIALIZE_NO_LOAD_SESSION, _INITIALIZE_TEMPORARY_LOAD_SESSION, 1)
    patched = patched.replace(_SESSION_PROMPT_BRANCH, _SESSION_LOAD_BRANCH, 1)
    if patched == text or '"loadSession": True' not in patched or "session/load" not in patched:
        raise ProbeError("apply_probe_patch", "unexpected patch surface: isolated patch did not apply")
    spec_path.write_text(patched, encoding="utf-8")


def _verify_cleanup_dry_run(scratch_parent: Path) -> bool:
    canary = scratch_parent / ".plan1119-cleanup-canary"
    if canary.exists():
        shutil.rmtree(canary)
    canary.mkdir(parents=True)
    (canary / "marker").write_text("dry-run", encoding="utf-8")
    shutil.rmtree(canary)
    return not canary.exists()


def prepare_real_zed_probe(
    isolated_root: Path,
    *,
    normal_root: Path,
    scratch_parent: Path,
    patch_plan: ProbePatchPlan | None = None,
) -> ProbePreparation:
    """Copy the normal tree into throwaway scratch and apply only the allowlisted probe patch."""
    plan = patch_plan or DEFAULT_PROBE_PATCH_PLAN
    validate_probe_patch_plan(plan)
    scratch = scratch_parent.resolve()
    isolated = isolated_root.resolve()
    normal = normal_root.resolve()
    if not scratch.is_dir():
        raise ProbeError("prepare_real_zed_probe", "scratch parent must be an existing directory")
    if not isolated.is_relative_to(scratch):
        raise ProbeError("prepare_real_zed_probe", "isolated source must be outside the normal workspace")
    if not _is_outside_normal_workspace(isolated, normal):
        raise ProbeError("prepare_real_zed_probe", "isolated source must be outside the normal workspace")
    if isolated.exists():
        raise ProbeError("prepare_real_zed_probe", "isolated source root already exists")
    source_paths = normal_workspace_source_paths(normal)
    before = normal_workspace_source_digest(normal, source_paths)
    _copy_normal_workspace_sources(normal, isolated, source_paths)
    spec_path = isolated.joinpath(*ALLOWED_PROBE_CHANGED_PATHS[0].split("/"))
    _apply_isolated_probe_patch(spec_path)
    build_root = scratch / "probe-build"
    hermetic_root = scratch / "zed-home"
    build_root.mkdir(parents=True, exist_ok=True)
    hermetic_root.mkdir(parents=True, exist_ok=True)
    cleanup_dry_run_verified = _verify_cleanup_dry_run(scratch)
    if not cleanup_dry_run_verified:
        raise ProbeError("prepare_real_zed_probe", "cleanup dry-run not verified")
    return ProbePreparation(
        isolated_source_root=str(isolated),
        isolated_build_root=str(build_root),
        hermetic_zed_root=str(hermetic_root),
        normal_root=str(normal),
        normal_commit=_git_head(normal),
        normal_source_sha256_before=before,
        patch_plan=plan,
        cleanup_dry_run_verified=cleanup_dry_run_verified,
    )


def verify_normal_operation_isolation(preparation: ProbePreparation) -> IsolationEvidence:
    """Record predicates 1-3 plus cleanup dry-run; observed removal stays false until later."""
    normal_root = Path(preparation.normal_root)
    isolated_root = Path(preparation.isolated_source_root)
    return IsolationEvidence(
        normal_agent_load_session_advertised=_advertises_top_level_load_session(normal_root),
        isolated_probe_load_session_advertised=_advertises_top_level_load_session(isolated_root),
        normal_source_sha256_before=preparation.normal_source_sha256_before,
        normal_source_sha256_after=normal_workspace_source_digest(normal_root),
        isolated_source_root=str(isolated_root),
        isolated_build_root=preparation.isolated_build_root,
        hermetic_zed_root=preparation.hermetic_zed_root,
        cleanup_dry_run_verified=preparation.cleanup_dry_run_verified,
        cleanup_verified=False,
    )


def evaluate_session_load_exchange(
    capability_payload: Mapping[str, Any] | None,
    load_exchange: Mapping[str, Any] | None,
) -> SessionLoadEvaluation:
    """Classify only a complete, internally consistent live capability/load exchange."""
    capabilities = dict(capability_payload) if isinstance(capability_payload, Mapping) else None
    exchange = dict(load_exchange) if isinstance(load_exchange, Mapping) else None
    if capabilities is None or exchange is None:
        return SessionLoadEvaluation(Finding.INDETERMINATE, capabilities, exchange)

    response = exchange.get("response")
    if not isinstance(response, Mapping):
        return SessionLoadEvaluation(Finding.INDETERMINATE, capabilities, exchange)

    advertised = capabilities.get("loadSession") is True
    has_result = "result" in response
    has_error = isinstance(response.get("error"), Mapping)
    if advertised and has_result:
        return SessionLoadEvaluation(Finding.REACHABLE, capabilities, exchange)
    if has_error:
        return SessionLoadEvaluation(Finding.UNREACHABLE, capabilities, exchange)
    return SessionLoadEvaluation(Finding.INDETERMINATE, capabilities, exchange)


def _run(command: Sequence[str], *, cwd: Path, env: Mapping[str, str]) -> CommandResult:
    completed = subprocess.run(  # noqa: S603
        list(command),
        cwd=cwd,
        env=dict(env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        shell=False,
        timeout=90,
    )
    return CommandResult(
        command=list(command),
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def _run_required(command: Sequence[str], *, cwd: Path, env: Mapping[str, str], stage: str) -> CommandResult:
    try:
        result = _run(command, cwd=cwd, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError(stage, f"{type(exc).__name__}: {exc}") from exc
    if result.returncode != 0:
        raise ProbeError(stage, f"exit={result.returncode}: captured command evidence", result)
    return result


def _resolve_acpx() -> Path:
    on_path = shutil.which("acpx")
    if on_path:
        return Path(on_path).resolve()
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        npm_shim = Path(appdata) / "npm" / "acpx.cmd"
        if npm_shim.is_file():
            return npm_shim.resolve()
    raise ProbeError("resolve_acpx", "independent acpx binary is not available on PATH or in APPDATA\\npm")


def _resolve_optimus_agent(repo_root: Path) -> Path:
    on_path = shutil.which("optimus-agent")
    if on_path:
        return Path(on_path).resolve()
    candidate = repo_root / ".venv" / "Scripts" / "optimus-agent.exe"
    if candidate.is_file():
        return candidate.resolve()
    raise ProbeError("resolve_optimus_agent", "optimus-agent is not available on PATH or in the repository virtualenv")


def _observe_zed_version() -> str:
    zed = shutil.which("zed")
    if zed is None:
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        candidate = Path(local_app_data) / "Programs" / "Zed" / "bin" / "Zed.exe"
        if candidate.is_file():
            zed = str(candidate)
    if zed is None:
        raise ProbeError("observe_zed_version", "Zed executable not found")
    try:
        completed = subprocess.run(  # noqa: S603
            [zed, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError("observe_zed_version", f"{type(exc).__name__}: {exc}") from exc
    version = (completed.stdout or completed.stderr).strip()
    if completed.returncode != 0 or not version:
        raise ProbeError("observe_zed_version", f"Zed --version exit={completed.returncode}")
    return version


def _acpx_version(acpx: Path, *, cwd: Path, env: Mapping[str, str]) -> str:
    result = _run_required([str(acpx), "--version"], cwd=cwd, env=env, stage="acpx_version")
    version = (result.stdout or result.stderr).strip()
    if not version:
        raise ProbeError("acpx_version", "acpx --version returned empty output")
    return version


def _file_sha256(path: Path) -> str:
    """Return the provenance digest for the exact acpx launcher invoked."""
    try:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as exc:
        raise ProbeError("acpx_provenance", f"{type(exc).__name__}: {exc}") from exc


def _isolated_environment(home: Path) -> dict[str, str]:
    passthrough = {
        "COMSPEC",
        "PATH",
        "PATHEXT",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "WINDIR",
    }
    environment = {key: value for key, value in os.environ.items() if key in passthrough}
    app_data = home / "AppData" / "Roaming"
    local_app_data = home / "AppData" / "Local"
    temp_root = home / "Temp"
    for directory in (app_data, local_app_data, temp_root):
        directory.mkdir(parents=True, exist_ok=True)
    environment.update(
        {
            "APPDATA": str(app_data),
            "HOME": str(home),
            "LOCALAPPDATA": str(local_app_data),
            "TEMP": str(temp_root),
            "TMP": str(temp_root),
            "USERPROFILE": str(home),
        }
    )
    return environment


def build_acpx_command(
    acpx: Path,
    *,
    workspace: Path,
    agent: Path,
    ttl_seconds: int = 60,
) -> list[str]:
    """Build a raw acpx agent command with slash-normalized Windows paths.

    Do not ``Path.resolve()`` the agent/workspace here: on POSIX, resolving a
    Windows drive-letter path prepends the current working directory and breaks
    the slash-normalized argv contract that acpx needs on Windows.
    """
    agent_argv = [
        PureWindowsPath(agent).as_posix(),
        "--workspace-root",
        PureWindowsPath(workspace).as_posix(),
        "--no-auto-start",
    ]
    # Windows CreateProcess cannot spawn a .py file directly (acpx reports "spawn EFTYPE").
    if Path(agent).suffix.casefold() == ".py":
        agent_argv.insert(0, PureWindowsPath(sys.executable).as_posix())
    return [
        str(acpx),
        "--format",
        "json",
        "--json-strict",
        "--no-terminal",
        "--auth-policy",
        "skip",
        "--deny-all",
        "--allowed-tools",
        "",
        "--timeout",
        "60",
        "--ttl",
        str(ttl_seconds),
        "--cwd",
        str(workspace),
        "--agent",
        subprocess.list2cmdline(agent_argv),
    ]


def _resolve_trust_cli(repo_root: Path) -> Path:
    candidate = repo_root / ".venv" / "Scripts" / "optimus-trust.exe"
    if candidate.is_file():
        return candidate.resolve()
    on_path = shutil.which("optimus-trust")
    if on_path:
        return Path(on_path).resolve()
    raise ProbeError("resolve_optimus_trust", "optimus-trust is not available in the repository virtualenv or on PATH")


def build_trust_command(trust_cli: Path, workspace: Path, action: str) -> list[str]:
    """Build the exact trust-CLI command for temporary approval or cleanup."""
    prefix = [str(trust_cli), "--workspace-root", str(workspace)]
    if action == "approve":
        return [*prefix, "approve", "--mode", "durable"]
    if action == "revoke":
        return [*prefix, "revoke"]
    if action == "inspect":
        return [*prefix, "inspect"]
    raise ValueError(f"unsupported trust action: {action}")


def build_cleanup_remediation(trust_cli: Path, workspace: Path) -> list[str]:
    """Return the exact workspace-scoped command needed after a failed cleanup."""
    return [str(trust_cli), "--workspace-root", str(workspace), "revoke"]


def _run_interactive_required(command: Sequence[str], *, cwd: Path, stage: str) -> CommandResult:
    """Run a trust ceremony only from an interactive terminal; never synthesize consent."""
    creationflags = 0
    if os.name == "nt" and (not sys.stdin.isatty() or not sys.stdout.isatty()):
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    elif not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ProbeError(stage, "interactive TTY required for Optimus launch-approval ceremony")
    try:
        completed = subprocess.run(  # noqa: S603
            list(command),
            cwd=cwd,
            check=False,
            shell=False,
            creationflags=creationflags,
        )
    except OSError as exc:
        raise ProbeError(stage, f"{type(exc).__name__}: {exc}") from exc
    if completed.returncode != 0:
        raise ProbeError(stage, f"exit={completed.returncode}")
    return CommandResult(command=list(command), returncode=completed.returncode, stdout="", stderr="")


def _parse_ndjson(raw: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in raw.splitlines():
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            records.append(decoded)
    return records


def _extract_session_load_evidence(records: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    capabilities: dict[str, Any] | None = None
    requests: dict[Any, dict[str, Any]] = {}
    exchanges: list[dict[str, Any]] = []
    for record in records:
        result = record.get("result")
        if isinstance(result, Mapping):
            candidate = result.get("agentCapabilities")
            if capabilities is None and isinstance(candidate, Mapping):
                capabilities = dict(candidate)
        if record.get("method") == "session/load":
            requests[record.get("id")] = dict(record)
            continue
        request = requests.get(record.get("id"))
        if request is not None and ("result" in record or "error" in record):
            exchanges.append({"request": request, "response": dict(record)})
    return capabilities, exchanges[0] if exchanges else None


def _safe_payload(value: Any) -> Any:
    """Apply the repository's evidence sanitizer to every persisted stream or payload."""
    return sanitize_for_persistence(value, policy=EVIDENCE_REDACTION_POLICY).value


def capture_acpx_evidence(command_result: CommandResult) -> dict[str, Any]:
    """Retain safe structured ACP evidence from a successful *or failed* acpx stage."""
    records = _parse_ndjson(command_result.stdout)
    capability_payload, load_exchange = _extract_session_load_evidence(records)
    non_protocol_lines = sum(1 for line in command_result.stdout.splitlines() if line.strip()) - len(records)
    return {
        "command": _safe_payload(command_result.command),
        "exit_code": command_result.returncode,
        "stdout_records": _safe_payload(records),
        "stdout_unparsed_line_count": non_protocol_lines,
        "stderr": _safe_payload(command_result.stderr.strip()) or None,
        "capability_payload": _safe_payload(capability_payload),
        "session_load_exchange": _safe_payload(load_exchange),
    }


def record_probe_command_failure(result: dict[str, Any], exc: ProbeError) -> None:
    """Persist sanitized stage/message plus captured acpx streams when a command failed."""
    result["failure"] = {"stage": exc.stage, "message": _safe_payload(str(exc))}
    if exc.command_result is None:
        return
    failure_evidence = capture_acpx_evidence(exc.command_result)
    result["acpx_failure"] = failure_evidence
    result["capability_payload"] = failure_evidence["capability_payload"]
    result["session_load_exchange"] = failure_evidence["session_load_exchange"]


def extract_acpx_archive_capability_payload(archive: Path) -> dict[str, Any] | None:
    """Read the live initialize capabilities persisted by acpx's own session export."""
    try:
        archive_payload = json.loads(archive.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeError("acpx_export_archive", f"{type(exc).__name__}: {exc}") from exc
    if not isinstance(archive_payload, Mapping):
        return None
    session = archive_payload.get("session")
    if not isinstance(session, Mapping):
        return None
    state = session.get("state")
    if not isinstance(state, Mapping):
        return None
    capabilities = state.get("agent_capabilities")
    return dict(capabilities) if isinstance(capabilities, Mapping) else None


def classify_indeterminate_context(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Separate a missing documented dependency from an incomplete ACP observation."""
    evidence_text = json.dumps(evidence, sort_keys=True).casefold()
    redis_unreachable = "redis" in evidence_text and (
        "not reachable" in evidence_text or "timeout connecting" in evidence_text
    )
    if redis_unreachable:
        return {
            "indeterminate_reason": IndeterminateReason.PRECONDITION_UNMET.value,
            "precondition": {
                "name": "redis",
                "remediation": {
                    "runbook": "docs/runbooks/local-live-dependencies.md#5-bounded-session-bound-smoke-redis--gateway-optional-phoenix",
                    "command": "optimus-agent --workspace-root <throwaway-workspace> --check-config --strict",
                },
            },
        }
    capability_payload = evidence.get("capability_payload")
    if isinstance(capability_payload, Mapping) and capability_payload.get("loadSession") is not True:
        return {
            "indeterminate_reason": IndeterminateReason.INTERNAL_CAPABILITY_UNAVAILABLE.value,
            "precondition": None,
        }
    return {
        "indeterminate_reason": IndeterminateReason.OBSERVATION_INCOMPLETE.value,
        "precondition": None,
    }


def _revoke_temporary_approval(trust_cli: Path, workspace: Path, *, cwd: Path) -> None:
    """Revoke and verify the temporary durable record, retrying bounded transient failures."""
    last_error: ProbeError | None = None
    for _attempt in range(1, 4):
        try:
            _run_interactive_required(
                build_trust_command(trust_cli, workspace, "revoke"),
                cwd=cwd,
                stage="temporary_approval_revoke",
            )
            try:
                inspected = _run(build_trust_command(trust_cli, workspace, "inspect"), cwd=cwd, env=os.environ)
            except (OSError, subprocess.TimeoutExpired) as exc:
                last_error = ProbeError("temporary_approval_verify", f"{type(exc).__name__}: {exc}")
                continue
            if inspected.returncode == 1:
                return
            last_error = ProbeError("temporary_approval_verify", f"inspect exit={inspected.returncode}")
        except ProbeError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _git_head(repo_root: Path) -> str | None:
    try:
        completed = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def _validate_parent_workspace(parent_workspace: Path, repo_root: Path) -> Path:
    resolved = parent_workspace.resolve()
    if not resolved.is_dir():
        raise ProbeError("workspace", "workspace path must be an existing directory")
    if resolved == repo_root or (resolved / ".git").exists():
        raise ProbeError("workspace", "workspace path must be a throwaway directory, never a repository")
    return resolved


def run_probe(parent_workspace: Path) -> dict[str, Any]:
    """Run the non-prompt acpx recovery sequence and return a self-contained finding."""
    repo_root = Path(__file__).resolve().parents[1]
    recorded_at = datetime.now(UTC).isoformat()
    result: dict[str, Any] = {
        "schema": "p11-feat-zed-resume-session-load-reprobe-v1",
        "recorded_at_utc": recorded_at,
        "commit": _git_head(repo_root),
        "finding": Finding.INDETERMINATE.value,
        "indeterminate_reason": IndeterminateReason.OBSERVATION_INCOMPLETE.value,
        "precondition": None,
        "zed_version": None,
        "acpx_version": None,
        "acpx_executable": None,
        "acpx_launcher_sha256": None,
        "capability_payload": None,
        "session_load_exchange": None,
        "command": "uv run --frozen python tools/probe_p11_zed_session_load.py <throwaway-workspace>",
        "origin_a_launches": 0,
        "zed_launches": 0,
        "temporary_launch_approval_revoked": None,
        "cleanup_remediation": None,
        "non_claims": [
            "Does not prove that Zed itself emits session/load after a restart.",
            "Does not establish origin-A correlation, server-side custody feasibility, or authorization for an amendment.",
        ],
    }
    run_root: Path | None = None
    trust_cli: Path | None = None
    temporary_approval_created = False
    cleanup_succeeded = True
    try:
        workspace_parent = _validate_parent_workspace(parent_workspace, repo_root)
        result["zed_version"] = _observe_zed_version()
        run_root = Path(tempfile.mkdtemp(prefix="p11-zed-session-load-", dir=workspace_parent))
        workspace = run_root / "workspace"
        first_home = run_root / "acpx-home-first"
        second_home = run_root / "acpx-home-second"
        workspace.mkdir()
        acpx = _resolve_acpx()
        result["acpx_executable"] = str(acpx)
        result["acpx_launcher_sha256"] = _file_sha256(acpx)
        agent = _resolve_optimus_agent(repo_root)
        trust_cli = _resolve_trust_cli(repo_root)
        first_environment = _isolated_environment(first_home)
        second_environment = _isolated_environment(second_home)
        result["acpx_version"] = _acpx_version(acpx, cwd=workspace, env=first_environment)
        command = build_acpx_command(acpx, workspace=workspace, agent=agent, ttl_seconds=1)
        try:
            trust_preflight = _run(build_trust_command(trust_cli, workspace, "inspect"), cwd=workspace, env=os.environ)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProbeError("temporary_approval_preflight", f"{type(exc).__name__}: {exc}") from exc
        if trust_preflight.returncode != 1:
            raise ProbeError("temporary_approval_preflight", f"inspect exit={trust_preflight.returncode}", trust_preflight)
        approval_command = build_trust_command(trust_cli, workspace, "approve")
        result["temporary_approval_command"] = approval_command
        _run_interactive_required(approval_command, cwd=workspace, stage="temporary_approval")
        temporary_approval_created = True
        _run_required([*command, "sessions", "new"], cwd=workspace, env=first_environment, stage="acpx_new_session")
        archive = run_root / "session.json"
        _run_required(
            [*command, "sessions", "export", "--output", str(archive)],
            cwd=workspace,
            env=first_environment,
            stage="acpx_export_session",
        )
        initial_capability_payload = extract_acpx_archive_capability_payload(archive)
        _run_required(
            [*command, "sessions", "import", str(archive)],
            cwd=workspace,
            env=second_environment,
            stage="acpx_import_session",
        )
        try:
            load_attempt = _run([*command, "set-mode", "p11-session-load-reprobe"], cwd=workspace, env=second_environment)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProbeError("acpx_recovery", f"{type(exc).__name__}: {exc}") from exc
        recovery_evidence = capture_acpx_evidence(load_attempt)
        capability_payload = initial_capability_payload
        load_exchange = recovery_evidence["session_load_exchange"]
        evaluated = evaluate_session_load_exchange(capability_payload, load_exchange)
        result.update(
            {
                "finding": evaluated.finding.value,
                "capability_payload": evaluated.capability_payload,
                "session_load_exchange": evaluated.load_exchange,
                "acpx_initialization": {
                    "evidence_source": "acpx session export",
                    "capability_payload": _safe_payload(initial_capability_payload),
                },
                "acpx_recovery": recovery_evidence,
            }
        )
        if evaluated.finding is Finding.INDETERMINATE:
            result.update(
                classify_indeterminate_context(
                    {**recovery_evidence, "capability_payload": capability_payload}
                )
            )
        else:
            result["indeterminate_reason"] = None
    except ProbeError as exc:
        record_probe_command_failure(result, exc)
        if exc.command_result is not None:
            result.update(classify_indeterminate_context(result["acpx_failure"]))
    finally:
        if temporary_approval_created and run_root is not None and trust_cli is not None:
            workspace = run_root / "workspace"
            try:
                result["temporary_revoke_command"] = build_trust_command(trust_cli, workspace, "revoke")
                _revoke_temporary_approval(trust_cli, workspace, cwd=workspace)
                result["temporary_launch_approval_revoked"] = True
            except ProbeError as exc:
                cleanup_succeeded = False
                result["temporary_launch_approval_revoked"] = False
                result["cleanup_failure"] = {"stage": exc.stage, "message": _safe_payload(str(exc))}
                result["cleanup_remediation"] = build_cleanup_remediation(trust_cli, workspace)
                result["finding"] = Finding.INDETERMINATE.value
        if run_root is not None and run_root.exists() and cleanup_succeeded:
            try:
                shutil.rmtree(run_root)
            except OSError as exc:
                cleanup_succeeded = False
                result["cleanup_failure"] = {
                    "stage": "throwaway_workspace_remove",
                    "message": _safe_payload(f"{type(exc).__name__}: {exc}"),
                }
                result["cleanup_remediation"] = ["remove-throwaway-workspace", str(run_root)]
                result["finding"] = Finding.INDETERMINATE.value
        result["throwaway_workspace_removed"] = run_root is not None and not run_root.exists()
    return result


def _list_process_names() -> tuple[str, ...]:
    try:
        completed = subprocess.run(  # noqa: S603
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    names: list[str] = []
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith('"'):
            names.append(stripped.split('","', 1)[0].strip('"'))
        elif stripped:
            names.append(stripped.split(",", 1)[0].strip('"'))
    return tuple(names)


def _resolve_zed_executable() -> Path:
    zed = shutil.which("zed")
    if zed is None:
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        for candidate in (
            Path(local_app_data) / "Programs" / "Zed" / "bin" / "Zed.exe",
            Path(local_app_data) / "Programs" / "Zed" / "Zed.exe",
        ):
            if candidate.is_file():
                return candidate.resolve()
        raise ProbeError("observe_zed_version", "Zed executable not found")
    return Path(zed).resolve()


def _observe_zed_help(executable: Path) -> str:
    try:
        completed = subprocess.run(  # noqa: S603
            [str(executable), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError("zed_discovery", f"{type(exc).__name__}: {exc}") from exc
    help_output = (completed.stdout or completed.stderr).strip()
    if not help_output:
        raise ProbeError("zed_discovery", "current-version hermetic invocation flag was not discovered")
    return help_output


def write_isolated_agent_launcher(build_root: Path, isolated_source: Path) -> Path:
    """Write a throwaway launcher that prefers the isolated src tree over the normal checkout."""
    build_root.mkdir(parents=True, exist_ok=True)
    launcher = build_root / _ISOLATED_LAUNCHER_NAME
    source = isolated_source.resolve().as_posix()
    launcher.write_text(
        "from __future__ import annotations\n\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        f"_SOURCE = Path({source!r})\n"
        'sys.path.insert(0, str(_SOURCE / "src"))\n'
        "from optimus.acp.__main__ import main\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n",
        encoding="utf-8",
        newline="\n",
    )
    return launcher


def seed_hermetic_zed_settings(
    appdata_root: Path,
    *,
    relay_command: str,
    relay_args: Sequence[str],
) -> Path:
    """Write hermetic ``%APPDATA%\\Zed\\settings.json`` for opaque-relay agent_servers.

    On Windows, ``--user-data-dir`` redirects ``%LOCALAPPDATA%\\Zed`` (DB/logs/extensions) only.
    Settings remain under ``%APPDATA%\\Zed\\settings.json``. Bind ``APPDATA`` to ``appdata_root``
    via ``hermetic_appdata_environment_bind`` — never rewrite ``USERPROFILE``/``HOME``.
    """
    appdata = appdata_root.resolve()
    settings_path = appdata / "Zed" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "agent_servers": {
            "optimus": {
                "command": relay_command,
                "args": list(relay_args),
            }
        }
    }
    settings_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    return settings_path


def hermetic_appdata_environment_bind(appdata_root: Path) -> tuple[tuple[str, str], ...]:
    """Bind only APPDATA for hermetic settings; leave USERPROFILE/HOME/LOCALAPPDATA alone."""
    return (("APPDATA", str(appdata_root.resolve())),)


def iter_acp_messages(payload: bytes) -> list[dict[str, Any]]:
    """Parse captured ACP bytes after process exit. Never used in the relay process."""
    framed: list[dict[str, Any]] = []
    data = payload
    while True:
        header_end = data.find(b"\r\n\r\n")
        if header_end == -1:
            break
        try:
            length = parse_content_length(data[:header_end])
        except FramingError:
            break
        start = header_end + 4
        body = data[start : start + length]
        if len(body) < length:
            break
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            break
        if isinstance(decoded, dict):
            framed.append(decoded)
        data = data[start + length :]
    if framed:
        return framed
    messages: list[dict[str, Any]] = []
    for line in payload.splitlines():
        try:
            decoded = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(decoded, dict):
            messages.append(decoded)
    return messages


def extract_session_load_from_messages(
    zed_to_agent: Sequence[Mapping[str, Any]],
    agent_to_zed: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    requests = {
        message.get("id"): dict(message)
        for message in zed_to_agent
        if message.get("method") == "session/load" and "id" in message
    }
    for message in agent_to_zed:
        request = requests.get(message.get("id"))
        if request is not None and ("result" in message or "error" in message):
            return {"request": request, "response": dict(message)}
    return None


def reconstruct_sanitized_relay_bytes(messages: Sequence[Mapping[str, Any]]) -> bytes:
    chunks: list[bytes] = []
    for message in messages:
        sanitized = _safe_payload(dict(message))
        if not isinstance(sanitized, dict):
            continue
        body = json.dumps(sanitized, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        chunks.append(body + b"\n")
    return b"".join(chunks)


def _reason_from_stage(stage: str) -> IndeterminateReason:
    mapping = {
        "already_running_zed": IndeterminateReason.ALREADY_RUNNING_ZED,
        "zed_discovery": IndeterminateReason.HERMETIC_INVOCATION_UNAVAILABLE,
        "zed_invocation": IndeterminateReason.HERMETIC_INVOCATION_UNAVAILABLE,
        "zed_launch": IndeterminateReason.OBSERVATION_INCOMPLETE,
        "zed_settings": IndeterminateReason.PRECONDITION_UNMET,
        "isolation": IndeterminateReason.ISOLATION_PREDICATE_FAILED,
        "validate_isolation_evidence": IndeterminateReason.ISOLATION_PREDICATE_FAILED,
        "relay": IndeterminateReason.RELAY_FAILURE,
        "relay_extract": IndeterminateReason.RELAY_FAILURE,
        "cleanup": IndeterminateReason.CLEANUP_UNVERIFIED,
        "throwaway_workspace_remove": IndeterminateReason.CLEANUP_UNVERIFIED,
        "real_zed": IndeterminateReason.LIVE_LAUNCH_UNAUTHORIZED,
    }
    return mapping.get(stage, IndeterminateReason.PRECONDITION_UNMET)


def _plan1119_base_result(repo_root: Path, *, mode: str) -> dict[str, Any]:
    return {
        "schema": PLAN1119_SCHEMA,
        "mode": mode,
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "commit": _git_head(repo_root),
        "finding": Finding.INDETERMINATE.value,
        "indeterminate_reason": IndeterminateReason.OBSERVATION_INCOMPLETE.value,
        "origin_a_launches": 0,
        "zed_launches": 0,
        "preflight_ok": False,
        "non_claims": [
            "Does not re-diagnose Zed 1.13.1.",
            "Does not establish origin-A correlation or authorize a budget-expansion amendment.",
        ],
    }


def _discover_live_zed_invocation(hermetic_root: Path) -> tuple[Path, ZedInvocation, str]:
    executable = _resolve_zed_executable()
    version = _observe_zed_version()
    help_output = _observe_zed_help(executable)
    invocation = discover_hermetic_zed_invocation(
        executable=executable,
        version_output=version,
        help_output=help_output,
        executable_sha256=_file_sha256(executable),
        hermetic_root=hermetic_root,
    )
    validate_zed_invocation(invocation, hermetic_root=hermetic_root)
    return executable, invocation, hashlib.sha256(help_output.encode("utf-8")).hexdigest()


def _run_acpx_against_isolated_agent(
    *,
    agent_launcher: Path,
    run_root: Path,
    repo_root: Path,
) -> AcpxBaselineEvidence:
    workspace = run_root / "acpx-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    first_home = run_root / "acpx-home-first"
    second_home = run_root / "acpx-home-second"
    acpx = _resolve_acpx()
    trust_cli = _resolve_trust_cli(repo_root)
    first_environment = _isolated_environment(first_home)
    second_environment = _isolated_environment(second_home)
    version = _acpx_version(acpx, cwd=workspace, env=first_environment)
    # ttl=1 forces a cold agent restart between steps so imported sessions rebind via session/load.
    command = build_acpx_command(acpx, workspace=workspace, agent=agent_launcher, ttl_seconds=1)
    try:
        trust_preflight = _run(build_trust_command(trust_cli, workspace, "inspect"), cwd=workspace, env=os.environ)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError("temporary_approval_preflight", f"{type(exc).__name__}: {exc}") from exc
    if trust_preflight.returncode != 1:
        raise ProbeError("temporary_approval_preflight", f"inspect exit={trust_preflight.returncode}", trust_preflight)
    _run_interactive_required(build_trust_command(trust_cli, workspace, "approve"), cwd=workspace, stage="temporary_approval")
    try:
        _run_required([*command, "sessions", "new"], cwd=workspace, env=first_environment, stage="acpx_new_session")
        archive = run_root / "session.json"
        _run_required(
            [*command, "sessions", "export", "--output", str(archive)],
            cwd=workspace,
            env=first_environment,
            stage="acpx_export_session",
        )
        capability_payload = extract_acpx_archive_capability_payload(archive) or {}
        _run_required(
            [*command, "sessions", "import", str(archive)],
            cwd=workspace,
            env=second_environment,
            stage="acpx_import_session",
        )
        # Do not use set-mode: Optimus does not implement session/set_mode (-32601).
        # Wait for ttl=1 shutdown, then status forces a cold session bind.
        time.sleep(2)
        reconnect = _run([*command, "status"], cwd=workspace, env=second_environment)
        recovery = capture_acpx_evidence(reconnect)
        exchange = recovery.get("session_load_exchange")
        evidence = AcpxBaselineEvidence(
            acpx_version=version,
            acpx_executable=str(acpx),
            acpx_sha256=_file_sha256(acpx),
            capability_payload=dict(capability_payload),
            origin_a_launches=0,
            session_load_exchange=dict(exchange) if isinstance(exchange, Mapping) else None,
        )
        try:
            validate_acpx_baseline(evidence)
        except ProbeError as exc:
            raise ProbeError(exc.stage, str(exc), reconnect) from exc
        return evidence
    finally:
        try:
            _revoke_temporary_approval(trust_cli, workspace, cwd=workspace)
        except ProbeError:
            pass


def _remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=False)


def _cleanup_plan1119_roots(
    *,
    run_root: Path | None,
    isolated_source: Path | None,
    isolated_build: Path | None,
    hermetic_root: Path | None,
) -> tuple[bool, list[str]]:
    leftovers: list[str] = []
    for candidate in (isolated_source, isolated_build, hermetic_root, run_root):
        if candidate is None:
            continue
        try:
            _remove_tree(candidate)
        except OSError as exc:
            leftovers.append(f"{candidate}: {type(exc).__name__}")
            continue
        if candidate.exists():
            leftovers.append(str(candidate))
    return (not leftovers, leftovers)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_zed_launch_timeout_seconds(value: float) -> float:
    """Accept only a finite launch window in ``[60.0, 900.0]`` seconds."""
    if not math.isfinite(value) or value < MIN_ZED_LAUNCH_TIMEOUT_SECONDS or value > MAX_ZED_LAUNCH_TIMEOUT_SECONDS:
        raise ValueError("zed launch timeout must be a finite value in [60.0, 900.0]")
    return float(value)


def _parse_zed_launch_timeout_seconds(raw: str) -> float:
    try:
        parsed = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("zed launch timeout must be a finite value in [60.0, 900.0]") from exc
    try:
        return validate_zed_launch_timeout_seconds(parsed)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _assert_allowed_report_dir(report_dir: Path) -> Path:
    resolved = report_dir.expanduser().resolve()
    root = REPORTS_ROOT.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ProbeError("evidence_bundle", "report directory must be inside reports/")
    if resolved.exists():
        raise ProbeError("evidence_bundle", "existing report directory must not be overwritten")
    return resolved


def _assert_cleanup_allows_publish(result: Mapping[str, Any]) -> None:
    isolation = result.get("isolation")
    if not isinstance(isolation, Mapping) or isolation.get("cleanup_verified") is not True:
        raise ProbeError("cleanup", "sanitized evidence is not published after failed cleanup")


def _plan1124_report_text(result: Mapping[str, Any]) -> str:
    finding = str(result.get("finding") or Finding.INDETERMINATE.value)
    recorded = str(result.get("recorded_at_utc") or "")
    commit = str(result.get("commit") or "")
    reason = result.get("indeterminate_reason")
    lines = [
        "# Plan 11.24 operator-guided Zed `session/load` probe",
        "",
        "## Finding",
        "",
    ]
    if finding == Finding.INDETERMINATE.value and isinstance(reason, str) and reason:
        lines.append(f"**{finding} / {reason}** as of `{recorded}` at commit `{commit}`.")
        if reason == IndeterminateReason.INTERNAL_CAPABILITY_UNAVAILABLE.value:
            lines.extend(["", "This is not a finding about Zed."])
    else:
        lines.append(f"**{finding}** as of `{recorded}` at commit `{commit}`.")
    lines.extend(
        [
            "",
            "The previous Plan 11.19 bundle remains unchanged.",
            "",
        ]
    )
    return "\n".join(lines)


def _manifest_from_sanitized_result(
    result: Mapping[str, Any],
    *,
    zed_to_agent: bytes,
    agent_to_zed: bytes,
    files: Mapping[str, str],
) -> dict[str, Any]:
    manifest = {key: value for key, value in result.items() if not str(key).startswith("_")}
    relay = dict(manifest["relay"]) if isinstance(manifest.get("relay"), Mapping) else {}
    relay["source"] = RELAY_EXTRACT_SOURCE
    relay["zed_to_agent_sha256"] = _sha256_bytes(zed_to_agent)
    relay["agent_to_zed_sha256"] = _sha256_bytes(agent_to_zed)
    manifest["relay"] = relay
    manifest["files"] = dict(files)
    manifest["origin_a_launches"] = 0
    sanitized = _safe_payload(manifest)
    if not isinstance(sanitized, dict):
        raise ProbeError("evidence_bundle", "sanitized manifest is not an object")
    encoded = json.dumps(sanitized, default=str)
    loaded = json.loads(encoded)
    if not isinstance(loaded, dict):
        raise ProbeError("evidence_bundle", "sanitized manifest is not an object")
    return loaded


def _verify_existing_evidence_manifest(manifest_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from tools.verify_plan1119_zed_reprobe_evidence import verify_manifest

    verify_manifest(manifest_path)


def materialize_sanitized_zed_evidence(
    *,
    report_dir: Path,
    result: Mapping[str, Any],
    zed_to_agent: bytes,
    agent_to_zed: bytes,
) -> Path:
    """Atomically publish reconstructed sanitized relay bytes plus a verifier-valid bundle."""
    target = _assert_allowed_report_dir(report_dir)
    _assert_cleanup_allows_publish(result)
    zed_bytes = bytes(zed_to_agent)
    agent_bytes = bytes(agent_to_zed)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=parent))
    try:
        relay_dir = staging / "relay"
        relay_dir.mkdir()
        zed_path = relay_dir / "zed-to-agent.bin"
        agent_path = relay_dir / "agent-to-zed.bin"
        report_path = staging / "report.md"
        zed_path.write_bytes(zed_bytes)
        agent_path.write_bytes(agent_bytes)
        report_path.write_text(_plan1124_report_text(result), encoding="utf-8", newline="\n")
        files = {
            "report.md": _sha256_bytes(report_path.read_bytes()),
            "relay/zed-to-agent.bin": _sha256_bytes(zed_bytes),
            "relay/agent-to-zed.bin": _sha256_bytes(agent_bytes),
        }
        manifest = _manifest_from_sanitized_result(
            result,
            zed_to_agent=zed_bytes,
            agent_to_zed=agent_bytes,
            files=files,
        )
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        try:
            _verify_existing_evidence_manifest(manifest_path)
        except Exception as exc:
            raise ProbeError("evidence_bundle", "existing verifier rejected the sanitized bundle") from exc
        if target.exists():
            raise ProbeError("evidence_bundle", "existing report directory must not be overwritten")
        staging.replace(target)
        return target / "manifest.json"
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _zed_env_for_invocation(invocation: ZedInvocation) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(dict(invocation.environment_bind))
    return environment


def _launch_zed_once(
    argv: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path,
    log_path: Path | None = None,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        raise ProbeError("real_zed", "Zed GUI launch is forbidden inside pytest")
    stdout_target: Any = subprocess.DEVNULL
    stderr_target: Any = subprocess.DEVNULL
    log_handle = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("w", encoding="utf-8", newline="\n")
        stdout_target = log_handle
        stderr_target = log_handle
    try:
        proc = subprocess.Popen(  # noqa: S603
            list(argv),
            cwd=cwd,
            env=dict(env),
            stdout=stdout_target,
            stderr=stderr_target,
            shell=False,
        )
    except OSError as exc:
        if log_handle is not None:
            log_handle.close()
        raise ProbeError("real_zed", f"{type(exc).__name__}: {exc}") from exc
    try:
        returncode = proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        subprocess.run(  # noqa: S603
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
            shell=False,
            timeout=30,
        )
        try:
            returncode = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            returncode = proc.wait(timeout=5)
    finally:
        if log_handle is not None:
            log_handle.close()
    return {"pid": proc.pid, "returncode": returncode, "log_path": str(log_path) if log_path else None}


def _launch_log_excerpt(log_path: Path, *, limit: int = 4000) -> str:
    """Return a sanitized trailing excerpt so cleanup can still leave diagnosis in the sidecar."""
    if not log_path.is_file():
        return ""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    collapsed = " ".join(text.split())
    if len(collapsed) > limit:
        collapsed = collapsed[-limit:]
    sanitized = sanitize_for_persistence(collapsed, policy=EVIDENCE_REDACTION_POLICY).value
    return str(sanitized) if sanitized is not None else ""

def _record_identities(
    result: dict[str, Any],
    *,
    executable: Path,
    invocation: ZedInvocation,
    help_sha256: str,
    preparation: ProbePreparation,
    isolation: IsolationEvidence,
    launcher: Path,
    acpx: AcpxBaselineEvidence | None,
) -> None:
    result["zed"] = {
        "version": invocation.version,
        "executable": str(executable),
        "executable_sha256": invocation.executable_sha256,
    }
    result["invocation"] = {
        "discovered_from": invocation.discovered_from,
        "argv": list(invocation.argv),
        "user_data_root": invocation.user_data_root,
        "help_sha256": help_sha256,
        "environment_bind": [list(item) for item in invocation.environment_bind],
    }
    result["normal_source"] = {
        "commit": preparation.normal_commit,
        "sha256_before": isolation.normal_source_sha256_before,
        "sha256_after": isolation.normal_source_sha256_after,
    }
    result["isolated_source"] = {"sha256": throwaway_tree_digest(Path(preparation.isolated_source_root))}
    result["isolated_build"] = {"sha256": _file_sha256(launcher)}
    result["isolation"] = {
        "normal_agent_load_session_advertised": isolation.normal_agent_load_session_advertised,
        "isolated_probe_load_session_advertised": isolation.isolated_probe_load_session_advertised,
        "cleanup_dry_run_verified": isolation.cleanup_dry_run_verified,
        "cleanup_verified": isolation.cleanup_verified,
        "isolated_source_root": isolation.isolated_source_root,
        "isolated_build_root": isolation.isolated_build_root,
        "hermetic_zed_root": isolation.hermetic_zed_root,
    }
    if acpx is not None:
        result["acpx"] = {
            "version": acpx.acpx_version,
            "executable": acpx.acpx_executable,
            "executable_sha256": acpx.acpx_sha256,
        }
        result["capability_payload"] = _safe_payload(dict(acpx.capability_payload))
        if acpx.session_load_exchange is not None:
            result["session_load_exchange"] = _safe_payload(dict(acpx.session_load_exchange))
        result["load_response_contract"] = _safe_payload(
            dict(ALLOWED_PROBE_SEMANTICS["request.session/load.response.result"])
        )


def run_plan1119_preflight(parent_workspace: Path) -> dict[str, Any]:
    """Discover hermetic invocation, prove isolation, and confirm isolated acpx baseline. Never launch Zed."""
    repo_root = Path(__file__).resolve().parents[1]
    result = _plan1119_base_result(repo_root, mode="preflight")
    run_root: Path | None = None
    preparation: ProbePreparation | None = None
    try:
        workspace_parent = _validate_parent_workspace(parent_workspace, repo_root)
        if zed_target_already_running(_list_process_names()):
            raise ProbeError("already_running_zed", "an already-running Zed process is in scope")
        run_root = Path(tempfile.mkdtemp(prefix="p1119-preflight-", dir=workspace_parent))
        isolated = run_root / "probe-source"
        preparation = prepare_real_zed_probe(isolated, normal_root=repo_root, scratch_parent=run_root)
        isolation = verify_normal_operation_isolation(preparation)
        if not isolation.prelaunch_predicates_pass:
            raise ProbeError("isolation", "pre-launch isolation predicates failed")
        validate_isolation_evidence(isolation, require_cleanup=False)
        executable, invocation, help_sha256 = _discover_live_zed_invocation(Path(preparation.hermetic_zed_root))
        launcher = write_isolated_agent_launcher(Path(preparation.isolated_build_root), Path(preparation.isolated_source_root))
        acpx = _run_acpx_against_isolated_agent(agent_launcher=launcher, run_root=run_root, repo_root=repo_root)
        _record_identities(
            result,
            executable=executable,
            invocation=invocation,
            help_sha256=help_sha256,
            preparation=preparation,
            isolation=isolation,
            launcher=launcher,
            acpx=acpx,
        )
        result["approved_real_zed_command"] = [
            "uv",
            "run",
            "--frozen",
            "python",
            "tools/probe_p11_zed_session_load.py",
            "--mode",
            "real-zed",
            str(workspace_parent),
        ]
        result["preflight_ok"] = True
        result["indeterminate_reason"] = None
    except ProbeError as exc:
        record_probe_command_failure(result, exc)
        result["indeterminate_reason"] = _reason_from_stage(exc.stage).value
        if exc.stage == "acpx_baseline" and "loadSession" in str(exc):
            result["indeterminate_reason"] = IndeterminateReason.INTERNAL_CAPABILITY_UNAVAILABLE.value
    finally:
        cleaned, leftovers = _cleanup_plan1119_roots(
            run_root=run_root,
            isolated_source=Path(preparation.isolated_source_root) if preparation else None,
            isolated_build=Path(preparation.isolated_build_root) if preparation else None,
            hermetic_root=Path(preparation.hermetic_zed_root) if preparation else None,
        )
        result.setdefault("isolation", {})
        if isinstance(result["isolation"], dict):
            result["isolation"]["cleanup_verified"] = cleaned
            result["isolation"]["cleanup_dry_run_verified"] = (
                preparation.cleanup_dry_run_verified if preparation else False
            )
        if not cleaned:
            result["finding"] = Finding.INDETERMINATE.value
            result["indeterminate_reason"] = IndeterminateReason.CLEANUP_UNVERIFIED.value
            result["cleanup_remediation"] = leftovers
            result["preflight_ok"] = False
        result["zed_launches"] = 0
        try:
            sidecar = parent_workspace / "plan1119-preflight-result.json"
            sidecar.write_text(
                json.dumps({k: v for k, v in result.items() if not str(k).startswith("_")}, indent=2, sort_keys=True, default=str),
                encoding="utf-8",
                newline="\n",
            )
            result["sidecar"] = str(sidecar)
        except (OSError, TypeError, ValueError):
            pass
    return result


def run_plan1119_acpx_baseline(parent_workspace: Path) -> dict[str, Any]:
    """Independent acpx confirmation of the isolated advertisement. Not a Zed finding."""
    result = run_plan1119_preflight(parent_workspace)
    result["mode"] = "acpx-baseline"
    result["zed_launches"] = 0
    if result.get("capability_payload", {}).get("loadSession") is True:
        result["finding"] = Finding.INDETERMINATE.value
        if result.get("preflight_ok"):
            result["indeterminate_reason"] = None
            result["notes"] = "acpx baseline confirmed isolated loadSession advertisement; not a Zed finding."
    return result


def run_plan1119_real_zed(
    parent_workspace: Path,
    *,
    launch_timeout_seconds: float = DEFAULT_ZED_LAUNCH_TIMEOUT_SECONDS,
    report_dir: Path,
) -> dict[str, Any]:
    """Launch the installed Zed once through the opaque relay. Caller must have recorded authorization."""
    timeout_s = validate_zed_launch_timeout_seconds(launch_timeout_seconds)
    repo_root = Path(__file__).resolve().parents[1]
    result = _plan1119_base_result(repo_root, mode="real-zed")
    run_root: Path | None = None
    preparation: ProbePreparation | None = None
    isolation: IsolationEvidence | None = None
    capture_root: Path | None = None
    zed_launched = False
    try:
        workspace_parent = _validate_parent_workspace(parent_workspace, repo_root)
        if zed_target_already_running(_list_process_names()):
            raise ProbeError("already_running_zed", "an already-running Zed process is in scope")
        run_root = Path(tempfile.mkdtemp(prefix="p1119-real-zed-", dir=workspace_parent))
        isolated = run_root / "probe-source"
        preparation = prepare_real_zed_probe(isolated, normal_root=repo_root, scratch_parent=run_root)
        isolation = verify_normal_operation_isolation(preparation)
        if not isolation.prelaunch_predicates_pass:
            raise ProbeError("isolation", "pre-launch isolation predicates failed")
        validate_isolation_evidence(isolation, require_cleanup=False)
        executable, invocation, help_sha256 = _discover_live_zed_invocation(Path(preparation.hermetic_zed_root))
        launcher = write_isolated_agent_launcher(Path(preparation.isolated_build_root), Path(preparation.isolated_source_root))
        acpx = _run_acpx_against_isolated_agent(agent_launcher=launcher, run_root=run_root, repo_root=repo_root)
        workspace = run_root / "zed-workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        capture_root = run_root / "relay-capture"
        capture_root.mkdir()
        child_args = [str(sys.executable), str(launcher), "--workspace-root", str(workspace), "--no-auto-start"]
        relay_argv = build_opaque_relay_command(
            capture_root=capture_root,
            run_id=PLAN1119_RUN_ID,
            child_executable=Path(sys.executable),
            invocation=invocation,
            child_args=child_args,
        )
        appdata_root = run_root / "zed-appdata"
        settings_path = seed_hermetic_zed_settings(
            appdata_root,
            relay_command=relay_argv[0],
            relay_args=relay_argv[1:],
        )
        if not settings_path.is_file():
            raise ProbeError("zed_settings", f"hermetic settings missing before launch: {settings_path}")
        settings_sha_before = hashlib.sha256(settings_path.read_bytes()).hexdigest()
        invocation = replace(
            invocation,
            environment_bind=hermetic_appdata_environment_bind(appdata_root),
        )
        result["hermetic_settings"] = {
            "path": str(settings_path),
            "present_before_launch": True,
            "sha256_before": settings_sha_before,
            "appdata_bind": str(appdata_root.resolve()),
        }
        launch_binary = Path(invocation.argv[0])
        launch_help = _observe_zed_help(launch_binary)
        zed_argv = list(
            build_real_zed_launch_argv(
                invocation,
                workspace=workspace,
                launch_help=launch_help,
            )
        )
        result["zed_argv"] = _safe_payload(zed_argv)
        result["launch_help_sha256"] = hashlib.sha256(launch_help.encode("utf-8")).hexdigest()
        _record_identities(
            result,
            executable=executable,
            invocation=invocation,
            help_sha256=help_sha256,
            preparation=preparation,
            isolation=isolation,
            launcher=launcher,
            acpx=acpx,
        )
        zed_launched = True
        result["zed_launches"] = 1
        log_path = run_root / "zed-launch.log"
        launch_meta = _launch_zed_once(
            zed_argv,
            env=_zed_env_for_invocation(invocation),
            cwd=workspace,
            log_path=log_path,
            timeout_s=timeout_s,
        )
        log_excerpt = _launch_log_excerpt(log_path)
        result["zed_launch"] = {
            "returncode": launch_meta.get("returncode"),
            "log_captured": bool(launch_meta.get("log_path")),
            "log_excerpt": log_excerpt,
            "timeout_seconds": timeout_s,
        }
        settings_after = settings_path.is_file()
        result["hermetic_settings"]["present_after_launch"] = settings_after
        if settings_after:
            result["hermetic_settings"]["sha256_after"] = hashlib.sha256(settings_path.read_bytes()).hexdigest()
        if int(launch_meta.get("returncode") or 0) != 0:
            detail = f"Zed exited with returncode {launch_meta.get('returncode')}"
            if log_excerpt:
                detail = f"{detail}: {log_excerpt}"
            raise ProbeError("zed_launch", detail)
        run_dir = capture_root / PLAN1119_RUN_ID
        zed_bin = run_dir / "zed-to-agent.bin"
        agent_bin = run_dir / "agent-to-zed.bin"
        if not zed_bin.is_file() or not agent_bin.is_file():
            raise ProbeError(
                "relay",
                "opaque relay capture files are missing "
                f"(hermetic_settings_present={settings_after} path={settings_path})",
            )
        zed_bytes = zed_bin.read_bytes()
        agent_bytes = agent_bin.read_bytes()
        zed_messages = iter_acp_messages(zed_bytes)
        agent_messages = iter_acp_messages(agent_bytes)
        exchange = extract_session_load_from_messages(zed_messages, agent_messages)
        sanitized_zed = reconstruct_sanitized_relay_bytes(zed_messages)
        sanitized_agent = reconstruct_sanitized_relay_bytes(agent_messages)
        result["relay"] = {
            "source": RELAY_EXTRACT_SOURCE,
            "zed_to_agent_sha256": hashlib.sha256(sanitized_zed).hexdigest(),
            "agent_to_zed_sha256": hashlib.sha256(sanitized_agent).hexdigest(),
        }
        result["captured_exchange"] = _safe_payload(exchange)
        result["_sanitized_relay_zed"] = sanitized_zed
        result["_sanitized_relay_agent"] = sanitized_agent
        extract = {
            "source": RELAY_EXTRACT_SOURCE,
            "zed_to_agent_sha256": result["relay"]["zed_to_agent_sha256"],
            "agent_to_zed_sha256": result["relay"]["agent_to_zed_sha256"],
            "request": exchange["request"] if exchange else None,
            "response": exchange["response"] if exchange else None,
        }
        classified = exchange_from_relay_extract(extract)
        after_digest = normal_workspace_source_digest(repo_root)
        result["normal_source"]["sha256_after"] = after_digest
        isolation_after = IsolationEvidence(
            normal_agent_load_session_advertised=isolation.normal_agent_load_session_advertised,
            isolated_probe_load_session_advertised=isolation.isolated_probe_load_session_advertised,
            normal_source_sha256_before=isolation.normal_source_sha256_before,
            normal_source_sha256_after=after_digest,
            isolated_source_root=isolation.isolated_source_root,
            isolated_build_root=isolation.isolated_build_root,
            hermetic_zed_root=isolation.hermetic_zed_root,
            cleanup_dry_run_verified=isolation.cleanup_dry_run_verified,
            cleanup_verified=False,
        )
        finding = classify_live_zed_observation(
            classified,
            isolation_after,
            invocation,
            already_running_zed=False,
            relay_failed=False,
            cleanup_roots_empty=True,
        )
        result["finding"] = finding.value
        if finding is Finding.INDETERMINATE:
            result["indeterminate_reason"] = IndeterminateReason.OBSERVATION_INCOMPLETE.value
        else:
            result["indeterminate_reason"] = None
    except ProbeError as exc:
        record_probe_command_failure(result, exc)
        result["finding"] = Finding.INDETERMINATE.value
        result["indeterminate_reason"] = _reason_from_stage(exc.stage).value
        if not zed_launched:
            result["zed_launches"] = 0
    finally:
        cleaned, leftovers = _cleanup_plan1119_roots(
            run_root=run_root,
            isolated_source=Path(preparation.isolated_source_root) if preparation else None,
            isolated_build=Path(preparation.isolated_build_root) if preparation else None,
            hermetic_root=Path(preparation.hermetic_zed_root) if preparation else None,
        )
        result.setdefault("isolation", {})
        if isinstance(result["isolation"], dict):
            result["isolation"]["cleanup_verified"] = cleaned
        if not cleaned:
            result["finding"] = Finding.INDETERMINATE.value
            result["indeterminate_reason"] = IndeterminateReason.CLEANUP_UNVERIFIED.value
            result["cleanup_remediation"] = leftovers
            result["preflight_ok"] = False
        elif isolation is not None and preparation is not None:
            result["isolation"]["cleanup_dry_run_verified"] = isolation.cleanup_dry_run_verified
            after = normal_workspace_source_digest(repo_root)
            result["normal_source"]["sha256_after"] = after
            if after != isolation.normal_source_sha256_before:
                result["finding"] = Finding.INDETERMINATE.value
                result["indeterminate_reason"] = IndeterminateReason.ISOLATION_PREDICATE_FAILED.value
        if (
            report_dir is not None
            and cleaned
            and isolation is not None
            and isinstance(result.get("normal_source"), dict)
            and result["normal_source"].get("sha256_after") == isolation.normal_source_sha256_before
            and isinstance(result.get("_sanitized_relay_zed"), (bytes, bytearray))
            and isinstance(result.get("_sanitized_relay_agent"), (bytes, bytearray))
        ):
            try:
                result["evidence_manifest"] = str(
                    materialize_sanitized_zed_evidence(
                        report_dir=report_dir,
                        result=result,
                        zed_to_agent=bytes(result["_sanitized_relay_zed"]),
                        agent_to_zed=bytes(result["_sanitized_relay_agent"]),
                    )
                )
            except (ProbeError, OSError, TypeError, ValueError) as exc:
                result["evidence_materialization_error"] = {
                    "type": type(exc).__name__,
                    "stage": exc.stage if isinstance(exc, ProbeError) else "evidence_bundle",
                    "message": _safe_payload(str(exc)),
                }
        try:
            sidecar = parent_workspace / "plan1119-real-zed-result.json"
            sidecar.write_text(
                json.dumps({k: v for k, v in result.items() if not str(k).startswith("_")}, indent=2, sort_keys=True, default=str),
                encoding="utf-8",
                newline="\n",
            )
            result["sidecar"] = str(sidecar)
        except OSError:
            pass
    return result


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("acpx", "acpx-baseline", "preflight", "real-zed"),
        default="acpx",
        help="acpx is the existing non-Zed baseline; preflight never launches Zed; real-zed is the authorized live capture",
    )
    parser.add_argument(
        "--zed-launch-timeout-seconds",
        type=_parse_zed_launch_timeout_seconds,
        default=DEFAULT_ZED_LAUNCH_TIMEOUT_SECONDS,
        help="real-zed launch wait in seconds; unattended default is 180, guided shot uses 900",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="sanitized evidence directory under reports/; required for --mode real-zed",
    )
    parser.add_argument("workspace", type=Path, help="existing throwaway parent directory; never a repository")
    args = parser.parse_args(argv)
    if args.mode == "real-zed" and args.report_dir is None:
        parser.error("--report-dir is required for --mode real-zed")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.mode == "real-zed" and os.environ.get("PYTEST_CURRENT_TEST"):
        print(
            json.dumps(
                {
                    "finding": Finding.INDETERMINATE.value,
                    "zed_launches": 0,
                    "failure": {
                        "stage": "real_zed",
                        "message": "Zed GUI launch is forbidden inside pytest",
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    if args.mode == "preflight":
        result = run_plan1119_preflight(args.workspace)
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0 if result.get("preflight_ok") and result.get("zed_launches") == 0 else 1
    if args.mode == "acpx-baseline":
        result = run_plan1119_acpx_baseline(args.workspace)
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0 if result.get("preflight_ok") and result.get("zed_launches") == 0 else 1
    if args.mode == "real-zed":
        result = run_plan1119_real_zed(
            args.workspace,
            launch_timeout_seconds=args.zed_launch_timeout_seconds,
            report_dir=args.report_dir,
        )
        printable = {key: value for key, value in result.items() if not str(key).startswith("_")}
        print(json.dumps(printable, indent=2, sort_keys=True, default=str))
        return 0 if result.get("isolation", {}).get("cleanup_verified") else 1
    print(json.dumps(run_probe(args.workspace), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
