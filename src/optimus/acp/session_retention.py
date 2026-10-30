"""Bounded process-local custody for ACP session retirement."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import itertools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from optimus.acp.debug_trace import acp_debug_log
from optimus_security.failure_facts import exception_fact, host_session_id

if TYPE_CHECKING:
    from optimus.acp.spec import AcpSpecSession
    from optimus.mcp.client_disposition import ClientMcpSessionState


class RetirementReason(Enum):
    CREATE_FAILED = 'CREATE_FAILED'
    SHUTDOWN = 'SHUTDOWN'
    EXPLICIT_REMOVE = 'EXPLICIT_REMOVE'


class RetirementStatus(Enum):
    DEFERRED = 'DEFERRED'
    RETIRING = 'RETIRING'
    QUARANTINED = 'QUARANTINED'
    RELEASED = 'RELEASED'


class SessionCapacityError(RuntimeError):
    pass


@dataclass(frozen=True)
class SessionRetentionPolicy:
    max_sessions: int = 64

    def __post_init__(self) -> None:
        if type(self.max_sessions) is not int:
            raise TypeError('max_sessions must be an integer')
        if self.max_sessions <= 0:
            raise ValueError('max_sessions must be positive')


DEFAULT_SESSION_RETENTION_POLICY = SessionRetentionPolicy()


@dataclass(frozen=True)
class SessionCloseResult:
    failures: tuple[str, ...]
    pending: bool


@dataclass(frozen=True)
class RetirementResult:
    session_id: str
    generation: int
    status: RetirementStatus
    close: SessionCloseResult


@dataclass(eq=False)
class _SessionEntry:
    session: AcpSpecSession
    generation: int
    phase: str
    created: float
    uses: int = 0
    setup_states: list[ClientMcpSessionState] = field(default_factory=list)
    reason: RetirementReason | None = None
    job: asyncio.Task[RetirementResult] | None = None
    result: RetirementResult | None = None
    failure_fact: dict[str, Any] | None = None
    observed_close: SessionCloseResult | None = None
    quiescent: asyncio.Event = field(default_factory=asyncio.Event)


class SessionUseLease:
    def __init__(self, owner: SessionRetentionOwner, entry: _SessionEntry) -> None:
        self._owner: SessionRetentionOwner | None = owner
        self._entry: _SessionEntry | None = entry

    @property
    def session_id(self) -> str | None:
        return self._entry.session.session_id if self._entry is not None else None

    def fork(self) -> SessionUseLease | None:
        if self._entry is None or self._owner is None:
            return None
        self._owner._check_loop()
        entry = self._entry
        if self._owner._entries.get(entry.session.session_id) is not entry or entry.result is not None:
            raise RuntimeError('stale session use')
        return self._owner._acquire_entry(entry)

    def release(self) -> None:
        if self._entry is None or self._owner is None:
            return
        self._owner._check_loop()
        owner, entry = self._owner, self._entry
        self._owner = self._entry = None
        owner._release_use(entry)

    def release_on(self, source: concurrent.futures.Future[Any]) -> None:
        if self._owner is None:
            return
        loop = self._owner._loop

        def completed(_source: concurrent.futures.Future[Any]) -> None:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(self.release)

        source.add_done_callback(completed)


class SessionRetentionOwner:
    def __init__(self, *, policy: SessionRetentionPolicy, clock: Callable[[], float],
                 close_session: Callable[[AcpSpecSession, tuple[ClientMcpSessionState, ...]], Awaitable[SessionCloseResult]],
                 detach_session: Callable[[AcpSpecSession], bool]) -> None:
        self.policy = policy
        self._loop = asyncio.get_running_loop()
        self._clock = clock
        self._close_session = close_session
        self._detach_session = detach_session
        self._entries: dict[str, _SessionEntry] = {}
        self._generations = itertools.count(1)
        self._reservations = 0
        self._admission_closed = False
        self._bound = False

    def _check_loop(self) -> None:
        if asyncio.get_running_loop() is not self._loop:
            raise RuntimeError('session retention belongs to another loop')

    def _log(self, event: str, entry: _SessionEntry | None = None) -> None:
        # Diagnostics cannot affect custody, even when a custom sink fails.
        with contextlib.suppress(Exception):
            acp_debug_log(location='session_retention.py:SessionRetentionOwner', message='session retention',
                          data=lambda: {'event': event, 'session_id': host_session_id(entry.session.session_id)
                                        if entry is not None else None,
                                        'phase': entry.phase if entry is not None else None,
                                        'uses': entry.uses if entry is not None else 0,
                                        'retained_count': self.retained_count,
                                        'reason': entry.reason.value if entry is not None and entry.reason else None,
                                        'elapsed_seconds': max(0.0, self._clock() - entry.created) if entry else 0.0,
                                        'failures': entry.result.close.failures if entry and entry.result else (),
                                        'failure_fact': entry.failure_fact if entry else None})

    @property
    def retained_count(self) -> int:
        return len(self._entries) + self._reservations

    @property
    def session_ids(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def is_active(self, session_id: str) -> bool:
        entry = self._entries.get(session_id)
        return entry is not None and entry.phase == 'ACTIVE'

    def adopt(self, sessions: tuple[AcpSpecSession, ...]) -> None:
        self._check_loop()
        if self._bound or self._entries:
            raise RuntimeError('session retention already bound')
        if len(sessions) > self.policy.max_sessions:
            raise SessionCapacityError('SESSION_CAPACITY')
        if len({session.session_id for session in sessions}) != len(sessions):
            raise RuntimeError('duplicate session identity')
        entries = {session.session_id: self._entry(session, provisional=False) for session in sessions}
        self._entries.update(entries)
        self._bound = True

    def _entry(self, session: AcpSpecSession, *, provisional: bool) -> _SessionEntry:
        created = 0.0
        with contextlib.suppress(Exception):
            created = self._clock()
        entry = _SessionEntry(session, next(self._generations), 'PROVISIONAL' if provisional else 'ACTIVE', created)
        entry.quiescent.set()
        return entry

    def create(self, factory: Callable[[], AcpSpecSession], *, provisional: bool = False) -> AcpSpecSession:
        self._check_loop()
        if self._admission_closed or self.retained_count >= self.policy.max_sessions:
            self._log('refused')
            raise SessionCapacityError('SESSION_CAPACITY')
        self._reservations += 1
        try:
            session = factory()
            if session.session_id in self._entries:
                raise RuntimeError('duplicate session identity')
            self._entries[session.session_id] = self._entry(session, provisional=provisional)
        finally:
            self._reservations -= 1
        self._log('created', self._entries[session.session_id])
        return session

    def activate(self, session_id: str) -> None:
        self._check_loop()
        entry = self._entries[session_id]
        if entry.phase != 'PROVISIONAL':
            raise RuntimeError('session is not provisional')
        entry.phase = 'ACTIVE'
        self._log('activated', entry)

    def acquire(self, session_id: str) -> SessionUseLease | None:
        self._check_loop()
        entry = self._entries.get(session_id)
        if entry is None or entry.phase not in ('PROVISIONAL', 'ACTIVE'):
            return None
        return self._acquire_entry(entry)

    def _acquire_entry(self, entry: _SessionEntry) -> SessionUseLease:
        entry.uses += 1
        entry.quiescent.clear()
        self._log('acquired', entry)
        return SessionUseLease(self, entry)

    def _release_use(self, entry: _SessionEntry) -> None:
        current = self._entries.get(entry.session.session_id)
        if current is not entry or current.generation != entry.generation:
            raise RuntimeError('stale session lease')
        entry.uses -= 1
        if entry.uses == 0:
            entry.quiescent.set()
        self._log('use_released', entry)

    def retain_setup_state(self, session_id: str, state: ClientMcpSessionState) -> None:
        self._check_loop()
        entry = self._entries[session_id]
        if state.session_id != session_id:
            raise RuntimeError('setup state belongs to another session')
        if any(existing is state for existing in entry.setup_states):
            return
        if len(entry.setup_states) >= 2:
            raise RuntimeError('too many setup states')
        entry.setup_states.append(state)

    def _states(self, entry: _SessionEntry) -> tuple[ClientMcpSessionState, ...]:
        states = list(entry.setup_states)
        state = entry.session.client_mcp_state
        if state is not None and not any(existing is state for existing in states):
            states.append(state)
        return tuple(states)

    def request_retire(self, session_id: str, *, reason: RetirementReason) -> RetirementStatus:
        self._check_loop()
        entry = self._entries.get(session_id)
        if entry is None:
            return RetirementStatus.RELEASED
        if entry.result is not None:
            return entry.result.status
        if entry.job is None:
            entry.phase, entry.reason = 'RETIRING', reason
            entry.job = self._loop.create_task(self._retire(entry), name='optimus-session-retirement')
            self._log('retiring', entry)
        return RetirementStatus.DEFERRED if entry.uses else RetirementStatus.RETIRING

    def close_admission(self) -> None:
        self._check_loop()
        self._admission_closed = True

    def retain_close_result(self, session: AcpSpecSession, close: SessionCloseResult) -> None:
        self._check_loop()
        entry = self._entries[session.session_id]
        if entry.session is not session:
            raise RuntimeError('stale session cleanup result')
        prior = entry.observed_close
        entry.observed_close = close if prior is None else SessionCloseResult(
            prior.failures + close.failures, prior.pending or close.pending)

    def _finish(self, entry: _SessionEntry, close: SessionCloseResult) -> RetirementResult:
        current = self._entries.get(entry.session.session_id)
        if current is not entry or current.generation != entry.generation:
            close = SessionCloseResult(('SESSION_IDENTITY_MISMATCH',), False)
        prior = entry.observed_close
        if prior is not None and close is not prior:
            close = SessionCloseResult(prior.failures + close.failures, prior.pending or close.pending)
        clean = not close.failures and not close.pending
        detach_failure: BaseException | None = None
        if clean:
            try:
                detached = self._detach_session(entry.session)
            except BaseException as exc:
                detach_failure = exc
                entry.failure_fact = exception_fact(exc)
                close = SessionCloseResult(('SESSION_DETACH_FAILED',), True)
                clean = False
            else:
                if not detached:
                    close = SessionCloseResult(('SESSION_IDENTITY_MISMATCH',), False)
                    clean = False
        result = RetirementResult(entry.session.session_id, entry.generation,
                                  RetirementStatus.RELEASED if clean else RetirementStatus.QUARANTINED, close)
        entry.result = result
        entry.phase = result.status.value
        self._log('retired', entry)
        if clean:
            del self._entries[entry.session.session_id]
        if detach_failure is not None:
            raise detach_failure
        return result

    async def _retire(self, entry: _SessionEntry) -> RetirementResult:
        await entry.quiescent.wait()
        try:
            close = await self._close_session(entry.session, self._states(entry))
        except BaseException as exc:
            entry.failure_fact = exception_fact(exc)
            close = entry.observed_close or SessionCloseResult(('SESSION_CLOSE_FAILED',), True)
            if not close.failures and not close.pending:
                close = SessionCloseResult(('SESSION_CLOSE_FAILED',), True)
            self._finish(entry, close)
            raise
        return self._finish(entry, close)

    async def drain(self) -> tuple[RetirementResult, ...]:
        self._check_loop()
        results: list[RetirementResult] = []
        primary: BaseException | None = None
        for entry in tuple(self._entries.values()):
            if entry.job is not None:
                try:
                    results.append(await asyncio.shield(entry.job))
                except BaseException as exc:
                    current = asyncio.current_task()
                    if isinstance(exc, asyncio.CancelledError) and current is not None and current.cancelling():
                        raise
                    if primary is None:
                        primary = exc
            elif entry.result is not None:
                results.append(entry.result)
        if primary is not None:
            raise primary
        return tuple(results)

    async def wait_retired(self, session_id: str) -> RetirementResult | None:
        self._check_loop()
        entry = self._entries.get(session_id)
        if entry is None:
            return None
        if entry.job is not None:
            return await asyncio.shield(entry.job)
        return entry.result

    def precheck_sync(self, session_id: str | None = None) -> None:
        self._check_loop()
        entries = tuple(self._entries.values()) if session_id is None else (
            (self._entries[session_id],) if session_id in self._entries else ())
        for entry in entries:
            if entry.result is not None:
                continue
            if (entry.uses or entry.job is not None or entry.session.config_lock.locked()
                    or any(state._suspending or (state._owned_close is not None and not state._owned_close.result.done())
                           for state in self._states(entry))):
                raise RuntimeError('session cleanup requires await aclose()')

    def remove_sync(self, session_id: str) -> None:
        self.precheck_sync(session_id)
        entry = self._entries.get(session_id)
        if entry is None or entry.result is not None:
            return
        entry.phase, entry.reason = 'RETIRING', RetirementReason.EXPLICIT_REMOVE
        failures: list[str] = []
        pending = False
        primary: BaseException | None = None
        for state in self._states(entry):
            try:
                state.close()
            except BaseException as exc:
                if primary is None:
                    primary = exc
                    entry.failure_fact = exception_fact(exc)
            operation = state.prepare_owned_close()
            if operation.result.done():
                failures.extend(operation.result.result())
                pending = pending or operation.pending
            else:
                pending = True
        self._finish(entry, SessionCloseResult(tuple(failures), pending))
        if primary is not None:
            raise primary

    def close_all_sync(self) -> None:
        self.precheck_sync()
        self.close_admission()
        primary: BaseException | None = None
        for session_id in tuple(self._entries):
            try:
                self.remove_sync(session_id)
            except BaseException as exc:
                if primary is None:
                    primary = exc
        if primary is not None:
            raise primary
