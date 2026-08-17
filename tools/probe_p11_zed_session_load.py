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
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PureWindowsPath
from typing import Any

from optimus_security.sanitization import EVIDENCE_REDACTION_POLICY, sanitize_for_persistence


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


def _ambient_profile_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    for key in ("APPDATA", "LOCALAPPDATA", "USERPROFILE"):
        raw = os.environ.get(key, "").strip()
        if raw:
            roots.append(Path(raw))
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
        if user_resolved == profile or user_resolved.is_relative_to(profile):
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
    """Bind Zed to a new hermetic root using a flag found in this version's help text."""
    hermetic = hermetic_root.resolve()
    flag = _discover_user_data_flag(help_output)
    if flag is None:
        raise ProbeError("zed_discovery", "current-version hermetic invocation flag was not discovered")
    environment_bind = (
        ("APPDATA", str(hermetic / "AppData" / "Roaming")),
        ("LOCALAPPDATA", str(hermetic / "AppData" / "Local")),
        ("USERPROFILE", str(hermetic)),
        ("HOME", str(hermetic)),
    )
    return ZedInvocation(
        argv=(str(executable), flag, str(hermetic)),
        user_data_root=str(hermetic),
        discovered_from="zed --help",
        version=version_output.strip(),
        executable_sha256=executable_sha256,
        environment_bind=environment_bind,
    )


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
) -> list[str]:
    """Build the Plan 11.7 opaque relay argv; byte interpretation stays out of the relay process."""
    if invocation.user_data_root is None:
        raise ProbeError("zed_invocation", "current-version hermetic invocation descriptor is missing")
    validate_zed_invocation(invocation, hermetic_root=Path(invocation.user_data_root))
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
        str(child_executable),
    ]


def validate_acpx_baseline(evidence: AcpxBaselineEvidence) -> None:
    """Require the isolated initialize payload to advertise loadSession; forbid origin-A."""
    if evidence.origin_a_launches != 0:
        raise ProbeError("acpx_baseline", "origin-A launches are forbidden")
    if dict(evidence.capability_payload).get("loadSession") is not True:
        raise ProbeError("acpx_baseline", "isolated probe must advertise loadSession")


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


def build_acpx_command(acpx: Path, *, workspace: Path, agent: Path) -> list[str]:
    """Build a raw acpx agent command with slash-normalized Windows paths."""
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
        "1",
        "--cwd",
        str(workspace),
        "--agent",
        subprocess.list2cmdline(
            [
                PureWindowsPath(agent).as_posix(),
                "--workspace-root",
                PureWindowsPath(workspace).as_posix(),
                "--no-auto-start",
            ]
        ),
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
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ProbeError(stage, "interactive TTY required for Optimus launch-approval ceremony")
    try:
        completed = subprocess.run(list(command), cwd=cwd, check=False, shell=False)  # noqa: S603
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
        command = build_acpx_command(acpx, workspace=workspace, agent=agent)
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
        result["failure"] = {"stage": exc.stage, "message": _safe_payload(str(exc))}
        if exc.command_result is not None:
            failure_evidence = capture_acpx_evidence(exc.command_result)
            result["acpx_failure"] = failure_evidence
            result["capability_payload"] = failure_evidence["capability_payload"]
            result["session_load_exchange"] = failure_evidence["session_load_exchange"]
            result.update(classify_indeterminate_context(failure_evidence))
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


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("acpx", "acpx-baseline", "preflight", "real-zed"),
        default="acpx",
        help="acpx is the existing non-Zed baseline; real-zed stays unauthorized until Task 4",
    )
    parser.add_argument("workspace", type=Path, help="existing throwaway parent directory; never a repository")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.mode == "real-zed":
        print(
            json.dumps(
                {
                    "finding": Finding.INDETERMINATE.value,
                    "zed_launches": 0,
                    "failure": {
                        "stage": "real_zed",
                        "message": "live Zed launch requires a separate recorded operator authorization",
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    if args.mode != "acpx":
        print(
            json.dumps(
                {
                    "mode": args.mode,
                    "finding": Finding.INDETERMINATE.value,
                    "zed_launches": 0,
                    "origin_a_launches": 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    print(json.dumps(run_probe(args.workspace), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
