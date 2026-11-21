"""Plan 12.11 Task 1: the memory store's one-time setup, its approved configuration and what a launch binds. Real files; Docker,
Redis and the native keyring are proven in tests/integration/memory."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from optimus.acp import local_infra, memory_setup
from optimus.acp.local_gateway_secrets import CredentialLayer, CredentialProvenance, ProviderCredentialResolution, ProviderSecrets
from optimus_gateway import __main__ as gateway_main
from optimus_model_policy.binding import trusted_approval_literal
from optimus_security import gateway_identity as gi
from optimus_security import launch_manifest as lm
from optimus_security import memory_index_config as mc
from optimus_security import memory_store_config as sc
from tests.unit.acp.conftest import FakeKeyring


def _settings(**overrides: Any) -> dict[str, Any]:
    return {"image": "redis@sha256:" + "a" * 64, "container": "test-memory-store", "volume": "test-memory-data", "host": "127.0.0.1",
            "port": 6398, "user": "optimus-memory", "maxmemory_mb": 128, "admission_ceiling_mb": 96, **overrides}


def _run(tmp_path: Path, keyring: Any = None, confirm: Any = lambda _d: True, **overrides: Any) -> Path:
    return memory_setup.run_store_setup(tmp_path, keyring_backend=keyring or FakeKeyring(), confirm=confirm, defaults=_settings(**overrides))


def test_store_setup_writes_only_non_secret_files_and_the_keyring_holds_the_password(tmp_path: Path) -> None:
    keyring = FakeKeyring()
    path = _run(tmp_path, keyring)
    root = path.parent
    literal, config, refusal = sc.read(root)
    assert refusal is None and config is not None and literal is not None
    password = keyring.get_password(sc.KEYRING_SERVICE, config.credential_name)
    assert password
    for file in root.rglob("*"):
        if file.is_file():
            assert password.encode() not in file.read_bytes(), file
    assert password not in sc.memory_store_literal(root, literal)
    assert "user default off" in (root / sc.ACL_NAME).read_text(encoding="utf-8")


def test_store_setup_opens_only_the_memory_key_pattern_and_named_commands(tmp_path: Path) -> None:
    acl = (_run(tmp_path).parent / sc.ACL_NAME).read_text(encoding="utf-8")
    assert "~omem:*" in acl and "~oidx:" not in acl and "-@all" in acl and "+@all" not in acl
    for forbidden in ("+eval", "+flushall", "+flushdb", "+config", "+debug", "+keys", "+module", "+acl", "+shutdown"):
        assert forbidden not in acl.split(), forbidden
    assert "+waitaof" in acl.split() and "+xadd" in acl.split()


def test_the_store_has_its_own_keyring_namespace_and_resource() -> None:
    assert sc.KEYRING_SERVICE != mc.KEYRING_SERVICE and sc.SECURITY_LITERAL_NAME != mc.SECURITY_LITERAL_NAME
    assert sc.KEY_PATTERN != mc.KEY_PATTERN


def test_a_declined_store_setup_changes_nothing(tmp_path: Path) -> None:
    keyring = FakeKeyring()
    with pytest.raises(memory_setup.MemorySetupError):
        _run(tmp_path, keyring, confirm=lambda _d: False)
    assert not sc.memory_store_root(tmp_path).exists()
    assert keyring.get_password(sc.KEYRING_SERVICE, memory_setup.credential_name(sc.memory_store_root(tmp_path))) is None


def test_the_description_names_the_resource_and_the_single_copy_risk(tmp_path: Path) -> None:
    described: list[str] = []
    _run(tmp_path, confirm=lambda d: (described.append(d), True)[1])
    assert "test-memory-store" in described[0] and "6398" in described[0] and sc.KEYRING_SERVICE in described[0]
    assert "losing the volume loses it" in described[0] and "Nothing is downloaded" in described[0]


def test_a_keyring_failure_configures_nothing(tmp_path: Path) -> None:
    class Refusing(FakeKeyring):
        def set_password(self, service: str, name: str, value: str) -> None:
            raise RuntimeError("locked")

    with pytest.raises(memory_setup.MemorySetupError):
        _run(tmp_path, Refusing())
    assert sc.config_literal(sc.memory_store_root(tmp_path)) is None


def _unavailable_path(tmp_path: Path, backend: Any) -> None:
    """With no usable OS keyring, setup configures nothing, and a Gateway reading that keyring for a configured store says the
    password is missing (plan v5: CI without Secret Service proves the unavailable path)."""
    import time

    from optimus_gateway import memory_store
    from optimus_security import memory_store_contract as msc

    with pytest.raises(memory_setup.MemorySetupError, match="nothing was configured"):
        _run(tmp_path / "unavailable", backend)
    assert sc.config_literal(sc.memory_store_root(tmp_path / "unavailable")) is None
    _literal, config, _refusal = sc.read(_run(tmp_path / "configured").parent)
    assert config is not None
    service = memory_store.build_memory_store_service(config, keyring_backend=backend, hmac_key=b"k" * 32)
    assert service.handle(b'{"op":"capabilities"}', deadline=time.monotonic() + 1) == (503, msc.error_body("MEMORY_STORE_CREDENTIAL_MISSING"))


def test_the_keyring_librarys_no_backend_configures_nothing(tmp_path: Path) -> None:
    from keyring.backends import fail

    _unavailable_path(tmp_path, fail.Keyring())


def test_a_host_whose_os_keyring_is_unavailable_configures_nothing(tmp_path: Path) -> None:
    """The real `keyring` module as the host resolves it. Runs where the platform offers no keyring (Linux CI has no Secret
    Service); never on a host with a real one, where it would write."""
    import keyring
    from keyring.backends import fail

    if not isinstance(keyring.get_keyring(), fail.Keyring):
        pytest.skip(f"this host has an OS keyring ({type(keyring.get_keyring()).__name__}); tests/integration/memory qualifies it")
    _unavailable_path(tmp_path, keyring)


def test_a_rerun_never_replaces_a_working_password(tmp_path: Path) -> None:
    keyring = FakeKeyring()
    path = _run(tmp_path, keyring)
    before = (path.read_bytes(), keyring.get_password(sc.KEYRING_SERVICE, memory_setup.credential_name(sc.memory_store_root(tmp_path))))
    assert _run(tmp_path, keyring, confirm=lambda _d: pytest.fail("a configured store asks nothing")) == path
    assert (path.read_bytes(), keyring.get_password(sc.KEYRING_SERVICE, memory_setup.credential_name(sc.memory_store_root(tmp_path)))) == before


def test_store_setup_leaves_the_index_untouched_and_index_setup_leaves_the_store(tmp_path: Path) -> None:
    _run(tmp_path)
    assert not mc.memory_index_root(tmp_path).exists()
    assert local_infra.gateway_memory_index(tmp_path, None) == (None, None)


def test_the_shipped_store_defaults_are_a_valid_configuration() -> None:
    settings = memory_setup.shipped_store_defaults()
    assert settings["image"].startswith("redis@sha256:") and settings["port"] == 6394
    document = {"schema_version": 1, "resource": "optimus-memory-store-test", "credential_name": "n", "acl_sha256": "0" * 64, **settings}
    config = sc._parse(json.dumps(document).encode())
    assert config.admission_ceiling_mb < config.maxmemory_mb


@pytest.mark.parametrize(
    "change",
    [{"password": "secret"},  # pragma: allowlist secret - synthetic test fixture
     {"host": "10.0.0.1"}, {"image": "redis:8"}, {"resource": "BAD resource"}, {"port": 0}, {"schema_version": 2},
     {"maxmemory_mb": 1}, {"admission_ceiling_mb": 128}, {"admission_ceiling_mb": 0}, {"acl_sha256": "short"}],
    ids=["a-password", "remote-host", "mutable-tag", "bad-resource", "bad-port", "schema", "memory", "no-reserve", "no-ceiling", "acl-digest"],
)
def test_anything_but_the_documented_shape_is_refused(tmp_path: Path, change: dict[str, Any]) -> None:
    path = _run(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    document.update(change)
    path.write_text(json.dumps(document), encoding="utf-8")
    assert sc.read(path.parent)[2] is not None


def test_without_a_file_the_store_is_off_and_nothing_is_bound(tmp_path: Path) -> None:
    assert sc.config_literal(sc.memory_store_root(tmp_path)) is None
    assert local_infra.gateway_memory_store(tmp_path, None) == (None, None)
    assert local_infra.ensure_memory_store_redis(sc.memory_store_root(tmp_path)).state == "off"


def test_only_the_approved_store_configuration_is_served(tmp_path: Path) -> None:
    path = _run(tmp_path)
    literal = sc.config_literal(path.parent)
    assert literal is not None and literal.startswith("memory-store-config:sha256:")
    root, bound = local_infra.gateway_memory_store(tmp_path, literal)
    assert root == path.parent and bound == sc.memory_store_literal(path.parent, literal)
    logged: list[str] = []
    assert local_infra.gateway_memory_store(tmp_path, "memory-store-config:sha256:other", log=logged.append) == (None, None)
    assert "not the approved one" in logged[0]
    assert local_infra.gateway_memory_store(tmp_path, None) == (None, None)


def test_a_swapped_acl_file_is_a_conflict_before_docker(tmp_path: Path) -> None:
    path = _run(tmp_path)
    (path.parent / sc.ACL_NAME).write_text("user default on nopass ~* +@all\n", encoding="utf-8")
    status = local_infra.ensure_memory_store_redis(path.parent)
    assert status.state == "conflict" and "ACL" in status.detail


def _manifest(store: str | None, index: str | None = None) -> str:
    return lm.serialize_gateway_child_manifest(lm.build_gateway_child_manifest(
        workspace_digest="a" * 64, security_snapshot_digest="b" * 64, provider="openrouter", base_url="http://127.0.0.1:9/v1", bind_host="127.0.0.1",
        bind_port=8765, provider_api_key="k", shared_secret="s", hmac_key=b"h" * 32, policy_version="P", memory_index=index, memory_store=store))


def _verify(serialized: str, store: str | None, index: str | None = None) -> lm.GatewayChildManifest:
    return lm.verify_gateway_child_manifest(serialized, hmac_key=b"h" * 32, provider="openrouter", base_url="http://127.0.0.1:9/v1", provider_api_key="k",
                                            shared_secret="s", bind_host="127.0.0.1", bind_port=8765, memory_index=index, memory_store=store)


def test_the_manifest_binds_the_store_literal_both_ways() -> None:
    assert _verify(_manifest("literal"), "literal").memory_store == "literal"
    for signed, served in (("literal", None), (None, "literal"), ("literal", "other")):
        with pytest.raises(lm.LaunchManifestError) as raised:
            _verify(_manifest(signed), served)
        assert raised.value.code == "MANIFEST_MEMORY_STORE_MISMATCH"


def test_the_store_and_index_literals_are_bound_independently() -> None:
    both = _verify(_manifest("store", "index"), "store", "index")
    assert (both.memory_store, both.memory_index) == ("store", "index")
    assert both.schema_version == lm.MANIFEST_SCHEMA_VERSION + lm.MANIFEST_MEMORY_INDEX_VERSION_OFFSET + lm.MANIFEST_MEMORY_STORE_VERSION_OFFSET
    with pytest.raises(lm.LaunchManifestError):
        _verify(_manifest("store", "index"), "index", "store")


def test_a_manifest_without_a_store_keeps_its_version_and_field_set() -> None:
    document = json.loads(_manifest(None))
    assert document["schema_version"] == lm.MANIFEST_SCHEMA_VERSION and "memory_store" not in document


def test_a_store_field_with_the_wrong_version_is_corrupt() -> None:
    document = json.loads(_manifest("literal"))
    document["schema_version"] = lm.MANIFEST_SCHEMA_VERSION
    with pytest.raises(lm.LaunchManifestError) as raised:
        _verify(json.dumps(document), "literal")
    assert raised.value.code == "MANIFEST_CORRUPT"


def _identity(store: str | None) -> gi.GatewayIdentity:
    return gi.compose_identity(provider="openrouter", base_url="http://x", provider_api_key="k", shared_secret="s", composition=gi.COMPOSITION_STANDARD,
                               model_registry=None, stage_c_envelope=None, accounting=None, tool_environ={}, hmac_key=b"h" * 32, memory_store=store)


def test_a_gateway_serving_another_store_is_not_compatible() -> None:
    assert gi.differing_fields(_identity("one"), _identity("two")) == ("memory_store",)
    assert gi.differing_fields(_identity("one"), _identity(None)) == ("memory_store",)
    assert gi.differing_fields(_identity(None), _identity(None)) == ()
    assert gi.FIELD_LABELS["memory_store"] == "memory store"


# Plan 12.10's identity (main at 71d1c1e) for these inputs: a launch without a store must keep it byte for byte.
_BASELINE_DIGEST = "1fb4d21165100a912a9f6db3262bfbd542ff1bf2a5281eecb758a4cd5eb1b5e0"  # pragma: allowlist secret
_BASELINE_FIELDS = ["accounting", "composition", "gateway_key", "memory_index", "provider", "registry", "stage_c", "tool_policy", "upstream",
                    "upstream_credential"]


def _baseline_inputs(**extra: Any) -> gi.GatewayIdentity:
    return gi.compose_identity(provider="openrouter", base_url="https://upstream.test/api/v1/", provider_api_key="upstream-key",  # pragma: allowlist secret
                               shared_secret="gateway-key", composition="ordinary", model_registry="registry:x", stage_c_envelope=None,  # pragma: allowlist secret
                               accounting="accounting:y", tool_environ={}, hmac_key=b"k" * 32, memory_index="index:z", **extra)


def test_without_a_store_the_identity_is_the_one_before_plan_12_11() -> None:
    identity = _baseline_inputs()
    assert sorted(identity.fields) == _BASELINE_FIELDS and identity.digest == _BASELINE_DIGEST
    assert _baseline_inputs(memory_store=None).digest == _BASELINE_DIGEST


def _reply(identity: gi.GatewayIdentity, nonce: str = "n" * 32) -> dict[str, Any]:
    return gi.ServedIdentity(identity, gi.proof_key(b"k" * 32)).reply(nonce)


def test_a_reply_without_the_store_field_is_read_and_only_matches_a_launch_without_a_store() -> None:
    old = gi.read_reply(_reply(_baseline_inputs()), nonce="n" * 32, hmac_key=b"k" * 32)
    assert gi.differing_fields(_baseline_inputs(), old) == ()
    assert gi.differing_fields(_baseline_inputs(memory_store="store:1"), old) == ("memory_store",)
    new = gi.read_reply(_reply(_baseline_inputs(memory_store="store:1")), nonce="n" * 32, hmac_key=b"k" * 32)
    assert gi.differing_fields(_baseline_inputs(), new) == ("memory_store",)


def test_a_reply_missing_a_required_field_or_carrying_an_unknown_one_is_refused() -> None:
    for change in ({"drop": "memory_index"}, {"add": "workspace"}):
        reply = _reply(_baseline_inputs())
        fields = dict(reply["fields"])
        if "drop" in change:
            fields.pop(change["drop"])
        else:
            fields[change["add"]] = "0" * 64
        with pytest.raises(gi.IdentityReplyError):
            gi.read_reply({**reply, "fields": fields}, nonce="n" * 32, hmac_key=b"k" * 32)


def test_a_launch_expects_what_the_gateway_it_starts_serves_with_a_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The real child arguments and environment, into the real Gateway entrypoint, with no password anywhere in either."""
    keyring = FakeKeyring()
    path = _run(tmp_path, keyring)
    literal = sc.config_literal(path.parent)
    password = keyring.get_password(sc.KEYRING_SERVICE, memory_setup.credential_name(sc.memory_store_root(tmp_path)))
    assert password
    key = b"test-memory-store-hmac-key-32-by"
    secret, api_key, base_url = "shared-secret-value", "sk-or-test-key", "http://127.0.0.1:9/stub/v1"  # pragma: allowlist secret - synthetic test fixture
    provenance = CredentialProvenance(CredentialLayer.ENVIRONMENT, "test")
    credentials = ProviderCredentialResolution(secrets=ProviderSecrets(provider="openrouter", model_provider_api_key=api_key, base_url=base_url),
                                               provider_provenance=provenance, api_key_provenance=provenance, base_url_provenance=provenance)
    inputs: dict[str, Any] = {"gateway_url": "http://127.0.0.1:8765", "provider_credentials": credentials, "shared_secret": secret, "manifest_hmac_key": key,
                              "system_env": {}, "config_root": tmp_path, "approved_memory_store": literal, "model_registry": trusted_approval_literal()}
    expected = local_infra.expected_gateway_identity(**inputs)
    assert expected is not None
    without = local_infra.expected_gateway_identity(**{**inputs, "approved_memory_store": None})
    assert without is not None and gi.differing_fields(expected, without) == ("memory_store",)
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
    assert "--memory-store-root" in spawned["argv"] and "--memory-index-root" not in spawned["argv"]
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

    monkeypatch.setattr(gateway_main, "serve_gateway", lambda *, config: (configs.append(config), Server())[1])
    assert gateway_main.main(spawned["argv"][2:]) == 0
    assert configs[0].local_identity.identity == expected
    assert configs[0].memory_store is not None and configs[0].memory_index is None


def test_a_gateway_given_an_unsigned_store_root_refuses_to_start(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A store root the manifest does not bind is refused, so a swapped configuration cannot be served."""
    path = _run(tmp_path)
    key = b"test-memory-store-hmac-key-32-by"
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "openrouter")
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "s")
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "k")
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_BASE_URL", "http://127.0.0.1:9/v1")

    class Keyring(FakeKeyring):
        def get_password(self, service: str, name: str) -> str | None:
            return base64.urlsafe_b64encode(key).decode("ascii") if name == "hmac_integrity_key" else None

    monkeypatch.setattr(gateway_main, "_keyring_module", Keyring())
    manifest = lm.serialize_gateway_child_manifest(lm.build_gateway_child_manifest(
        workspace_digest="a" * 64, security_snapshot_digest="b" * 64, provider="openrouter", base_url="http://127.0.0.1:9/v1", bind_host="127.0.0.1",
        bind_port=8765, provider_api_key="k", shared_secret="s", hmac_key=key, policy_version="P", model_registry=trusted_approval_literal()))
    argv =["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", manifest, "--memory-store-root", str(path.parent)]
    assert gateway_main.main(argv) == 2
    assert "MANIFEST_MEMORY_STORE_MISMATCH" in capsys.readouterr().err


def test_each_config_root_keeps_its_own_password(tmp_path: Path) -> None:
    """#526: two config roots on one machine must not share one keyring entry, and removing one leaves the other."""
    keyring = FakeKeyring()
    configs = [sc.read(_run(tmp_path / name, keyring).parent)[1] for name in ("first", "second")]
    assert configs[0] is not None and configs[1] is not None
    first, second = configs
    assert first.credential_name != second.credential_name
    for name, config in (("first", first), ("second", second)):  # each root's password still matches its own ACL
        password = keyring.get_password(sc.KEYRING_SERVICE, config.credential_name)
        assert password and hashlib.sha256(password.encode()).hexdigest() in (sc.memory_store_root(tmp_path / name) / sc.ACL_NAME).read_text("utf-8")
    kept = keyring.get_password(sc.KEYRING_SERVICE, second.credential_name)
    keyring.delete_password(sc.KEYRING_SERVICE, first.credential_name)
    assert keyring.get_password(sc.KEYRING_SERVICE, second.credential_name) == kept


def test_a_config_with_the_legacy_shared_name_keeps_its_password(tmp_path: Path) -> None:
    """A store set up before #526 names `redis-password`; it is read as written and a rerun migrates nothing."""
    keyring = FakeKeyring()
    path = _run(tmp_path, keyring)
    document = json.loads(path.read_bytes())
    keyring.set_password(sc.KEYRING_SERVICE, "redis-password", keyring.get_password(sc.KEYRING_SERVICE, document["credential_name"]) or "")
    keyring.delete_password(sc.KEYRING_SERVICE, document["credential_name"])
    path.write_text(json.dumps({**document, "credential_name": "redis-password"}, indent=2, sort_keys=True), encoding="utf-8")
    before = path.read_bytes(), dict(keyring._store)
    assert _run(tmp_path, keyring, confirm=lambda _d: pytest.fail("a configured store asks nothing")) == path
    _literal, config, _refusal = sc.read(path.parent)
    assert config is not None and config.credential_name == "redis-password"
    assert (path.read_bytes(), keyring._store) == before and keyring.get_password(sc.KEYRING_SERVICE, "redis-password")
