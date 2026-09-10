"""Seam 2, checkpoint B round 2 (R1): the operator verifier's Redis custody spans its whole lifetime.

The verifier acquires a runtime through the store convenience factory. Every failure after
that point -- building the subprocess environment, launching the child, a failing session
or process cleanup -- must still close that runtime, and the original failure must survive.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from optimus.acp import operator_verify, subprocess_env
from optimus.redis.async_bridge import RedisLoopOwner
from optimus.redis.runtime import RedisRuntime, RedisRuntimeState


class _Resource:
    def __init__(self) -> None:
        self.count = 0

    async def aclose(self) -> None:
        self.count += 1


def _runtime() -> tuple[RedisRuntime, _Resource, _Resource]:
    client, pool = _Resource(), _Resource()
    return RedisRuntime(pool=pool, client=client, owner=RedisLoopOwner(name="seam2b-verify-owner")), client, pool


def _store_for(monkeypatch, runtime: RedisRuntime):
    from optimus.agent.state_store import AsyncRedisAgentStateStore, RedisAgentStateStore

    store = RedisAgentStateStore(
        async_store=AsyncRedisAgentStateStore(client=runtime.client), submit=runtime.run_sync, owned_runtime=runtime
    )
    monkeypatch.setattr(operator_verify.RedisAgentStateStore, "from_url", staticmethod(lambda url, **kw: store))
    return store


def _config(tmp_path) -> SimpleNamespace:
    return SimpleNamespace(workspace_root=tmp_path, wall_clock_timeout_seconds=1, model="glm-5.2")


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
        operator_verify.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no subprocess"))
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

    monkeypatch.setattr(operator_verify.subprocess, "Popen", lambda *a, **k: _Process())
    monkeypatch.setattr(operator_verify, "NdjsonSubprocessSession", _Session)

    with pytest.raises(RuntimeError, match="child rejected the first message") as exc_info:
        operator_verify.run_operator_live_session(_config(tmp_path), environ=env, transcript=None)
    assert runtime.state is RedisRuntimeState.CLOSED
    assert client.count == 1 and pool.count == 1
    assert any("stdin already closed" in note for note in getattr(exc_info.value, "__notes__", []))


def _launch_child_whose_status_query_fails(monkeypatch, *, send_error: BaseException | None):
    env = {"OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0"}
    monkeypatch.setattr(operator_verify, "apply_local_defaults", lambda environ, **kw: env)
    monkeypatch.setattr(operator_verify, "build_acp_subprocess_env", lambda *, operator_environ: dict(operator_environ))
    killed: list[int] = []

    class _Process:
        def poll(self):
            raise OSError("process status query failed")

        @property
        def kill(self):
            # Reached only because the unanswerable status query assumed the child was
            # still running. Raising on ATTRIBUTE ACCESS models the reviewer's control: a
            # finalizer that evaluates `process.kill` outside its stage lets this escape.
            killed.append(1)
            raise OSError("kill unavailable")

        def wait(self, timeout=None):
            return 0

    class _Session:
        def __init__(self, *, process, transcript) -> None:
            pass

        def send(self, message):
            if send_error is not None:
                raise send_error
            return None

        def wait_for_response(self, request_id, *, deadline):
            # A well-formed but incomplete initialize reply: the verifier returns its
            # ordinary failure RESULT, so no exception is propagating when cleanup runs.
            return {"result": {}}

        def close_stdin(self):
            return None

        def terminate(self):
            return None

    monkeypatch.setattr(operator_verify.subprocess, "Popen", lambda *a, **k: _Process())
    monkeypatch.setattr(operator_verify, "NdjsonSubprocessSession", _Session)
    return env, killed


def test_a_failing_process_status_query_never_skips_the_runtime_close_nor_replaces_the_primary_error(
    monkeypatch, tmp_path
):
    """R8 MUTATION: `process.poll()` ran outside the protected stages -- its OSError replaced the
    primary error and the owning runtime was left OPEN with its resources unclosed."""
    runtime, client, pool = _runtime()
    _store_for(monkeypatch, runtime)
    primary = ValueError("primary operation failure")
    env, killed = _launch_child_whose_status_query_fails(monkeypatch, send_error=primary)

    with pytest.raises(ValueError) as exc_info:
        operator_verify.run_operator_live_session(_config(tmp_path), environ=env, transcript=None)
    assert exc_info.value is primary, "the cleanup failure replaced the primary error"
    assert any("process status query failed" in note for note in getattr(primary, "__notes__", []))
    assert runtime.state is RedisRuntimeState.CLOSED
    assert client.count == 1 and pool.count == 1, "Redis teardown did not happen exactly once"
    assert runtime.owner.is_terminated
    assert killed == [1], "an unanswerable status query must assume the child is still running"
    assert any("kill unavailable" in note for note in getattr(primary, "__notes__", []))


def test_a_failing_process_status_query_with_no_primary_error_is_raised_after_the_runtime_closes(
    monkeypatch, tmp_path
):
    """With nothing else propagating, the cleanup failure IS the failure -- reported, after custody ends."""
    runtime, client, pool = _runtime()
    _store_for(monkeypatch, runtime)
    env, _killed = _launch_child_whose_status_query_fails(monkeypatch, send_error=None)

    with pytest.raises(OSError, match="process status query failed"):
        operator_verify.run_operator_live_session(_config(tmp_path), environ=env, transcript=None)
    assert runtime.state is RedisRuntimeState.CLOSED
    assert client.count == 1 and pool.count == 1
    assert runtime.owner.is_terminated


def test_a_store_that_owns_no_runtime_is_refused_before_anything_is_launched(monkeypatch, tmp_path):
    """Fail closed: the factory contract is an OWNING store; a borrowed seam cannot be closed here."""
    runtime, _client, _pool = _runtime()
    borrowed = runtime.sync_state_store()
    monkeypatch.setattr(operator_verify.RedisAgentStateStore, "from_url", staticmethod(lambda url, **kw: borrowed))
    launched: list[int] = []
    monkeypatch.setattr(operator_verify.subprocess, "Popen", lambda *a, **k: launched.append(1))
    env = {"OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0"}
    monkeypatch.setattr(operator_verify, "apply_local_defaults", lambda environ, **kw: env)
    try:
        with pytest.raises(RuntimeError, match="requires the owning store"):
            operator_verify.run_operator_live_session(_config(tmp_path), environ=env, transcript=None)
        assert launched == []
    finally:
        runtime.close(timeout=5.0)
