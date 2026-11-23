"""Seam 2, checkpoint B round 2 (R1): the operator verifier's Redis custody spans its whole lifetime.

The verifier acquires a runtime through the store convenience factory. Every failure after
that point -- building the subprocess environment, launching the child, a failing session
or process cleanup -- must still close that runtime, and the original failure must survive.
"""

from __future__ import annotations

from functools import partial
from unittest.mock import create_autospec

import pytest

from optimus.acp import operator_verify, subprocess_env
from optimus.acp.ndjson_subprocess_session import NdjsonSubprocessSession
from optimus.redis.async_bridge import RedisLoopOwner
from optimus.redis.runtime import CloseablePool, RedisRuntime, RedisRuntimeState, RuntimeClient
from tests.support.contract_doubles import new_contract_call_log


class _Resource:
    def __init__(self) -> None:
        self.count = 0

    async def aclose(self) -> None:
        self.count += 1


def _runtime() -> tuple[RedisRuntime, _Resource, _Resource]:
    client, pool = _Resource(), _Resource()
    checked_client = create_autospec(RuntimeClient, instance=True, spec_set=True)
    checked_client.aclose.side_effect = client.aclose
    checked_pool = create_autospec(CloseablePool, instance=True, spec_set=True)
    checked_pool.aclose.side_effect = pool.aclose
    return RedisRuntime(pool=checked_pool, client=checked_client, owner=RedisLoopOwner(name="seam2b-verify-owner")), client, pool


def _store_for(monkeypatch, runtime: RedisRuntime):
    from optimus.agent.state_store import AsyncRedisAgentStateStore, RedisAgentStateStore

    store = RedisAgentStateStore(
        async_store=AsyncRedisAgentStateStore(client=runtime.client), submit=runtime.run_sync, owned_runtime=runtime
    )
    monkeypatch.setattr(operator_verify.RedisAgentStateStore, "from_url", create_autospec(operator_verify.RedisAgentStateStore.from_url, return_value=store))
    return store


def _config(tmp_path) -> operator_verify.OperatorLiveSessionConfig:
    return operator_verify.OperatorLiveSessionConfig(
        workspace_root=tmp_path, repository_root=tmp_path, model="glm-5.2",
        task="Offline custody control", transcript_path=tmp_path / "transcript.ndjson", wall_clock_timeout_seconds=1,
    )


def _checked_session_factory(script_type):
    constructor = create_autospec(NdjsonSubprocessSession, spec_set=True)
    def build(*args, **kwargs):
        script = script_type(*args, **kwargs)
        checked = create_autospec(NdjsonSubprocessSession, instance=True, spec_set=True)
        calls = new_contract_call_log("NdjsonSubprocessSession")
        for name in ("send", "wait_for_response", "close_stdin", "terminate"):
            getattr(checked, name).side_effect = partial(calls.reject, name)
            if hasattr(script, name):
                getattr(checked, name).side_effect = getattr(script, name)
        return checked
    constructor.side_effect = build
    return constructor


def test_a_projection_failure_before_the_subprocess_closes_the_store_runtime(monkeypatch, tmp_path):
    """R1 MUTATION: the runtime was acquired before the protected region began."""
    runtime, client, pool = _runtime()
    _store_for(monkeypatch, runtime)
    env = {"OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0", "PATH": "one", "Path": "two"}
    monkeypatch.setattr(operator_verify, "apply_local_defaults", lambda environ, **kw: env)

    # Force the REAL Windows folding rules on either platform: conflicting PATH spellings
    # are refused by the genuine projection, before any subprocess exists.
    monkeypatch.setattr(subprocess_env, "_windows_semantics_default", lambda: True)
    monkeypatch.setattr(
        operator_verify.process_tree, "popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no subprocess"))
    )

    with pytest.raises(subprocess_env.SubprocessEnvConfigurationError):
        operator_verify.run_operator_live_session(_config(tmp_path), environ=env, transcript=None)
    assert runtime.state is RedisRuntimeState.CLOSED
    assert client.count == 1 and pool.count == 1
    assert runtime.owner.is_terminated


def test_a_failing_session_cleanup_still_closes_the_store_runtime_and_keeps_the_first_error(monkeypatch, tmp_path):
    runtime, client, pool = _runtime()
    _store_for(monkeypatch, runtime)
    env = {"OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0"}
    monkeypatch.setattr(operator_verify, "apply_local_defaults", lambda environ, **kw: env)
    monkeypatch.setattr(operator_verify, "build_acp_subprocess_env", lambda *, operator_environ: dict(operator_environ))

    class _Process:
        def poll(self):
            return 0

    class _Session:
        def __init__(self, *, process, transcript) -> None:
            pass

        def send(self, message):
            raise RuntimeError("child rejected the first message")

        def close_stdin(self):
            raise OSError("stdin already closed")

        def terminate(self):
            return None

    monkeypatch.setattr(operator_verify.process_tree, "popen", lambda *a, **k: _Process())
    monkeypatch.setattr(operator_verify, "NdjsonSubprocessSession", _checked_session_factory(_Session))

    with pytest.raises(RuntimeError, match="child rejected the first message") as exc_info:
        operator_verify.run_operator_live_session(_config(tmp_path), environ=env, transcript=None)
    assert runtime.state is RedisRuntimeState.CLOSED
    assert client.count == 1 and pool.count == 1
    assert any("stdin already closed" in note for note in getattr(exc_info.value, "__notes__", []))


def test_a_failed_session_start_stops_the_whole_tree_and_preserves_the_primary_failure(monkeypatch, tmp_path):
    runtime, client, pool = _runtime()
    _store_for(monkeypatch, runtime)
    env = {"OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0"}
    monkeypatch.setattr(operator_verify, "apply_local_defaults", lambda environ, **kw: env)
    monkeypatch.setattr(operator_verify, "build_acp_subprocess_env", lambda *, operator_environ: dict(operator_environ))
    process = object()
    primary = ValueError("session setup failure")
    cleanup_calls = []

    def fail_session(*, process, transcript):
        raise primary

    def stop_tree(child, *, deadline):
        cleanup_calls.append(child)
        raise operator_verify.process_tree.PipeCleanupError("root process reap unconfirmed")

    monkeypatch.setattr(operator_verify.process_tree, "popen", lambda *a, **k: process)
    monkeypatch.setattr(operator_verify, "NdjsonSubprocessSession", fail_session)
    monkeypatch.setattr(operator_verify.process_tree, "stop_piped_process", stop_tree)
    with pytest.raises(ValueError) as exc_info:
        operator_verify.run_operator_live_session(_config(tmp_path), environ=env, transcript=None)
    assert exc_info.value is primary
    assert cleanup_calls == [process]
    assert any("root process reap unconfirmed" in note for note in primary.__notes__)
    assert runtime.state is RedisRuntimeState.CLOSED
    assert client.count == 1 and pool.count == 1
    assert runtime.owner.is_terminated


def test_cleanup_failure_prevents_an_ordinary_result_after_the_runtime_closes(monkeypatch, tmp_path):
    runtime, client, pool = _runtime()
    _store_for(monkeypatch, runtime)
    env = {"OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0"}
    monkeypatch.setattr(operator_verify, "apply_local_defaults", lambda environ, **kw: env)
    monkeypatch.setattr(operator_verify, "build_acp_subprocess_env", lambda *, operator_environ: dict(operator_environ))

    class _Session:
        def __init__(self, *, process, transcript):
            pass

        def send(self, message):
            return None

        def wait_for_response(self, request_id, *, deadline):
            return {"result": {}}

        def close_stdin(self):
            return None

        def terminate(self):
            raise operator_verify.LiveSessionError("ACP subprocess cleanup incomplete")

    monkeypatch.setattr(operator_verify.process_tree, "popen", lambda *a, **k: object())
    monkeypatch.setattr(operator_verify, "NdjsonSubprocessSession", _checked_session_factory(_Session))
    with pytest.raises(operator_verify.LiveSessionError, match="ACP subprocess cleanup incomplete"):
        operator_verify.run_operator_live_session(_config(tmp_path), environ=env, transcript=None)
    assert runtime.state is RedisRuntimeState.CLOSED
    assert client.count == 1 and pool.count == 1
    assert runtime.owner.is_terminated


def test_a_store_that_owns_no_runtime_is_refused_before_anything_is_launched(monkeypatch, tmp_path):
    """Fail closed: the factory contract is an OWNING store; a borrowed seam cannot be closed here."""
    runtime, _client, _pool = _runtime()
    borrowed = runtime.sync_state_store()
    monkeypatch.setattr(operator_verify.RedisAgentStateStore, "from_url", create_autospec(operator_verify.RedisAgentStateStore.from_url, return_value=borrowed))
    launched: list[int] = []
    monkeypatch.setattr(operator_verify.process_tree, "popen", lambda *a, **k: launched.append(1))
    env = {"OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0"}
    monkeypatch.setattr(operator_verify, "apply_local_defaults", lambda environ, **kw: env)
    try:
        with pytest.raises(RuntimeError, match="requires the owning store"):
            operator_verify.run_operator_live_session(_config(tmp_path), environ=env, transcript=None)
        assert launched == []
    finally:
        runtime.close(timeout=5.0)


@pytest.mark.parametrize("operation", ["_plan_keys_for_run", "_delete_plan_keys"])
def test_sync_store_verification_refuses_without_scan_or_delete(operation):
    from optimus.acp import operator_verify
    from optimus.agent.state_store import RedisAgentStateStore

    effects = []

    class SyncClient:
        def scan_iter(self, **_kwargs):
            effects.append("scan")
            pytest.fail("sync verification must refuse before scanning")

        def delete(self, _key):
            effects.append("delete")
            pytest.fail("sync verification must refuse before deleting")

    store = RedisAgentStateStore(client=SyncClient())
    with pytest.raises(RuntimeError, match="^this store has no owner submission seam; it wraps a synchronous client$"):
        getattr(operator_verify, operation)(store, "offline-run")
    assert effects == []


def test_contract_operator_configuration_is_real_model(tmp_path):
    config = _config(tmp_path)
    assert isinstance(config, operator_verify.OperatorLiveSessionConfig)
    assert config.repository_root == tmp_path
    assert config.task
    assert config.transcript_path.parent == tmp_path


def test_contract_ndjson_session_rejects_drift_and_preserves_send():
    sent = []
    class Script:
        def __init__(self, *, process, transcript):
            pass
        def send(self, message):
            sent.append(message)
    factory = _checked_session_factory(Script)
    with pytest.raises(TypeError):
        factory(obsolete_process=object(), transcript=None)
    session = factory(process=object(), transcript=None)
    with pytest.raises(AttributeError):
        session.unknown_session_operation = True
    with pytest.raises(TypeError):
        session.send(payload={})
    session.send({"id": 1})
    assert sent == [{"id": 1}]
