"""Plan 12.10 Task 2: one-time setup, the approved configuration and what a launch binds. Real files; Docker and Redis are proven in
tests/integration/context."""

from __future__ import annotations

import base64
import fnmatch
import json
from pathlib import Path
from typing import Any

import pytest

from optimus.acp import launch_approval_cli, local_infra, memory_setup
from optimus.acp.local_gateway_secrets import CredentialLayer, CredentialProvenance, ProviderCredentialResolution, ProviderSecrets
from optimus_gateway import __main__ as gateway_main
from optimus_model_policy.binding import trusted_approval_literal
from optimus_security import gateway_identity as gi
from optimus_security import launch_manifest as lm
from optimus_security import memory_index_config as mc
from tests.unit.acp.conftest import FakeKeyring


def _download(*, repository: str, revision: str, target: Path) -> None:
    (target / "model.onnx").write_bytes(f"{repository}@{revision}".encode())
    (target / ".cache").mkdir(exist_ok=True)
    (target / ".cache" / "bookkeeping").write_text("download tool state", encoding="utf-8")


def _settings(tmp_path: Path) -> dict[str, Any]:
    probe = tmp_path / "probe"
    probe.mkdir(exist_ok=True)
    (probe / "model.onnx").write_bytes(b"test/repository@abc")
    return {
        "image": "redis@sha256:" + "a" * 64, "container": "test-redis", "volume": "test-data", "host": "127.0.0.1", "port": 6399, "user": "optimus-index",
        "maxmemory_mb": 128, "artifact_megabytes": 1,
        "embedding": {"model": "test/model", "source": "test", "repository": "test/repository", "revision": "abc", "licence": "MIT", "dimensions": 8,
                      "max_input_tokens": 16, "artifact_directory": "model", "artifact_sha256": mc.artifact_digest(probe)},
    }


def _run(tmp_path: Path, keyring: Any = None, confirm: Any = lambda _d: True, **overrides: Any) -> Path:
    settings = {**_settings(tmp_path), **overrides}
    return memory_setup.run_setup(tmp_path, keyring_backend=keyring or FakeKeyring(), confirm=confirm, download=_download, defaults=settings)


def test_setup_writes_only_non_secret_files_and_the_keyring_holds_the_password(tmp_path: Path) -> None:
    keyring = FakeKeyring()
    path = _run(tmp_path, keyring)
    root = path.parent
    _literal, config, refusal = mc.read(root)
    assert refusal is None and config is not None
    password = keyring.get_password(mc.KEYRING_SERVICE, config.credential_name)
    assert password
    for file in root.rglob("*"):
        if file.is_file():
            assert password.encode() not in file.read_bytes(), file
    assert "user default off" in (root / mc.ACL_NAME).read_text(encoding="utf-8")


def test_setup_only_opens_the_index_key_pattern_and_named_commands(tmp_path: Path) -> None:
    acl = (_run(tmp_path).parent / mc.ACL_NAME).read_text(encoding="utf-8")
    assert "~oidx:*" in acl and "-@all" in acl and "+@all" not in acl and "+eval" not in acl and "+flushall" not in acl


def test_a_declined_setup_changes_nothing(tmp_path: Path) -> None:
    keyring = FakeKeyring()
    with pytest.raises(memory_setup.MemorySetupError):
        _run(tmp_path, keyring, confirm=lambda _d: False)
    assert not mc.memory_index_root(tmp_path).exists()
    assert keyring.get_password(mc.KEYRING_SERVICE, "redis-password") is None


def test_the_description_names_what_will_happen_before_any_download(tmp_path: Path) -> None:
    described: list[str] = []

    def confirm(description: str) -> bool:
        described.append(description)
        assert not mc.memory_index_root(tmp_path).exists()
        return True

    _run(tmp_path, confirm=confirm)
    for fact in ("test/model", "abc", "MIT", "test-redis", "test-data", "6399", "No model is called"):
        assert fact in described[0]


def test_a_wrong_artifact_configures_nothing_and_stores_no_password(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings["embedding"]["artifact_sha256"] = "0" * 64
    keyring = FakeKeyring()
    with pytest.raises(memory_setup.MemorySetupError, match="digest"):
        memory_setup.run_setup(tmp_path, keyring_backend=keyring, confirm=lambda _d: True, download=_download, defaults=settings)
    assert not (mc.memory_index_root(tmp_path) / mc.CONFIG_NAME).exists()
    assert keyring.get_password(mc.KEYRING_SERVICE, "redis-password") is None


def test_a_keyring_failure_configures_nothing(tmp_path: Path) -> None:
    class Broken(FakeKeyring):
        def set_password(self, *_args: Any) -> None:
            raise OSError("no keyring")

    with pytest.raises(memory_setup.MemorySetupError, match="keyring") as raised:
        _run(tmp_path, Broken())
    assert "no keyring" not in str(raised.value)
    assert not (mc.memory_index_root(tmp_path) / mc.CONFIG_NAME).exists()


def test_a_rerun_never_replaces_a_working_password_or_downloads_again(tmp_path: Path) -> None:
    keyring = FakeKeyring()
    path = _run(tmp_path, keyring)
    before = path.read_bytes(), keyring.get_password(mc.KEYRING_SERVICE, "redis-password")

    def no_download(**_kwargs: Any) -> None:
        raise AssertionError("a rerun must not download")

    again = memory_setup.run_setup(tmp_path, keyring_backend=keyring, confirm=lambda _d: pytest.fail("no prompt"), download=no_download, defaults=_settings(tmp_path))
    assert again == path
    assert (path.read_bytes(), keyring.get_password(mc.KEYRING_SERVICE, "redis-password")) == before


def test_setup_needs_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launch_approval_cli.sys.stdin, "isatty", lambda: False, raising=False)
    assert launch_approval_cli.main(["memory-setup"]) != 0


def test_the_shipped_defaults_are_a_valid_configuration() -> None:
    settings = memory_setup.shipped_defaults()
    assert settings["image"].startswith("redis@sha256:")
    document = {"schema_version": 1, "resource": "optimus-memory-test", "credential_name": "n", "acl_sha256": "0" * 64,
                "image": settings["image"], "container": settings["container"], "volume": settings["volume"], "host": settings["host"],
                "port": settings["port"], "user": settings["user"], "maxmemory_mb": settings["maxmemory_mb"],
                "embedding": {k: settings["embedding"][k] for k in ("model", "source", "revision", "licence", "dimensions", "max_input_tokens", "artifact_sha256")}}
    assert mc._parse(json.dumps(document).encode()).embedding.dimensions == settings["embedding"]["dimensions"]


# --- what a launch binds ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [{"password": "secret"},  # pragma: allowlist secret - synthetic test fixture
     {"host": "10.0.0.1"}, {"image": "redis:8"}, {"resource": "BAD resource"}, {"port": 0}, {"schema_version": 2},
     {"maxmemory_mb": 1}, {"acl_sha256": "short"}, {"embedding": {"model": "x"}}],
    ids=["a-password", "remote-host", "mutable-tag", "bad-resource", "bad-port", "schema", "memory", "acl-digest", "embedding"],
)
def test_anything_but_the_documented_shape_is_refused(tmp_path: Path, change: dict[str, Any]) -> None:
    path = _run(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    document.update(change)
    path.write_text(json.dumps(document), encoding="utf-8")
    assert mc.read(path.parent)[2] is not None


def test_without_a_file_the_feature_is_off_and_nothing_is_bound(tmp_path: Path) -> None:
    assert mc.config_literal(mc.memory_index_root(tmp_path)) is None
    assert local_infra.gateway_memory_index(tmp_path, None) == (None, None)
    assert local_infra.ensure_memory_redis(mc.memory_index_root(tmp_path)).state == "off"


def test_only_the_approved_configuration_is_served(tmp_path: Path) -> None:
    path = _run(tmp_path)
    literal = mc.config_literal(path.parent)
    root, bound = local_infra.gateway_memory_index(tmp_path, literal)
    assert root == path.parent and bound == mc.memory_index_literal(path.parent, literal)
    logged: list[str] = []
    assert local_infra.gateway_memory_index(tmp_path, "memory-index-config:sha256:other", log=logged.append) == (None, None)
    assert "not the approved one" in logged[0]
    assert local_infra.gateway_memory_index(tmp_path, None) == (None, None)


def test_changing_the_configuration_changes_the_literal_a_launch_approves(tmp_path: Path) -> None:
    path = _run(tmp_path)
    before = mc.config_literal(path.parent)
    path.write_bytes(path.read_bytes() + b"\n")
    assert mc.config_literal(path.parent) != before


def _manifest(memory: str | None) -> str:
    return lm.serialize_gateway_child_manifest(lm.build_gateway_child_manifest(
        workspace_digest="a" * 64, security_snapshot_digest="b" * 64, provider="openrouter", base_url="http://127.0.0.1:9/v1", bind_host="127.0.0.1",
        bind_port=8765, provider_api_key="k", shared_secret="s", hmac_key=b"h" * 32, policy_version="P", memory_index=memory))


def _verify(serialized: str, memory: str | None) -> lm.GatewayChildManifest:
    return lm.verify_gateway_child_manifest(serialized, hmac_key=b"h" * 32, provider="openrouter", base_url="http://127.0.0.1:9/v1", provider_api_key="k",
                                            shared_secret="s", bind_host="127.0.0.1", bind_port=8765, memory_index=memory)


def test_the_manifest_binds_the_index_literal_both_ways() -> None:
    assert _verify(_manifest("literal"), "literal").memory_index == "literal"
    with pytest.raises(lm.LaunchManifestError) as raised:
        _verify(_manifest("literal"), None)
    assert raised.value.code == "MANIFEST_MEMORY_INDEX_MISMATCH"
    with pytest.raises(lm.LaunchManifestError):
        _verify(_manifest(None), "literal")


def test_a_manifest_without_an_index_keeps_its_version_and_field_set() -> None:
    document = json.loads(_manifest(None))
    assert document["schema_version"] == lm.MANIFEST_SCHEMA_VERSION and "memory_index" not in document


def _identity(memory: str | None) -> gi.GatewayIdentity:
    return gi.compose_identity(provider="openrouter", base_url="http://x", provider_api_key="k", shared_secret="s", composition=gi.COMPOSITION_STANDARD,
                               model_registry=None, stage_c_envelope=None, accounting=None, tool_environ={}, hmac_key=b"h" * 32, memory_index=memory)


def test_a_gateway_serving_another_index_is_not_compatible() -> None:
    assert gi.differing_fields(_identity("one"), _identity("two")) == ("memory_index",)
    assert gi.differing_fields(_identity(None), _identity(None)) == ()


def test_a_launch_expects_what_the_gateway_it_starts_serves_with_an_index(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The real child arguments and environment, into the real Gateway entrypoint, with no password anywhere in either."""
    keyring = FakeKeyring()
    path = _run(tmp_path, keyring)
    literal = mc.config_literal(path.parent)
    password = keyring.get_password(mc.KEYRING_SERVICE, "redis-password")
    assert password
    key = b"test-memory-setup-hmac-key-32-by"
    secret, api_key, base_url = "shared-secret-value", "sk-or-test-key", "http://127.0.0.1:9/stub/v1"  # pragma: allowlist secret - synthetic test fixture
    provenance = CredentialProvenance(CredentialLayer.ENVIRONMENT, "test")
    credentials = ProviderCredentialResolution(secrets=ProviderSecrets(provider="openrouter", model_provider_api_key=api_key, base_url=base_url),
                                               provider_provenance=provenance, api_key_provenance=provenance, base_url_provenance=provenance)
    inputs: dict[str, Any] = {"gateway_url": "http://127.0.0.1:8765", "provider_credentials": credentials, "shared_secret": secret, "manifest_hmac_key": key,
                              "system_env": {}, "config_root": tmp_path, "approved_memory_index": literal, "model_registry": trusted_approval_literal()}
    expected = local_infra.expected_gateway_identity(**inputs)
    assert expected is not None
    spawned: dict[str, Any] = {}

    class Child:
        pid = 1
        returncode = None

        def poll(self) -> None:
            return None

    def popen(args: list[str], **kwargs: Any) -> Child:
        spawned.update(argv=args[1:], env=kwargs["env"])
        return Child()

    calls = {"n": 0}

    def reachable(*_a: object, **_k: object) -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    monkeypatch.setattr(local_infra.subprocess, "Popen", popen)
    monkeypatch.setattr(local_infra, "_tcp_reachable", reachable)
    monkeypatch.setattr(local_infra, "verify_local_gateway", lambda *_a, **_k: None)
    local_infra.ensure_local_gateway(**inputs, workspace_digest="a" * 64, security_snapshot_digest="b" * 64, policy_version="P9.99-v1",
                                     runtime_root=tmp_path / "runtime", expected_identity=expected)
    assert "--memory-index-root" in spawned["argv"]
    assert password not in " ".join(spawned["argv"]) and password not in " ".join(spawned["env"].values())

    class Keyring(FakeKeyring):
        def get_password(self, service: str, name: str) -> str | None:
            if name == "hmac_integrity_key":
                return base64.urlsafe_b64encode(key).decode("ascii")
            return keyring.get_password(service, name)

    for name in ("OPTIMUS_LOCAL_GATEWAY_BIND_HOST", "OPTIMUS_LOCAL_GATEWAY_PORT", "OPTIMUS_LOCAL_GATEWAY_BASE_URL", *gi.TOOL_POLICY_NAMES):
        monkeypatch.delenv(name, raising=False)
    for name, value in spawned["env"].items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(gateway_main, "_keyring_module", Keyring())
    configs: list[Any] = []

    class Server:
        server_address = ("127.0.0.1", 8765)

        def serve_forever(self) -> None:
            raise KeyboardInterrupt

        def shutdown(self) -> None:
            return None

    monkeypatch.setattr(gateway_main, "serve_gateway", lambda *, config: configs.append(config) or Server())
    assert gateway_main.main(spawned["argv"][2:]) == 0
    assert configs[0].local_identity.identity == expected
    assert configs[0].memory_index is not None


def test_the_real_download_asks_for_exactly_the_files_the_digest_covers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Found by the first real download: every other test copies a snapshot, so none went through this filter."""
    repository_files = {name: name.encode("utf-8") for name in (
        ".gitattributes", "README.md", "config.json", "model_optimized.onnx", "ort_config.json", "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json", "vocab.txt")}
    only_the_digests_files = {name: data for name, data in repository_files.items() if name in memory_setup._ALLOWED_ARTIFACT_FILES}
    assert set(only_the_digests_files) == {"config.json", "model_optimized.onnx", "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json"}

    def snapshot_download(*, repo_id: str, revision: str, local_dir: Path, allow_patterns: list[str]) -> None:
        for name, data in repository_files.items():
            if any(fnmatch.fnmatchcase(name, pattern) for pattern in allow_patterns):
                (local_dir / name).write_bytes(data)
        (local_dir / ".cache").mkdir(exist_ok=True)  # what the hub leaves beside a local_dir download
        (local_dir / ".cache" / "marker.lock").write_bytes(b"")

    monkeypatch.setattr("huggingface_hub.snapshot_download", snapshot_download)
    target = tmp_path / "artifact"
    target.mkdir()
    memory_setup.huggingface_download(repository="r", revision="v", target=target)
    assert {path.name for path in target.iterdir() if path.is_file()} == set(only_the_digests_files)
