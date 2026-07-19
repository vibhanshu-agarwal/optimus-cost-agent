from __future__ import annotations

import pytest

from optimus.acp.operator_paths import (
    OperatorPathConfigurationError,
    _is_at_or_below,
    resolve_operator_paths,
)


def test_windows_default_config_root_uses_appdata_outside_workspace(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    appdata = tmp_path / "operator" / "AppData" / "Roaming"
    paths = resolve_operator_paths(
        workspace_root=workspace,
        environ={"APPDATA": str(appdata)},
        platform_name="win32",
    )
    assert paths.workspace_root == workspace.resolve()
    assert paths.config_root == (appdata / "optimus-cost-agent").resolve()
    assert paths.runtime_root == (workspace / ".optimus").resolve()
    assert paths.debug_log_path == paths.runtime_root / "debug-acp.ndjson"
    assert paths.gateway_log_path == paths.runtime_root / "local-gateway.log"


def test_absolute_config_override_outside_workspace_wins(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    config = tmp_path / "operator-config"
    paths = resolve_operator_paths(
        workspace_root=workspace,
        environ={"OPTIMUS_CONFIG_ROOT": str(config)},
        platform_name="win32",
    )
    assert paths.config_root == config.resolve()


@pytest.mark.parametrize("suffix", ["", "config", "nested/config"])
def test_config_root_rejects_workspace_or_descendant(tmp_path, suffix) -> None:
    workspace = tmp_path / "workspace"
    candidate = workspace / suffix
    with pytest.raises(OperatorPathConfigurationError, match="Move .env.gateway"):
        resolve_operator_paths(
            workspace_root=workspace,
            environ={"OPTIMUS_CONFIG_ROOT": str(candidate)},
            platform_name="win32",
        )


def test_config_root_rejects_case_variant_workspace_descendant_on_windows(tmp_path) -> None:
    workspace = tmp_path / "WorkSpace"
    candidate = tmp_path / "workspace" / "CONFIG"
    assert _is_at_or_below(candidate, workspace, windows=True)


def test_string_prefix_sibling_is_not_treated_as_descendant(tmp_path) -> None:
    workspace = tmp_path / "repo"
    sibling = tmp_path / "repo-safe-config"
    assert not _is_at_or_below(sibling, workspace, windows=False)


def test_relative_config_root_fails(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    with pytest.raises(OperatorPathConfigurationError, match="absolute"):
        resolve_operator_paths(
            workspace_root=workspace,
            environ={"OPTIMUS_CONFIG_ROOT": "relative/path"},
            platform_name="win32",
        )


def test_missing_appdata_on_windows_fails(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    with pytest.raises(OperatorPathConfigurationError, match="APPDATA"):
        resolve_operator_paths(
            workspace_root=workspace,
            environ={},
            platform_name="win32",
        )


def test_posix_default_uses_xdg_config_home(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    xdg = tmp_path / "xdg-config"
    paths = resolve_operator_paths(
        workspace_root=workspace,
        environ={"XDG_CONFIG_HOME": str(xdg)},
        platform_name="linux",
    )
    assert paths.config_root == (xdg / "optimus-cost-agent").resolve()


def test_posix_fallback_uses_home_dot_config(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    paths = resolve_operator_paths(
        workspace_root=workspace,
        environ={"HOME": str(home)},
        platform_name="linux",
    )
    assert paths.config_root == (home / ".config" / "optimus-cost-agent").resolve()


def test_containment_resolves_dotdot_before_check(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    nested = workspace / "a" / "b"
    nested.mkdir(parents=True)
    candidate_via_dotdot = nested / ".." / "config"
    with pytest.raises(OperatorPathConfigurationError, match="Move .env.gateway"):
        resolve_operator_paths(
            workspace_root=workspace,
            environ={"OPTIMUS_CONFIG_ROOT": str(candidate_via_dotdot)},
            platform_name="linux",
        )


def test_symlink_resolved_before_containment_check(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    inner = workspace / "inner"
    inner.mkdir()
    outside_link = tmp_path / "outside-link"
    try:
        outside_link.symlink_to(inner, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation requires elevated privileges on this host")
    with pytest.raises(OperatorPathConfigurationError, match="Move .env.gateway"):
        resolve_operator_paths(
            workspace_root=workspace,
            environ={"OPTIMUS_CONFIG_ROOT": str(outside_link)},
            platform_name="linux",
        )


def test_resolution_does_not_create_directories(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    config = tmp_path / "config"
    appdata = tmp_path / "appdata"
    mkdir_called = False
    original_mkdir = type(workspace).mkdir

    def tracking_mkdir(self, *args, **kwargs):
        nonlocal mkdir_called
        mkdir_called = True
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(type(workspace), "mkdir", tracking_mkdir)
    resolve_operator_paths(
        workspace_root=workspace,
        environ={"OPTIMUS_CONFIG_ROOT": str(config), "APPDATA": str(appdata)},
        platform_name="win32",
    )
    assert not mkdir_called
    assert not workspace.exists()
    assert not config.exists()


# --- Task 2 Step 4: Tests for resolve_operator_paths_from_trusted ---


def test_trusted_paths_uses_validated_config_root(tmp_path) -> None:
    from optimus.acp.operator_paths import resolve_operator_paths_from_trusted
    from optimus.acp.trusted_paths import TrustedOperatorRoots

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    validated_config = tmp_path / "validated-config"

    roots = TrustedOperatorRoots(
        default_config_root=tmp_path / "os-default-config",
        approval_runtime_root=tmp_path / "os-runtime",
    )
    paths = resolve_operator_paths_from_trusted(
        workspace_root=workspace,
        trusted_roots=roots,
        validated_config_root=validated_config,
    )
    assert paths.config_root == validated_config.resolve()
    assert paths.runtime_root == workspace.resolve() / ".optimus"


def test_trusted_paths_falls_back_to_os_default(tmp_path) -> None:
    from optimus.acp.operator_paths import resolve_operator_paths_from_trusted
    from optimus.acp.trusted_paths import TrustedOperatorRoots

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    os_config = tmp_path / "os-default-config"

    roots = TrustedOperatorRoots(
        default_config_root=os_config,
        approval_runtime_root=tmp_path / "os-runtime",
    )
    paths = resolve_operator_paths_from_trusted(
        workspace_root=workspace,
        trusted_roots=roots,
    )
    assert paths.config_root == os_config


def test_trusted_paths_rejects_workspace_contained_config(tmp_path) -> None:
    from optimus.acp.operator_paths import (
        OperatorPathConfigurationError,
        resolve_operator_paths_from_trusted,
    )
    from optimus.acp.trusted_paths import TrustedOperatorRoots

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    inside_workspace = workspace / "inside-config"

    roots = TrustedOperatorRoots(
        default_config_root=tmp_path / "os-default-config",
        approval_runtime_root=tmp_path / "os-runtime",
    )
    with pytest.raises(OperatorPathConfigurationError):
        resolve_operator_paths_from_trusted(
            workspace_root=workspace,
            trusted_roots=roots,
            validated_config_root=inside_workspace,
        )
