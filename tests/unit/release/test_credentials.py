from __future__ import annotations

from pathlib import Path

from optimus.release.credentials import (
    ALLOWED_LOCAL_CREDENTIAL_NAMES,
    PROVIDER_CREDENTIAL_NAMES,
    scan_local_credentials,
)


def test_scanner_allows_only_optimus_gateway_credentials(monkeypatch):
    for key in PROVIDER_CREDENTIAL_NAMES | ALLOWED_LOCAL_CREDENTIAL_NAMES:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.optimus.ai")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt-test")

    result = scan_local_credentials()

    assert result.passed is True
    assert result.allowed_present == ("OPTIMUS_API_KEY", "OPTIMUS_GATEWAY_URL")
    assert result.provider_keys_resolvable == ()


def test_scanner_fails_when_provider_key_is_resolvable(monkeypatch):
    for key in PROVIDER_CREDENTIAL_NAMES | ALLOWED_LOCAL_CREDENTIAL_NAMES:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.optimus.ai")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    result = scan_local_credentials()

    assert result.passed is False
    assert result.provider_keys_resolvable == ("OPENAI_API_KEY",)


def test_scanner_honors_explicit_empty_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-env")

    result = scan_local_credentials(environ={})

    assert result.passed is True
    assert result.allowed_present == ()
    assert result.provider_keys_resolvable == ()


def test_scanner_checks_selected_config_text_without_returning_secret_values(tmp_path, monkeypatch):
    for key in PROVIDER_CREDENTIAL_NAMES | ALLOWED_LOCAL_CREDENTIAL_NAMES:
        monkeypatch.delenv(key, raising=False)
    config = tmp_path / ".env"
    config.write_text("LANGSMITH_API_KEY=ls-test\nOPTIMUS_API_KEY=opt-test\n", encoding="utf-8")

    result = scan_local_credentials(config_paths=(config,))

    assert result.passed is False
    assert result.provider_keys_resolvable == ("LANGSMITH_API_KEY",)
    assert "ls-test" not in result.summary
    assert "LANGSMITH_API_KEY" in result.summary


def test_scanner_detects_json_and_yaml_process_snapshot_keys(tmp_path, monkeypatch):
    for key in PROVIDER_CREDENTIAL_NAMES | ALLOWED_LOCAL_CREDENTIAL_NAMES:
        monkeypatch.delenv(key, raising=False)
    snapshot = tmp_path / "process-state.json"
    snapshot.write_text('{"env": {"OPENROUTER_API_KEY": "or-test"}, "yaml": "TAVILY_API_KEY: tvly-test"}', encoding="utf-8")

    result = scan_local_credentials(config_paths=(snapshot,))

    assert result.passed is False
    assert result.provider_keys_resolvable == ("OPENROUTER_API_KEY", "TAVILY_API_KEY")
    assert "or-test" not in result.summary
    assert "tvly-test" not in result.summary


def test_default_release_scan_paths_cover_runner_local_artifacts():
    from optimus.release.credentials import DEFAULT_RELEASE_CREDENTIAL_SCAN_PATHS

    expected = {
        Path(".env"),
        Path(".env.local"),
        Path("pyproject.toml"),
        Path("reports/phase1-release-gate.json"),
        Path("reports/phase1-golden-results.json"),
        Path("reports/process-state.json"),
    }

    assert expected.issubset(set(DEFAULT_RELEASE_CREDENTIAL_SCAN_PATHS))


def test_scanner_detects_provider_key_in_default_release_artifact(tmp_path, monkeypatch):
    from optimus.release.credentials import default_release_credential_scan_paths

    for key in PROVIDER_CREDENTIAL_NAMES | ALLOWED_LOCAL_CREDENTIAL_NAMES:
        monkeypatch.delenv(key, raising=False)
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "phase1-golden-results.json").write_text(
        '{"results": [{"provider_keys_resolvable": ["OPENAI_API_KEY"], "OPENAI_API_KEY": "sk-test"}]}',
        encoding="utf-8",
    )

    result = scan_local_credentials(
        environ={"OPTIMUS_GATEWAY_URL": "https://gateway.example", "OPTIMUS_API_KEY": "opt-test"},
        config_paths=default_release_credential_scan_paths(root=tmp_path),
    )

    assert result.passed is False
    assert result.provider_keys_resolvable == ("OPENAI_API_KEY",)
    assert "sk-test" not in result.summary


def test_scanner_does_not_fail_on_provider_key_names_as_report_data(tmp_path, monkeypatch):
    from optimus.release.credentials import default_release_credential_scan_paths

    for key in PROVIDER_CREDENTIAL_NAMES | ALLOWED_LOCAL_CREDENTIAL_NAMES:
        monkeypatch.delenv(key, raising=False)
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "phase1-golden-results.json").write_text(
        '{"results": [{"provider_keys_resolvable": ["OPENAI_API_KEY"]}]}',
        encoding="utf-8",
    )

    result = scan_local_credentials(
        environ={"OPTIMUS_GATEWAY_URL": "https://gateway.example", "OPTIMUS_API_KEY": "opt-test"},
        config_paths=default_release_credential_scan_paths(root=tmp_path),
    )

    assert result.passed is True
    assert result.provider_keys_resolvable == ()


def test_scanner_detects_provider_key_assignment_inside_json_string_value(tmp_path, monkeypatch):
    from optimus.release.credentials import default_release_credential_scan_paths

    for key in PROVIDER_CREDENTIAL_NAMES | ALLOWED_LOCAL_CREDENTIAL_NAMES:
        monkeypatch.delenv(key, raising=False)
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "phase1-release-gate.json").write_text(
        '{"results": [{"name": "unit-and-integration-tests", "output_summary": "OPENAI_API_KEY=sk-test"}]}',
        encoding="utf-8",
    )

    result = scan_local_credentials(
        environ={"OPTIMUS_GATEWAY_URL": "https://gateway.example", "OPTIMUS_API_KEY": "opt-test"},
        config_paths=default_release_credential_scan_paths(root=tmp_path),
    )

    assert result.passed is False
    assert result.provider_keys_resolvable == ("OPENAI_API_KEY",)
    assert "sk-test" not in result.summary
