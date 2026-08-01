"""Strict scenario load, binding resolution, and digest tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_TOML = REPO_ROOT / "tests/fixtures/evidence/scenarios/zed-session.toml"
FIXTURE_JSON = REPO_ROOT / "tests/fixtures/evidence/scenarios/zed-session.json"


def _scenarios():
    from evidence_handoff.collector import scenarios

    return scenarios


def _models():
    from evidence_handoff.collector import models

    return models


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_toml_and_json_fixtures_produce_identical_scenarios() -> None:
    scenarios = _scenarios()
    models = _models()
    from_toml = scenarios.load_scenario(FIXTURE_TOML)
    from_json = scenarios.load_scenario(FIXTURE_JSON)
    assert from_toml == from_json
    assert from_toml.schema == "evidence-scenario-v1"
    assert from_toml.scenario_id == "zed-session"
    assert from_toml.required_bindings[0].name == "model"
    assert from_toml.required_bindings[0].kind is models.BindingKind.STRING
    assert from_toml.client.adapter_id == "zed_acp_client"
    # Fixture requires model at runtime and never assigns a model parameter value.
    assert from_toml.client.parameters == ()
    assert all(
        parameter.name != "model" for parameter in from_toml.client.parameters
    )
    canonical = json.dumps(models.scenario_to_canonical_dict(from_toml), sort_keys=True)
    assert '"name": "model"' in canonical
    assert '"value"' not in canonical.split('"required_bindings"')[1].split('"client"')[0]


def test_toml_json_parity_includes_identical_digests_after_binding() -> None:
    scenarios = _scenarios()
    from_toml = scenarios.load_scenario(FIXTURE_TOML)
    from_json = scenarios.load_scenario(FIXTURE_JSON)
    bindings_toml = scenarios.resolve_bindings(from_toml, ("model=operator-supplied",))
    bindings_json = scenarios.resolve_bindings(from_json, ("model=operator-supplied",))
    assert scenarios.scenario_sha256(from_toml, bindings_toml) == scenarios.scenario_sha256(
        from_json, bindings_json
    )


def test_rejects_unknown_top_level_field(tmp_path: Path) -> None:
    scenarios = _scenarios()
    path = _write(
        tmp_path,
        "unknown.toml",
        FIXTURE_TOML.read_text(encoding="utf-8") + "\nextra_field = true\n",
    )
    with pytest.raises(ValueError, match="unknown_field"):
        scenarios.load_scenario(path)


def test_rejects_unknown_nested_field(tmp_path: Path) -> None:
    scenarios = _scenarios()
    payload = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    payload["client"]["shell"] = "powershell"
    path = _write(tmp_path, "nested.json", json.dumps(payload))
    with pytest.raises(ValueError, match="unknown_field|non_executable_input"):
        scenarios.load_scenario(path)


def test_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    scenarios = _scenarios()
    path = _write(
        tmp_path,
        "dup.json",
        '{"schema":"evidence-scenario-v1","schema":"evidence-scenario-v1"}',
    )
    with pytest.raises(ValueError, match="duplicate_key"):
        scenarios.load_scenario(path)


def test_rejects_unknown_schema(tmp_path: Path) -> None:
    scenarios = _scenarios()
    payload = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    payload["schema"] = "evidence-scenario-v0"
    path = _write(tmp_path, "schema.json", json.dumps(payload))
    with pytest.raises(ValueError, match="unknown_schema"):
        scenarios.load_scenario(path)


@pytest.mark.parametrize(
    "scenario_id",
    [
        "-".join(["EVIDENCE", "HANDOFF", "FEAT", "EVIDENCE", "COLLECTOR"]),
        "Plan 12",
        "plan-12-collector",
        "../escape",
        "has/slash",
        "HasUpper",
        "",
    ],
)
def test_rejects_unsafe_scenario_id(tmp_path: Path, scenario_id: str) -> None:
    scenarios = _scenarios()
    payload = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    payload["scenario_id"] = scenario_id
    path = _write(tmp_path, "unsafe.json", json.dumps(payload))
    with pytest.raises(ValueError, match="unsafe_scenario_id"):
        scenarios.load_scenario(path)


def test_rejects_binding_type_mismatch(tmp_path: Path) -> None:
    scenarios = _scenarios()
    payload = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    payload["required_bindings"] = [
        {
            "name": "timeout_ms",
            "kind": "integer",
            "required": True,
        }
    ]
    path = _write(tmp_path, "int-binding.json", json.dumps(payload))
    scenario = scenarios.load_scenario(path)
    with pytest.raises(ValueError, match="invalid_binding"):
        scenarios.resolve_bindings(scenario, ("timeout_ms=not-an-int",))


def test_rejects_binding_bounds_violation() -> None:
    scenarios = _scenarios()
    scenario = scenarios.load_scenario(FIXTURE_JSON)
    with pytest.raises(ValueError, match="empty_binding|invalid_bounds"):
        scenarios.resolve_bindings(scenario, ("model=",))
    with pytest.raises(ValueError, match="invalid_bounds"):
        scenarios.resolve_bindings(scenario, ("model=" + ("x" * 300),))


def test_rejects_missing_empty_and_duplicate_model_bindings() -> None:
    scenarios = _scenarios()
    scenario = scenarios.load_scenario(FIXTURE_JSON)
    with pytest.raises(ValueError, match="missing_binding"):
        scenarios.resolve_bindings(scenario, ())
    with pytest.raises(ValueError, match="empty_binding|invalid_bounds"):
        scenarios.resolve_bindings(scenario, ("model=",))
    with pytest.raises(ValueError, match="duplicate_binding"):
        scenarios.resolve_bindings(scenario, ("model=a", "model=b"))


def test_rejects_unknown_supplied_binding() -> None:
    scenarios = _scenarios()
    scenario = scenarios.load_scenario(FIXTURE_JSON)
    with pytest.raises(ValueError, match="unknown_binding"):
        scenarios.resolve_bindings(scenario, ("model=ok", "extra=1"))


@pytest.mark.parametrize(
    "forbidden_fragment",
    [
        'import_path = "os.path"',
        'module = "subprocess"',
        'expression = "1+1"',
        'shell = "echo hi"',
        'command = "rm -rf /"',
        'hook = "pre_start"',
        'env = "HOME"',
        'argv = ["python", "-c", "pass"]',
        'entry_point = "pkg:main"',
        'package = "evil_pkg"',
    ],
)
def test_rejects_non_executable_input_constructs(
    tmp_path: Path, forbidden_fragment: str
) -> None:
    scenarios = _scenarios()
    text = FIXTURE_TOML.read_text(encoding="utf-8") + f"\n{forbidden_fragment}\n"
    path = _write(tmp_path, "exec.toml", text)
    with pytest.raises(ValueError, match="non_executable_input|unknown_field"):
        scenarios.load_scenario(path)


def test_rejects_environment_expansion_and_shell_metacharacters_in_parameters(
    tmp_path: Path,
) -> None:
    scenarios = _scenarios()
    payload = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    payload["client"]["parameters"] = [
        {"name": "label", "kind": "string", "value": "${HOME}/x"}
    ]
    path = _write(tmp_path, "env.json", json.dumps(payload))
    with pytest.raises(ValueError, match="non_executable_input"):
        scenarios.load_scenario(path)

    payload["client"]["parameters"] = [
        {"name": "label", "kind": "string", "value": "$(uname)"}
    ]
    path = _write(tmp_path, "shell.json", json.dumps(payload))
    with pytest.raises(ValueError, match="non_executable_input"):
        scenarios.load_scenario(path)


def test_rejects_ambiguous_toml_parameter_types(tmp_path: Path) -> None:
    scenarios = _scenarios()
    # Integer-typed parameter must not accept a TOML string; no silent coercion.
    text = FIXTURE_TOML.read_text(encoding="utf-8").replace(
        "parameters = []",
        'parameters = [{name = "timeout_ms", kind = "integer", value = "30"}]',
        1,
    )
    path = _write(tmp_path, "ambiguous.toml", text)
    with pytest.raises(ValueError, match="ambiguous_type|invalid_binding"):
        scenarios.load_scenario(path)


def test_boolean_binding_rejects_ambiguous_cli_tokens(tmp_path: Path) -> None:
    scenarios = _scenarios()
    payload = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    payload["required_bindings"] = [
        {"name": "enabled", "kind": "boolean", "required": True}
    ]
    path = _write(tmp_path, "bool.json", json.dumps(payload))
    scenario = scenarios.load_scenario(path)
    with pytest.raises(ValueError, match="ambiguous_type|invalid_binding"):
        scenarios.resolve_bindings(scenario, ("enabled=yes",))
    bindings = scenarios.resolve_bindings(scenario, ("enabled=true",))
    assert bindings[0].value is True


def test_absolute_path_binding_requires_absolute_value(tmp_path: Path) -> None:
    scenarios = _scenarios()
    payload = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    payload["required_bindings"] = [
        {"name": "capture", "kind": "absolute_path", "required": True}
    ]
    path = _write(tmp_path, "path.json", json.dumps(payload))
    scenario = scenarios.load_scenario(path)
    with pytest.raises(ValueError, match="invalid_binding"):
        scenarios.resolve_bindings(scenario, ("capture=relative/path",))
    absolute = str((tmp_path / "abs").resolve())
    bindings = scenarios.resolve_bindings(scenario, (f"capture={absolute}",))
    assert bindings[0].kind.value == "absolute_path"
    assert bindings[0].value == absolute


@pytest.mark.parametrize(
    "absolute_value",
    [
        "/tmp/evidence",
        "C:/Users/pc/evidence",
        r"C:\Users\pc\evidence",
        r"\\server\share\evidence",
        "//server/share/evidence",
    ],
)
def test_absolute_path_binding_accepts_portable_absolute_syntax(
    tmp_path: Path, absolute_value: str
) -> None:
    """Host-independent absolute syntax — same accept/reject on Windows and POSIX."""
    scenarios = _scenarios()
    payload = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    payload["required_bindings"] = [
        {"name": "capture", "kind": "absolute_path", "required": True}
    ]
    path = _write(tmp_path, "portable-abs.json", json.dumps(payload))
    scenario = scenarios.load_scenario(path)
    bindings = scenarios.resolve_bindings(scenario, (f"capture={absolute_value}",))
    assert bindings[0].value == absolute_value


@pytest.mark.parametrize(
    "relative_value",
    [
        "relative/path",
        "./local",
        "../escape",
        "~/evidence",
        "C:relative",  # drive-relative, not absolute
    ],
)
def test_absolute_path_binding_rejects_non_absolute_on_any_host(
    tmp_path: Path, relative_value: str
) -> None:
    scenarios = _scenarios()
    payload = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    payload["required_bindings"] = [
        {"name": "capture", "kind": "absolute_path", "required": True}
    ]
    path = _write(tmp_path, "portable-rel.json", json.dumps(payload))
    scenario = scenarios.load_scenario(path)
    with pytest.raises(ValueError, match="invalid_binding"):
        scenarios.resolve_bindings(scenario, (f"capture={relative_value}",))


@pytest.mark.parametrize(
    "value",
    [
        "$HOME/x",
        "%HOMEPATH%/x",
        "%USERPROFILE%\\evidence",
        "${HOME}/x",
        "$(uname)",
    ],
)
def test_rejects_bare_and_windows_env_expansion_in_parameters(
    tmp_path: Path, value: str
) -> None:
    scenarios = _scenarios()
    payload = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    payload["client"]["parameters"] = [
        {"name": "label", "kind": "string", "value": value}
    ]
    path = _write(tmp_path, "env-forms.json", json.dumps(payload))
    with pytest.raises(ValueError, match="non_executable_input"):
        scenarios.load_scenario(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("adapter_id", "$(id) PromptInject"),
        ("adapter_id", "safe`evil"),
        ("adapter_id", "safe\nevil"),
        ("adapter_id", "$HOME-client"),
        ("adapter_id", "%USERNAME%-client"),
        ("contract_version", "$(uname)"),
        ("contract_version", "%VERSION%"),
    ],
)
def test_rejects_executable_content_in_adapter_id_and_contract_version(
    tmp_path: Path, field: str, value: str
) -> None:
    scenarios = _scenarios()
    payload = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    payload["client"][field] = value
    path = _write(tmp_path, "adapter-exec.json", json.dumps(payload))
    with pytest.raises(ValueError, match="non_executable_input"):
        scenarios.load_scenario(path)


@pytest.mark.parametrize(
    "adapter_id",
    [
        "PromptInject",
        "prompt_inject_client",
        "zed-PROMPT-INJECT",
        "Prompt-Injection-Adapter",
    ],
)
def test_rejects_prompt_injection_adapter_ids_case_insensitively(
    tmp_path: Path, adapter_id: str
) -> None:
    scenarios = _scenarios()
    payload = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    payload["client"]["adapter_id"] = adapter_id
    path = _write(tmp_path, "prompt-inject.json", json.dumps(payload))
    with pytest.raises(ValueError, match="non_executable_input"):
        scenarios.load_scenario(path)


def test_scenario_sha256_is_stable_hex_digest() -> None:
    scenarios = _scenarios()
    scenario = scenarios.load_scenario(FIXTURE_JSON)
    bindings = scenarios.resolve_bindings(scenario, ("model=operator-supplied",))
    digest = scenarios.scenario_sha256(scenario, bindings)
    assert len(digest) == 64
    assert digest == digest.lower()
    assert digest == scenarios.scenario_sha256(scenario, bindings)
