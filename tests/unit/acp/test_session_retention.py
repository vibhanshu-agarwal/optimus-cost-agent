from __future__ import annotations

import asyncio
import gc
import weakref
from dataclasses import replace
from time import monotonic

import pytest

from optimus.acp.session_retention import (
    RetirementReason,
    RetirementStatus,
    SessionCapacityError,
    SessionCloseResult,
    SessionRetentionOwner,
    SessionRetentionPolicy,
)
from optimus.acp.spec import InMemoryAcpSpecSessionStore
from optimus.mcp.client_disposition import ClientMcpSessionState


def bound_store(*, cap=2, closer=None):
    store = InMemoryAcpSpecSessionStore()

    async def close(session, states):
        for state in states:
            state.close()
        return SessionCloseResult((), False)

    owner = SessionRetentionOwner(policy=SessionRetentionPolicy(cap), clock=monotonic,
                                  close_session=closer or close, detach_session=store._detach_session)
    store.bind_retention(owner)
    return store, owner


@pytest.mark.parametrize('value', [True, False, 0, -1, 1.0, None])
def test_policy_rejects_invalid_limits(value):
    with pytest.raises((TypeError, ValueError)):
        SessionRetentionPolicy(value)


async def test_capacity_counts_all_owned_phases(tmp_path):
    entered, finish = asyncio.Event(), asyncio.Event()

    async def close(session, states):
        entered.set()
        await finish.wait()
        return SessionCloseResult(('SESSION_CLOSE_FAILED',), False)

    store, owner = bound_store(cap=2, closer=close)
    first = store.create(cwd=tmp_path, provisional=True)
    second = store.create(cwd=tmp_path)
    assert owner.retained_count == 2
    with pytest.raises(SessionCapacityError):
        store.create(cwd=tmp_path)
    owner.activate(first.session_id)
    owner.request_retire(first.session_id, reason=RetirementReason.CREATE_FAILED)
    await entered.wait()
    with pytest.raises(SessionCapacityError):
        store.create(cwd=tmp_path)
    finish.set()
    results = await owner.drain()
    assert results[0].status is RetirementStatus.QUARANTINED
    assert owner.retained_count == 2
    assert store.get(second.session_id) is second
    with pytest.raises(SessionCapacityError):
        store.create(cwd=tmp_path)


async def test_factory_failure_consumes_no_slot(tmp_path):
    store, owner = bound_store(cap=1)

    def fail():
        raise ValueError('factory failed')

    with pytest.raises(ValueError, match='factory failed'):
        owner.create(fail)
    assert owner.retained_count == 0
    store.create(cwd=tmp_path)
    assert owner.retained_count == 1


async def test_adopted_store_over_cap_fails_without_mutation(tmp_path):
    store = InMemoryAcpSpecSessionStore()
    first, second = store.create(cwd=tmp_path), store.create(cwd=tmp_path)

    async def close(session, states):
        return SessionCloseResult((), False)

    owner = SessionRetentionOwner(policy=SessionRetentionPolicy(1), clock=monotonic,
                                  close_session=close, detach_session=store._detach_session)
    with pytest.raises(SessionCapacityError):
        store.bind_retention(owner)
    assert store.get(first.session_id) is first and store.get(second.session_id) is second
    assert owner.retained_count == 0
    assert store._retention is None


async def test_use_release_is_idempotent_and_drops_entry_reference(tmp_path):
    store, owner = bound_store()
    session = store.create(cwd=tmp_path)
    lease = owner.acquire(session.session_id)
    assert lease is not None
    session_ref = weakref.ref(session)
    assert owner.request_retire(session.session_id, reason=RetirementReason.SHUTDOWN) is RetirementStatus.DEFERRED
    assert owner.acquire(session.session_id) is None
    assert store.get(session.session_id) is session
    lease.release()
    lease.release()
    await owner.drain()
    del session
    gc.collect()
    assert session_ref() is None
    assert owner.retained_count == 0
    assert lease._entry is None


async def test_retirement_requires_exact_identity_and_generation(tmp_path):
    store, owner = bound_store()
    original = store.create(cwd=tmp_path)
    replacement = replace(original)
    store._sessions[original.session_id] = replacement
    owner.request_retire(original.session_id, reason=RetirementReason.SHUTDOWN)
    result, = await owner.drain()
    assert result.status is RetirementStatus.QUARANTINED
    assert store.get(original.session_id) is replacement
    assert owner.retained_count == 1


async def test_close_failure_is_sticky_and_does_not_free_capacity(tmp_path):
    calls = []

    async def close(session, states):
        calls.append(session.session_id)
        return SessionCloseResult(('SESSION_CLOSE_FAILED',), False)

    store, owner = bound_store(cap=1, closer=close)
    session = store.create(cwd=tmp_path)
    owner.request_retire(session.session_id, reason=RetirementReason.SHUTDOWN)
    first, = await owner.drain()
    assert first.status is RetirementStatus.QUARANTINED
    assert owner.request_retire(session.session_id, reason=RetirementReason.SHUTDOWN) is RetirementStatus.QUARANTINED
    assert await owner.drain() == (first,)
    assert calls == [session.session_id]
    assert store.get(session.session_id) is session
    with pytest.raises(SessionCapacityError):
        store.create(cwd=tmp_path)


async def test_second_retirement_joins_the_same_operation(tmp_path):
    entered, finish = asyncio.Event(), asyncio.Event()
    calls = []

    async def close(session, states):
        calls.append(session.session_id)
        entered.set()
        await finish.wait()
        return SessionCloseResult((), False)

    store, owner = bound_store(closer=close)
    session = store.create(cwd=tmp_path)
    owner.request_retire(session.session_id, reason=RetirementReason.SHUTDOWN)
    await entered.wait()
    assert owner.request_retire(session.session_id, reason=RetirementReason.SHUTDOWN) is RetirementStatus.RETIRING
    finish.set()
    result, = await owner.drain()
    assert result.status is RetirementStatus.RELEASED
    assert calls == [session.session_id]
    assert owner.retained_count == 0


async def test_bound_store_refuses_sync_cleanup_before_mutation(tmp_path):
    store, owner = bound_store()
    first, second = store.create(cwd=tmp_path), store.create(cwd=tmp_path)
    closed = []
    first.client_mcp_state = ClientMcpSessionState(first.session_id)
    first.client_mcp_state.register_close_hook(lambda: closed.append(first.session_id))
    lease = owner.acquire(second.session_id)
    with pytest.raises(RuntimeError, match=r'session cleanup requires await aclose\(\)'):
        store.remove(second.session_id)
    with pytest.raises(RuntimeError, match=r'session cleanup requires await aclose\(\)'):
        store.close_all()
    assert closed == []
    assert store.get(first.session_id) is first and store.get(second.session_id) is second
    lease.release()
    store.close_all()
    store.close_all()
    assert closed == [first.session_id]
    assert owner.retained_count == 0
    assert await owner.drain() == ()
    with pytest.raises(SessionCapacityError):
        store.create(cwd=tmp_path)


async def test_sync_close_failure_and_legacy_unknown_remain_owned(tmp_path):
    for legacy in (False, True):
        store, owner = bound_store(cap=1)
        session = store.create(cwd=tmp_path)
        state = session.client_mcp_state = ClientMcpSessionState(session.session_id)
        calls = []

        def fail(calls=calls):
            calls.append('close')
            raise RuntimeError('private failure')

        state.register_close_hook(fail)
        if legacy:
            hooks = state.prepare_close()
            assert len(hooks) == 1
        store.remove(session.session_id)
        result, = await owner.drain()
        assert result.status is RetirementStatus.QUARANTINED
        assert owner.retained_count == 1
        assert store.get(session.session_id) is session
        assert calls == ([] if legacy else ['close'])


async def test_setup_states_are_identity_deduplicated(tmp_path):
    received = []

    async def close(session, states):
        received.extend(states)
        return SessionCloseResult((), False)

    store, owner = bound_store(closer=close)
    session = store.create(cwd=tmp_path, provisional=True)
    first, second = ClientMcpSessionState(session.session_id), ClientMcpSessionState(session.session_id)
    owner.retain_setup_state(session.session_id, first)
    owner.retain_setup_state(session.session_id, first)
    owner.retain_setup_state(session.session_id, second)
    session.client_mcp_state = second
    owner.request_retire(session.session_id, reason=RetirementReason.CREATE_FAILED)
    await owner.drain()
    assert len(received) == 2 and received[0] is first and received[1] is second


async def test_capacity_is_reserved_before_reentrant_factory_and_failure(tmp_path):
    store, owner = bound_store(cap=1)

    def factory():
        assert owner.retained_count == 1
        with pytest.raises(SessionCapacityError):
            store.create(cwd=tmp_path)
        raise ValueError('allocation failed')

    with pytest.raises(ValueError, match='allocation failed'):
        owner.create(factory)
    assert owner.retained_count == 0 and store._sessions == {}


async def test_bind_is_one_time_and_adopts_real_sessions(tmp_path):
    store = InMemoryAcpSpecSessionStore()
    session = store.create(cwd=tmp_path)

    async def close(session, states):
        return SessionCloseResult((), False)

    owner = SessionRetentionOwner(policy=SessionRetentionPolicy(1), clock=monotonic,
                                  close_session=close, detach_session=store._detach_session)
    store.bind_retention(owner)
    assert owner.retained_count == 1
    lease = owner.acquire(session.session_id)
    assert lease._entry.session is session
    with pytest.raises(RuntimeError, match='already bound'):
        store.bind_retention(owner)
    with pytest.raises(RuntimeError, match='already bound'):
        InMemoryAcpSpecSessionStore().bind_retention(owner)
    lease.release()


async def test_stale_generation_cannot_detach_replacement(tmp_path):
    store, owner = bound_store()
    original = store.create(cwd=tmp_path)
    old_entry = owner._entries[original.session_id]
    store.remove(original.session_id)
    replacement = replace(original)
    store._sessions[replacement.session_id] = replacement
    owner.create(lambda: replacement)
    assert owner._entries[replacement.session_id].generation > old_entry.generation
    result = owner._finish(old_entry, SessionCloseResult((), False))
    assert result.status is RetirementStatus.QUARANTINED
    assert owner.retained_count == 1 and store.get(replacement.session_id) is replacement


async def test_pending_close_and_config_custody_refuse_sync_cleanup(tmp_path):
    store, owner = bound_store()
    session = store.create(cwd=tmp_path)
    state = session.client_mcp_state = ClientMcpSessionState(session.session_id)
    await session.config_lock.acquire()
    with pytest.raises(RuntimeError, match='requires await aclose'):
        store.remove(session.session_id)
    session.config_lock.release()
    operation = state.prepare_owned_close()
    assert operation.claim_hooks() == ()
    with pytest.raises(RuntimeError, match='requires await aclose'):
        store.close_all()
    assert store.get(session.session_id) is session
    operation.finish(())
    store.remove(session.session_id)
    assert owner.retained_count == 0


async def test_close_exception_is_never_success_and_is_not_retried(tmp_path):
    calls = []

    async def close(session, states):
        calls.append(session.session_id)
        raise ValueError('close failed')

    store, owner = bound_store(closer=close)
    session = store.create(cwd=tmp_path)
    owner.request_retire(session.session_id, reason=RetirementReason.SHUTDOWN)
    for _ in range(2):
        with pytest.raises(ValueError, match='close failed'):
            await owner.drain()
    assert owner.retained_count == 1 and calls == [session.session_id]
    assert owner.request_retire(session.session_id, reason=RetirementReason.SHUTDOWN) is RetirementStatus.QUARANTINED


async def test_cancelling_drain_does_not_cancel_owned_close(tmp_path):
    entered, finish = asyncio.Event(), asyncio.Event()

    async def close(session, states):
        entered.set()
        await finish.wait()
        return SessionCloseResult((), False)

    store, owner = bound_store(closer=close)
    session = store.create(cwd=tmp_path)
    owner.request_retire(session.session_id, reason=RetirementReason.SHUTDOWN)
    await entered.wait()
    observer = asyncio.create_task(owner.drain())
    await asyncio.sleep(0)
    observer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await observer
    assert owner.retained_count == 1
    assert not owner._entries[session.session_id].job.cancelled()
    finish.set()
    result, = await owner.drain()
    assert result.status is RetirementStatus.RELEASED


async def test_incomplete_close_is_sticky_without_deadline_expiry(tmp_path):
    calls = []

    async def close(session, states):
        calls.append(session.session_id)
        return SessionCloseResult((), True)

    store, owner = bound_store(cap=1, closer=close)
    session = store.create(cwd=tmp_path)
    owner.request_retire(session.session_id, reason=RetirementReason.CREATE_FAILED)
    first, = await owner.drain()
    assert first.status is RetirementStatus.QUARANTINED
    assert await owner.drain() == (first,)
    assert calls == [session.session_id]
    with pytest.raises(SessionCapacityError):
        store.create(cwd=tmp_path)


async def test_diagnostic_clock_failure_does_not_change_admission(tmp_path):
    store = InMemoryAcpSpecSessionStore()

    def broken_clock():
        raise ValueError('diagnostic failure')

    async def close(session, states):
        return SessionCloseResult((), False)

    owner = SessionRetentionOwner(policy=SessionRetentionPolicy(), clock=broken_clock,
                                  close_session=close, detach_session=store._detach_session)
    store.bind_retention(owner)
    session = store.create(cwd=tmp_path)
    store.remove(session.session_id)
    assert owner.retained_count == 0


async def test_retirement_diagnostic_fields_are_bounded_and_exclude_private_causes(tmp_path, monkeypatch):
    import optimus.acp.session_retention as module

    messages = []
    monkeypatch.setattr(module, 'acp_debug_log', lambda **fields: messages.append(fields['data']()))
    original = OSError('private-cause-with-history-and-credential')
    async def fail(_session, _states):
        raise original
    store, owner = bound_store(closer=fail)
    session = store.create(cwd=tmp_path)
    owner.request_retire(session.session_id, reason=RetirementReason.EXPLICIT_REMOVE)
    with pytest.raises(OSError) as caught:
        await owner.wait_retired(session.session_id)
    assert caught.value is original
    result = owner._entries[session.session_id].result
    assert result.status is RetirementStatus.QUARANTINED
    assert messages and messages[-1]['failure_fact']
    assert all(set(message) == {'event', 'session_id', 'phase', 'uses', 'retained_count', 'reason',
                                'elapsed_seconds', 'failures', 'failure_fact'} for message in messages)
    assert 'private-cause' not in repr(messages) and str(tmp_path) not in repr(messages)
    assert messages[-1]['retained_count'] == 1


async def test_sync_close_all_attempts_other_entries_preserving_first_control_failure(tmp_path):
    store, owner = bound_store()
    first, second = store.create(cwd=tmp_path), store.create(cwd=tmp_path)
    first.client_mcp_state = ClientMcpSessionState(first.session_id)
    second.client_mcp_state = ClientMcpSessionState(second.session_id)
    failure = SystemExit(23)
    closed = []

    def fail():
        closed.append('first')
        raise failure

    first.client_mcp_state.register_close_hook(fail)
    second.client_mcp_state.register_close_hook(lambda: closed.append('second'))
    with pytest.raises(SystemExit) as caught:
        store.close_all()
    assert caught.value is failure
    assert closed == ['first', 'second']
    assert owner.retained_count == 1
    assert store.get(first.session_id) is first and store.get(second.session_id) is None
    store.close_all()
    assert closed == ['first', 'second']


@pytest.mark.parametrize('synchronous', [False, True], ids=['async', 'sync'])
async def test_detach_exception_is_sticky_quarantine_with_original_cause(tmp_path, synchronous):
    store = InMemoryAcpSpecSessionStore()
    detached, closed = [], []
    cause = ValueError('private cause must not enter diagnostics')
    failure = OSError(5, 'private detach error')

    def detach(session):
        detached.append(session.session_id)
        raise failure from cause

    async def close(session, states):
        closed.append(session.session_id)
        return SessionCloseResult((), False)

    owner = SessionRetentionOwner(policy=SessionRetentionPolicy(1), clock=monotonic,
                                  close_session=close, detach_session=detach)
    store.bind_retention(owner)
    session = store.create(cwd=tmp_path)
    if synchronous:
        with pytest.raises(OSError) as caught:
            store.remove(session.session_id)
    else:
        owner.request_retire(session.session_id, reason=RetirementReason.SHUTDOWN)
        with pytest.raises(OSError) as caught:
            await owner.drain()
    assert caught.value is failure and caught.value.__cause__ is cause
    assert owner.request_retire(session.session_id, reason=RetirementReason.SHUTDOWN) is RetirementStatus.QUARANTINED
    entry = owner._entries[session.session_id]
    assert entry.result.status is RetirementStatus.QUARANTINED
    assert 'SESSION_DETACH_FAILED' in entry.result.close.failures
    assert entry.failure_fact == {'class': 'OSError', 'cause': 'ValueError', 'errno': 5}
    assert owner.retained_count == 1 and store.get(session.session_id) is session
    if synchronous:
        result, = await owner.drain()
        assert result is entry.result
    else:
        with pytest.raises(OSError) as repeated:
            await owner.drain()
        assert repeated.value is failure and repeated.value.__cause__ is cause
    assert detached == [session.session_id]
    assert closed == ([] if synchronous else [session.session_id])
