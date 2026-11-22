"""Plan 12.11 Task 1: the memory store's one-time setup, its approved configuration and what a launch binds. Real files; Docker,
Redis and the native keyring are proven in tests/integration/memory."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import threading
from pathlib import Path
from typing import Any

import pytest
from keyring.backends.Windows import DecodingCredential, WinVaultKeyring

import optimus_file_lock
from optimus.acp import local_infra, memory_setup
from optimus.acp.local_gateway_secrets import CredentialLayer, CredentialProvenance, ProviderCredentialResolution, ProviderSecrets
from optimus_gateway import __main__ as gateway_main
from optimus_model_policy.binding import trusted_approval_literal
from optimus_security import gateway_identity as gi
from optimus_security import launch_manifest as lm
from optimus_security import memory_index_config as mc
from optimus_security import memory_store_config as sc
from tests.unit.acp.conftest import FakeKeyring
from tests.unit.context.test_memory_recovery import LOCK_FAULTS, fault_platform_lock


def _settings(**overrides: Any) -> dict[str, Any]:
    return {"image": "redis@sha256:" + "a" * 64, "container": "test-memory-store", "volume": "test-memory-data", "host": "127.0.0.1",
            "port": 6398, "user": "optimus-memory", "maxmemory_mb": 128, "admission_ceiling_mb": 96, **overrides}


def _run(tmp_path: Path, keyring: Any = None, confirm: Any = lambda _d: True, **overrides: Any) -> Path:
    return memory_setup.run_store_setup(tmp_path, keyring_backend=keyring or FakeKeyring(), confirm=confirm, defaults=_settings(**overrides),
                                        lock_root=tmp_path)


def _stored_password(keyring: Any, path: Path) -> str | None:
    """The password under the keyring entry the written configuration names."""
    return keyring.get_password(sc.KEYRING_SERVICE, json.loads(path.read_bytes())["credential_name"])


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
    assert not keyring._store


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
    before = (path.read_bytes(), _stored_password(keyring, path))
    assert _run(tmp_path, keyring, confirm=lambda _d: pytest.fail("a configured store asks nothing")) == path
    assert (path.read_bytes(), _stored_password(keyring, path)) == before


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
    password = _stored_password(keyring, path)
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
    first, second = (sc.read(_run(tmp_path / name, keyring).parent)[1] for name in ("first", "second"))
    assert first is not None and second is not None
    assert first.credential_name != second.credential_name
    for name, config in (("first", first), ("second", second)):  # each root's password still matches its own ACL
        password = keyring.get_password(sc.KEYRING_SERVICE, config.credential_name)
        assert password and hashlib.sha256(password.encode()).hexdigest() in (sc.memory_store_root(tmp_path / name) / sc.ACL_NAME).read_text("utf-8")
    kept = keyring.get_password(sc.KEYRING_SERVICE, second.credential_name)
    keyring.delete_password(sc.KEYRING_SERVICE, first.credential_name)
    assert keyring.get_password(sc.KEYRING_SERVICE, second.credential_name) == kept
    assert keyring.get_password(sc.KEYRING_SERVICE, first.credential_name) is None


def test_a_config_with_the_legacy_shared_name_keeps_its_password(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
    from optimus_gateway import memory_store

    endpoints: list[Any] = []
    real_connect = memory_store.connect  # builds a client; nothing connects until a request
    monkeypatch.setattr(memory_store, "connect", lambda endpoint: (endpoints.append(endpoint), real_connect(endpoint))[1])
    memory_store.build_memory_store_service(config, keyring_backend=keyring, hmac_key=b"k" * 32)  # the Gateway's own reader
    assert endpoints and {endpoint.password for endpoint in endpoints} == {keyring.get_password(sc.KEYRING_SERVICE, "redis-password")}


def test_setting_up_a_root_again_after_its_configuration_moved_keeps_the_moved_password(tmp_path: Path) -> None:
    """#526 review: a configuration moved to another root keeps its entry when its old root is set up afresh."""
    keyring = FakeKeyring()
    _run(tmp_path / "old", keyring)
    (tmp_path / "new").mkdir()
    sc.memory_store_root(tmp_path / "old").rename(sc.memory_store_root(tmp_path / "new"))
    _run(tmp_path / "old", keyring)
    moved = sc.memory_store_root(tmp_path / "new") / sc.CONFIG_NAME
    password = _stored_password(keyring, moved)
    assert password and hashlib.sha256(password.encode()).hexdigest() in (moved.parent / sc.ACL_NAME).read_text("utf-8")


class _InterleavingVault(WinVaultKeyring):
    """keyring's own WinVault `set_password` and `get_password` over an in-memory vault (#529). Each vault write first waits at
    `barrier`, so two setups that are not serialized both read the service's shared slot before either writes. `log` records
    each thread's slot writes; `overlapped` is set when two writers really met at the barrier."""

    def __init__(self, barrier: threading.Barrier, log: list[tuple[str, str]]) -> None:
        super().__init__()
        self._targets: dict[str, tuple[str, str]] = {}
        self._barrier = barrier
        self._log = log
        self.overlapped = False

    def _read_credential(self, target: str) -> DecodingCredential | None:
        found = self._targets.get(target)
        return DecodingCredential(UserName=found[0], CredentialBlob=found[1].encode("utf-16")) if found else None

    def _set_password(self, target: str, username: str, password: str) -> None:
        try:
            self._barrier.wait()
            self.overlapped = True
        except threading.BrokenBarrierError:  # the other setup never arrived: it was held by the lock, or it already wrote
            pass
        self._log.append((threading.current_thread().name, "write"))
        self._targets[target] = (username, password)


def _race(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, locked: bool) -> tuple[_InterleavingVault, list[tuple[str, str]], list[bool]]:
    """Two store setups for different roots, started together, on one vault and one lock root. Returns the vault, every lock
    attempt and slot write in order, and whether each root's password still matches its own ACL."""
    from optimus.context import memory_recovery

    log: list[tuple[str, str]] = []
    vault = _InterleavingVault(threading.Barrier(2, timeout=2.0), log)
    real_lock = optimus_file_lock._lock

    def logged_lock(handle: Any) -> None:  # the one OS lock call, since #532 in optimus_file_lock
        try:
            real_lock(handle)
        except OSError:
            log.append((threading.current_thread().name, "refused"))
            raise
        log.append((threading.current_thread().name, "locked"))

    monkeypatch.setattr(optimus_file_lock, "_lock", logged_lock)
    if not locked:
        monkeypatch.setattr(memory_recovery, "_file_lock", lambda *_args, **_kwargs: contextlib.nullcontext())
    start, failures = threading.Barrier(2, timeout=10.0), []

    def setup(name: str) -> None:
        try:
            start.wait()
            memory_setup.run_store_setup(tmp_path / name, keyring_backend=vault, confirm=lambda _d: True, defaults=_settings(),
                                         lock_root=tmp_path / "runtime")
        except BaseException as exc:  # noqa: BLE001 - reported below, in the test's own thread
            failures.append(exc)

    threads = [threading.Thread(target=setup, args=(name,), name=name) for name in ("first", "second")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not failures and not any(thread.is_alive() for thread in threads)
    kept = []
    for name in ("first", "second"):
        path = sc.memory_store_root(tmp_path / name) / sc.CONFIG_NAME
        password = _stored_password(vault, path)
        kept.append(bool(password) and hashlib.sha256((password or "").encode()).hexdigest() in (path.parent / sc.ACL_NAME).read_text("utf-8"))
    return vault, log, kept


def test_unserialized_store_setups_really_overlap_and_lose_a_password(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The control for the test below: without the lock, the arranged overlap happens and keyring's backend loses one password."""
    vault, _log, kept = _race(monkeypatch, tmp_path, locked=False)
    assert vault.overlapped, "the two setups never met at the slot write, so this run proves nothing"
    assert sorted(kept) == [False, True]


def test_concurrent_store_setups_on_one_keyring_service_both_keep_their_passwords(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """#529: the Windows backend reads, then rewrites, one slot per service. Two setups that contend for it are serialized by the
    lock, so neither password is lost."""
    vault, log, kept = _race(monkeypatch, tmp_path, locked=True)
    first_write = next(index for index, (_thread, event) in enumerate(log) if event == "write")
    writer = log[first_write][0]
    assert any(event == "refused" and thread != writer for thread, event in log[:first_write]), f"no contention arranged: {log}"
    assert not vault.overlapped and kept == [True, True]


_HOLD_LOCK = """
import sys
from pathlib import Path

from optimus.context import memory_recovery

with memory_recovery._file_lock(Path(sys.argv[1])):
    print("held", flush=True)
    sys.stdin.readline()
"""


def test_another_process_holding_the_lock_keeps_a_setup_out(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """#529 review: the lock holds across processes, not only threads. While a child process holds it, setup stops before its
    keyring write; once the child lets go, the same setup completes."""
    import subprocess
    import sys

    monkeypatch.setattr(memory_setup, "_SETUP_LOCK_SECONDS", 0.2)
    keyring = FakeKeyring()
    # The child inherits this environment whole, so a census run's hook reaches it (#534 review 6).
    child = subprocess.Popen([sys.executable, "-c", _HOLD_LOCK, str(tmp_path / "locks" / memory_setup._SETUP_LOCK)], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout is not None and child.stdin is not None
        ready: list[str] = []
        reader = threading.Thread(target=lambda: ready.append(child.stdout.readline()), daemon=True)  # type: ignore[union-attr]
        reader.start()
        reader.join(30)  # bounded: a child that never takes the lock fails the test instead of hanging it
        assert ready == ["held\n"], ready
        with pytest.raises(memory_setup.MemorySetupError, match="Another memory setup"):
            _run(tmp_path, keyring)
        assert sc.config_literal(sc.memory_store_root(tmp_path)) is None and not keyring._store
        child.stdin.write("\n")
        child.stdin.flush()
        assert child.wait(timeout=30) == 0
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate()
    path = _run(tmp_path, keyring)
    assert _stored_password(keyring, path)


@pytest.mark.parametrize("number", LOCK_FAULTS)
def test_a_lock_fault_is_reported_as_itself_not_as_another_setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, number: int) -> None:
    """#529 review: only another holder's lock is retried. Any other locking failure stops setup at once with its errno."""
    fault_platform_lock(monkeypatch, number)
    monkeypatch.setattr(memory_setup, "_SETUP_LOCK_SECONDS", 30.0)  # a retried fault would wait this out
    keyring = FakeKeyring()
    with pytest.raises(memory_setup.MemorySetupError, match=rf"was not stored: The lock file memory-setup\.lock could not be taken \(errno {number}\)"):
        _run(tmp_path, keyring)
    assert sc.config_literal(sc.memory_store_root(tmp_path)) is None and not keyring._store


def test_a_failed_unlock_after_the_write_does_not_undo_the_setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """#529 review: closing the lock file releases the lock, so an unlock failure after a stored password is not a setup failure."""

    def broken_unlock(_handle: Any) -> None:
        raise OSError(5, "unlock failed")

    monkeypatch.setattr(optimus_file_lock, "_unlock", broken_unlock)
    keyring = FakeKeyring()
    path = _run(tmp_path, keyring)
    password = _stored_password(keyring, path)
    assert password and hashlib.sha256(password.encode()).hexdigest() in (path.parent / sc.ACL_NAME).read_text("utf-8")


@pytest.mark.parametrize("store", [True, False])
def test_memory_setup_from_the_terminal_locks_in_the_per_user_runtime_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, store: bool) -> None:
    """#529: every config root's setup must take one lock, so the command passes the per-user runtime root, never the config root."""
    from types import SimpleNamespace

    from optimus.acp import launch_approval_cli
    from optimus.acp.trusted_paths import TrustedOperatorRoots

    roots = TrustedOperatorRoots(default_config_root=tmp_path / "roaming", approval_runtime_root=tmp_path / "runtime")
    paths = SimpleNamespace(config_root=tmp_path / "config")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(launch_approval_cli, "_require_tty", lambda: None)
    monkeypatch.setattr(launch_approval_cli, "_prepare_candidate_context", lambda _workspace: (None, paths))
    monkeypatch.setattr(launch_approval_cli, "resolve_trusted_operator_roots", lambda **_kwargs: roots)
    record = lambda config_root, **kwargs: (seen.update(config_root=config_root, **kwargs), tmp_path / "configured")[1]  # noqa: E731
    monkeypatch.setattr(memory_setup, "run_store_setup" if store else "run_setup", record)
    assert launch_approval_cli._cmd_memory_setup(tmp_path, store=store) == 0
    assert seen["config_root"] == paths.config_root and seen["lock_root"] == roots.approval_runtime_root


def test_a_setup_that_cannot_take_the_lock_configures_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """#529: while another setup holds the lock, this one stops before its keyring write and writes no configuration."""
    from optimus.context import memory_recovery

    keyring = FakeKeyring()
    monkeypatch.setattr(memory_setup, "_SETUP_LOCK_SECONDS", 0.05)
    with memory_recovery._file_lock(tmp_path / "locks" / memory_setup._SETUP_LOCK):
        with pytest.raises(memory_setup.MemorySetupError, match="Another memory setup"):
            _run(tmp_path, keyring)
    assert sc.config_literal(sc.memory_store_root(tmp_path)) is None and not keyring._store
