from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from optimus.acp.trusted_paths import TrustedOperatorRoots, resolve_trusted_operator_roots

_CONFIG_DIR_NAME = "optimus-cost-agent"


class OperatorPathConfigurationError(ValueError):
    def __init__(self, user_message: str, *, exit_code: int = 2) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.exit_code = exit_code


@dataclass(frozen=True)
class OperatorPaths:
    workspace_root: Path
    config_root: Path
    runtime_root: Path
    debug_log_path: Path
    gateway_log_path: Path


def _is_at_or_below(candidate: Path, workspace: Path, *, windows: bool) -> bool:
    resolved_candidate = candidate.resolve()
    resolved_workspace = workspace.resolve()
    if windows:
        folded_candidate = PureWindowsPath(str(resolved_candidate).casefold())
        folded_workspace = PureWindowsPath(str(resolved_workspace).casefold())
        return folded_candidate.is_relative_to(folded_workspace)
    return resolved_candidate.is_relative_to(resolved_workspace)


def _is_windows(platform_name: str | None) -> bool:
    return (platform_name or sys.platform) == "win32"


def _default_config_root(
    environ: Mapping[str, str],
    *,
    platform_name: str | None = None,
) -> Path:
    if _is_windows(platform_name):
        appdata = environ.get("APPDATA", "").strip()
        if not appdata:
            raise OperatorPathConfigurationError(
                "APPDATA is not set. Set APPDATA or set OPTIMUS_CONFIG_ROOT to an "
                "absolute directory outside the workspace."
            )
        return Path(appdata) / _CONFIG_DIR_NAME

    xdg_config_home = environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg_config_home:
        return Path(xdg_config_home) / _CONFIG_DIR_NAME

    home = environ.get("HOME", "").strip()
    if home:
        return Path(home) / ".config" / _CONFIG_DIR_NAME

    return Path.home() / ".config" / _CONFIG_DIR_NAME


def _safe_default_for_remediation(
    environ: Mapping[str, str],
    *,
    platform_name: str | None = None,
) -> Path:
    if _is_windows(platform_name):
        appdata = environ.get("APPDATA", "").strip() or "%APPDATA%"
        return Path(appdata) / _CONFIG_DIR_NAME

    xdg_config_home = environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg_config_home:
        return Path(xdg_config_home) / _CONFIG_DIR_NAME

    home = environ.get("HOME", "").strip() or "~"
    return Path(home) / ".config" / _CONFIG_DIR_NAME


def validate_config_root_override(
    override: str,
    *,
    workspace_root: Path,
    platform_name: str | None = None,
) -> Path:
    """Validate an OPTIMUS_CONFIG_ROOT override value structurally.

    Plan 9.96, Task 5: extracted from the legacy resolve_config_root() so
    trusted-path callers (launch_approval_cli.py, and eventually __main__.py's
    gated flow) can validate an operator-supplied override — must be
    absolute and outside the workspace — without going through the old
    inherited-bootstrap resolve_operator_paths()/resolve_config_root() path.
    Returns the resolved Path. Raises OperatorPathConfigurationError on an
    invalid or workspace-contained override.
    """
    candidate = Path(override)
    if not candidate.is_absolute():
        raise OperatorPathConfigurationError(
            "OPTIMUS_CONFIG_ROOT must be an absolute path. Set OPTIMUS_CONFIG_ROOT to an "
            "absolute directory outside the workspace."
        )

    resolved_candidate = candidate.resolve()
    resolved_workspace = workspace_root.resolve()
    windows = _is_windows(platform_name)

    if _is_at_or_below(resolved_candidate, resolved_workspace, windows=windows):
        raise OperatorPathConfigurationError(
            f"Refusing to load local gateway configuration from {resolved_candidate} because it is inside "
            f"workspace {resolved_workspace}. Set OPTIMUS_CONFIG_ROOT to an absolute directory outside "
            "the workspace."
        )

    return resolved_candidate


def resolve_config_root(
    *,
    workspace_root: Path,
    environ: Mapping[str, str],
    platform_name: str | None = None,
) -> Path:
    override = environ.get("OPTIMUS_CONFIG_ROOT", "").strip()
    if not override:
        return _default_config_root(environ, platform_name=platform_name).resolve()

    safe_default = _safe_default_for_remediation(environ, platform_name=platform_name)
    windows = _is_windows(platform_name)
    if not windows or environ.get("APPDATA", "").strip():
        safe_default = safe_default.resolve()

    candidate = Path(override)
    if not candidate.is_absolute():
        raise OperatorPathConfigurationError(
            "OPTIMUS_CONFIG_ROOT must be an absolute path. Set OPTIMUS_CONFIG_ROOT to an "
            "absolute directory outside the workspace."
        )

    resolved_candidate = candidate.resolve()
    resolved_workspace = workspace_root.resolve()

    if _is_at_or_below(resolved_candidate, resolved_workspace, windows=windows):
        message = (
            f"Refusing to load local gateway configuration from {resolved_candidate} because it is inside "
            f"workspace {resolved_workspace}. Move .env.gateway to {safe_default} or set OPTIMUS_CONFIG_ROOT "
            "to an absolute directory outside the workspace."
        )
        raise OperatorPathConfigurationError(message)

    return resolved_candidate


def resolve_operator_paths(
    *,
    workspace_root: Path | str,
    environ: Mapping[str, str],
    platform_name: str | None = None,
) -> OperatorPaths:
    resolved_workspace = Path(workspace_root).resolve()
    config_root = resolve_config_root(
        workspace_root=resolved_workspace,
        environ=environ,
        platform_name=platform_name,
    )
    runtime_root = resolved_workspace / ".optimus"
    return OperatorPaths(
        workspace_root=resolved_workspace,
        config_root=config_root,
        runtime_root=runtime_root,
        debug_log_path=runtime_root / "debug-acp.ndjson",
        gateway_log_path=runtime_root / "local-gateway.log",
    )


def resolve_authorized_operator_paths(
    *,
    workspace_root: Path | str,
    snapshot_values: Mapping[str, str],
    platform_name: str | None = None,
) -> OperatorPaths:
    """Single shared entry point for resolving operator paths from an
    authorized launch snapshot.

    Plan 9.96, Task 5 review: this is the ONE place that composes trusted-root
    resolution, OPTIMUS_CONFIG_ROOT override validation, and
    resolve_operator_paths_from_trusted(). Every gated caller (the
    optimus-trust CLI, and __main__.py's authorized launch path) must call
    THIS function rather than reimplementing the same three-call sequence —
    two independent implementations of the same security-relevant resolution
    is exactly the shape that produced the Task 4 digest-mismatch bug.

    snapshot_values MUST come from an already-captured LaunchEnvironmentSnapshot
    (snapshot.values), never a live os.environ read — OPTIMUS_CONFIG_ROOT is a
    Security-tier name folded into the approval digest, so resolving it from
    a source other than the captured snapshot can let the digest-bound value
    and the actually-used config root diverge.
    """
    trusted_roots = resolve_trusted_operator_roots(platform_name=platform_name or sys.platform)
    override = snapshot_values.get("OPTIMUS_CONFIG_ROOT", "").strip()
    validated_config_root = (
        validate_config_root_override(override, workspace_root=Path(workspace_root), platform_name=platform_name)
        if override
        else None
    )
    return resolve_operator_paths_from_trusted(
        workspace_root=workspace_root,
        trusted_roots=trusted_roots,
        validated_config_root=validated_config_root,
        platform_name=platform_name,
    )


def resolve_operator_paths_from_trusted(
    *,
    workspace_root: Path | str,
    trusted_roots: TrustedOperatorRoots,
    validated_config_root: Path | None = None,
    platform_name: str | None = None,
) -> OperatorPaths:
    """Resolve operator paths from already-validated trusted roots.

    Plan 9.96, Task 2: This function receives pre-validated inputs from the
    launch gate. It does NOT read inherited APPDATA/HOME/XDG_CONFIG_HOME or
    OPTIMUS_CONFIG_ROOT from the environment — those are resolved and validated
    earlier in the launch authorization flow.

    If validated_config_root is provided, it has already passed containment,
    permission, and approval checks. Otherwise, the OS-derived default from
    trusted_roots is used.

    The workspace .optimus runtime root (debug/Gateway logs) remains inside the
    workspace, separate from the external approval runtime root.
    """
    resolved_workspace = Path(workspace_root).resolve()

    if validated_config_root is not None:
        config_root = validated_config_root.resolve()
    else:
        config_root = trusted_roots.default_config_root

    # Containment check: config_root must not be inside the workspace.
    windows = _is_windows(platform_name)
    if _is_at_or_below(config_root, resolved_workspace, windows=windows):
        raise OperatorPathConfigurationError(
            f"Validated config root {config_root} is inside workspace {resolved_workspace}. "
            "This should have been caught during launch authorization."
        )

    runtime_root = resolved_workspace / ".optimus"
    return OperatorPaths(
        workspace_root=resolved_workspace,
        config_root=config_root,
        runtime_root=runtime_root,
        debug_log_path=runtime_root / "debug-acp.ndjson",
        gateway_log_path=runtime_root / "local-gateway.log",
    )
