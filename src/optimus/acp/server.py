from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import io
import json
import os
import queue
import sys
import threading
import uuid
import weakref
from collections.abc import Callable, Mapping
from pathlib import Path
from time import monotonic
from typing import Any, Protocol

from optimus.acp.admission import DEFAULT_LIMITS, AdmissionAccount, AdmissionClass, AdmissionLimits, Reservation
from optimus.acp.debug_trace import acp_debug_log, debug_trace_enabled, log_provenance_once
from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.errors import (
    INTERNAL_ERROR,
    INVALID_REQUEST,
    REQUEST_CANCELLED,
    AcpOutboundError,
    JsonRpcError,
    error_response,
    sanitize_protocol_error_message,
)
from optimus.acp.framing import FramingError, encode_message, read_message
from optimus.acp.lifecycle import (
    NonTurnResponseEnvelope,
    NoticeControl,
    ResponseKind,
    ResponseOwnershipSlot,
    SendCompletion,
    TurnControl,
    TurnResponseEnvelope,
)
from optimus.acp.outbound_writer import DedicatedOutboundWriter, EphemeralSendOwner, OutboundQueueItem, next_ephemeral_send_key
from optimus.acp.process_lifecycle import ProcessLifecycle, ShutdownObservation, StopReason, cleanup_failure, raise_preserving_failure
from optimus.acp.settlement import RpcResponseDelivery, SendOutcome, SettlementInvariantError
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, progress_submission, request_worker_custody
from optimus.mcp.client_disposition import ClientMcpShutdownOutcome
from optimus.mcp.client_supervisor import MCPSupervisorState


# A Protocol describes a shape ("anything with async read(size) -> bytes") without
# requiring inheritance. handle_one() accepts asyncio.StreamReader in production or
# in-memory test fakes, as long as they implement the same methods.
class AsyncByteReader(Protocol):
    """Async byte input for ACP framing (e.g. asyncio.StreamReader on stdin)."""

    async def read(self, size: int) -> bytes:
        ...


class AsyncByteWriter(Protocol):
    """Async byte output for framed responses (e.g. stdout with drain())."""

    def write(self, data: bytes) -> None:
        ...

    async def drain(self) -> None:
        ...


class SyncByteReader(Protocol):
    def read(self, size: int, /) -> bytes: ...


class SyncLineReader(Protocol):
    def readline(self) -> bytes: ...


class SyncByteWriter(Protocol):
    def write(self, data: bytes, /) -> object: ...
    def flush(self) -> object: ...


def _request_failure_payload(
    exc: Exception, request_id: object, method: object, pending_permission_id: object,
    format_exception: Callable[[Exception], str],
) -> Callable[[], dict[str, object]]:
    def payload() -> dict[str, object]:
        return {
            "request_id": request_id,
            "method": method,
            "pending_permission_id": pending_permission_id,
            "exception_type": type(exc).__name__,
            "exception_message": format_exception(exc),
        }
    return payload


def _inbound_response_payload(message: Mapping[str, object]) -> Callable[[], dict[str, object]]:
    def payload() -> dict[str, object]:
        return {
            "id": message.get("id"),
            "has_result": "result" in message,
            "has_error": "error" in message,
            "error": message.get("error") if "error" in message else None,
            "result": message.get("result") if "result" in message else None,
        }
    return payload


class _StdinRead:
    """Exclusive ACP input without holding Python's shared buffered-stdin lock at exit."""

    def __init__(self, descriptor: int) -> None:
        self._descriptor = descriptor
        self._buffer = bytearray()

    def read(self, size: int) -> bytes:
        if size == 0:
            return b""
        if self._buffer:
            result = bytes(self._buffer if size < 0 else self._buffer[:size])
            del self._buffer[:len(result)]
            return result
        return os.read(self._descriptor, 8192 if size < 0 else size)

    def readline(self, size: int = -1) -> bytes:
        while True:
            newline = self._buffer.find(b"\n")
            count = newline + 1 if newline >= 0 else len(self._buffer)
            if size >= 0:
                count = min(count, size)
            if newline >= 0 or (size >= 0 and len(self._buffer) >= size):
                result = bytes(self._buffer[:count])
                del self._buffer[:count]
                return result
            chunk = os.read(self._descriptor, 8192 if size < 0 else min(8192, size - len(self._buffer)))
            if not chunk:
                result = bytes(self._buffer)
                self._buffer.clear()
                return result
            self._buffer.extend(chunk)


class _OwnedStdioReader:
    """One daemon owns borrowed input; cancelling an await never closes that input."""

    def __init__(self, operation: Callable[..., bytes]) -> None:
        self._operation = operation
        self._commands: queue.Queue[tuple[concurrent.futures.Future[bytes], tuple[Any, ...]] | None] = queue.Queue(maxsize=2)
        self._pending_read: concurrent.futures.Future[bytes] | None = None
        self._read_thread: threading.Thread | None = None
        self._read_lock = threading.Lock()
        self._read_closed = False
        self._awaiting_read = False

    @property
    def pending_read(self) -> concurrent.futures.Future[bytes] | None:
        return self._pending_read

    @property
    def read_thread(self) -> threading.Thread | None:
        return self._read_thread

    async def _read(self, *args: Any) -> bytes:
        with self._read_lock:
            if self._read_closed:
                raise RuntimeError("stdio reader is closed")
            if self._awaiting_read:
                raise RuntimeError("concurrent stdio reads are not supported")
            self._awaiting_read = True
            if self._pending_read is None:
                self._pending_read = concurrent.futures.Future()
                if self._read_thread is None:
                    self._read_thread = threading.Thread(target=self._run_read, name="optimus-acp-stdin", daemon=True)
                    try:
                        self._read_thread.start()
                    except BaseException:
                        self._read_thread = None
                        self._pending_read = None
                        self._awaiting_read = False
                        raise
                self._commands.put_nowait((self._pending_read, args))
            pending = self._pending_read
        try:
            result = await asyncio.shield(asyncio.wrap_future(pending))
        except BaseException:
            raise
        else:
            with self._read_lock:
                if self._pending_read is pending:
                    self._pending_read = None
            return result
        finally:
            with self._read_lock:
                self._awaiting_read = False

    def _run_read(self) -> None:
        while True:
            command = self._commands.get()
            if command is None:
                return
            future, args = command
            if future.set_running_or_notify_cancel():
                try:
                    result = self._operation(*args)
                except BaseException as exc:
                    future.set_exception(exc)
                else:
                    future.set_result(result)

    def request_close(self) -> None:
        with self._read_lock:
            if self._read_closed:
                return
            self._read_closed = True
            if self._pending_read is not None:
                self._pending_read.cancel()  # succeeds only before the physical call starts
            if self._read_thread is not None:
                self._commands.put_nowait(None)  # second slot is reserved for this one marker

    def observe_closed(self, timeout: float) -> bool:
        thread = self._read_thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()


class _StdioReadFacade:
    def __init__(self, operation: Callable[..., bytes]) -> None:
        self._owner = _OwnedStdioReader(operation)
        # The owner thread retains its state, not this facade; retirement can wake an idle owner.
        self._retire = weakref.finalize(self, self._owner.request_close)

    @property
    def pending_read(self) -> concurrent.futures.Future[bytes] | None:
        return self._owner.pending_read

    @property
    def read_thread(self) -> threading.Thread | None:
        return self._owner.read_thread

    async def _read(self, *args: Any) -> bytes:
        return await self._owner._read(*args)

    def request_close(self) -> None:
        self._retire()

    def observe_closed(self, timeout: float) -> bool:
        return self._owner.observe_closed(timeout)


class StdioByteReader(_StdioReadFacade):
    def __init__(self, stream: SyncByteReader) -> None:
        self._stream = stream
        physical = _StdinRead(sys.stdin.fileno()) if stream is getattr(sys.stdin, "buffer", None) else stream
        super().__init__(physical.read)

    async def read(self, size: int) -> bytes:
        return await self._read(size)


class StdioByteWriter:
    def __init__(self, stream: SyncByteWriter) -> None:
        self._stream = stream
        self._physical = StdioNdjsonLineWriter(stream)
        self._dedicated = DedicatedOutboundWriter(self._physical)
        self._last_send: concurrent.futures.Future[SendCompletion] | None = None
        self._retire = weakref.finalize(self, self._dedicated.request_close)

    def write(self, data: bytes) -> None:
        self._dedicated.start()
        owner = EphemeralSendOwner()
        key = next_ephemeral_send_key("framed")
        owner.create_queued(key)
        source: concurrent.futures.Future[SendCompletion] = concurrent.futures.Future()
        self._dedicated.submit(OutboundQueueItem(payload={}, send_key=key, owner=owner, source_future=source, encoded_payload=data))
        self._last_send = source

    async def drain(self) -> None:
        if self._last_send is not None:
            completion = await asyncio.shield(asyncio.wrap_future(self._last_send))
            if self._physical.physical_failure is not None:
                raise_preserving_failure(self._physical.physical_failure)
            if completion.outcome is not SendOutcome.FLUSHED:
                raise OSError("framed output delivery incomplete")

    def request_close(self) -> None:
        self._dedicated.request_close()

    def observe_closed(self, timeout: float | None) -> bool:
        return self._dedicated.observe_closed(timeout)

    def close_and_join(self) -> None:
        self._dedicated.close_and_join()

    @property
    def thread_alive(self) -> bool:
        return self._dedicated.thread_alive


class StdioNdjsonLineReader(_StdioReadFacade):
    def __init__(self, stream: SyncLineReader, *, limited_readline: Callable[[int], bytes] | None = None) -> None:
        self._stream = stream
        physical = _StdinRead(sys.stdin.fileno()) if stream is getattr(sys.stdin, "buffer", None) else stream
        self.supports_limited_read = limited_readline is not None or isinstance(physical, (_StdinRead, io.IOBase))
        if limited_readline is not None:
            super().__init__(lambda size=None: stream.readline() if size is None else limited_readline(size))
            return
        super().__init__(physical.readline)

    async def readline(self) -> bytes:
        return await self._read()

    async def readline_limited(self, limit: int) -> bytes:
        if not self.supports_limited_read:
            raise TypeError("injected stream requires an explicit limited-read seam")
        line = await self._read(limit + 2)
        if len(line.removesuffix(b"\n").removesuffix(b"\r")) <= limit:
            return line
        ended = line.endswith(b"\n")
        del line
        while not ended:
            chunk = await self._read(min(65536, limit + 1))
            ended = not chunk or chunk.endswith(b"\n")
        raise FramingError("body too large", code=INVALID_REQUEST)


class StdioNdjsonLineWriter:
    def __init__(self, stream: SyncByteWriter) -> None:
        self._stream = stream
        self._physical_failure: BaseException | None = None

    @property
    def physical_failure(self) -> BaseException | None:
        return self._physical_failure

    def write_bytes(self, data: bytes) -> None:
        try:
            self._stream.write(data)
        except BaseException as exc:
            self._physical_failure = exc
            raise

    def flush(self) -> None:
        try:
            self._stream.flush()
        except BaseException as exc:
            self._physical_failure = exc
            raise

    async def write_line(self, message: Mapping[str, Any]) -> None:
        payload = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
        await asyncio.to_thread(self.write_bytes, payload)
        await asyncio.to_thread(self.flush)


class NdjsonLineReader(Protocol):
    async def readline(self) -> bytes:
        ...


class NdjsonLineWriter(Protocol):
    async def write_line(self, message: Mapping[str, Any]) -> None:
        ...


class NdjsonOutboundChannel:
    """
    Handles the outbound communication channel over NDJSON protocol.

    This class is responsible for sending notifications and requests in the
    NDJSON-RPC format, managing request IDs, handling responses from the client,
    and providing means to cancel pending requests. Physical writes go through
    the dedicated FIFO writer when configured.
    """

    def __init__(
        self,
        writer: NdjsonLineWriter,
        *,
        dedicated_writer: Any | None = None,
    ) -> None:
        self._writer = writer
        self._dedicated_writer = dedicated_writer
        self._agent_request_ids = iter(range(10_000, 100_000))
        self._futures: dict[str | int, asyncio.Future[dict[str, Any]]] = {}
        self.last_outbound_request_id: str | int | None = None
        self._ephemeral_owners: list[Any] = []

    def allocate_permission_request(
        self, method: str, params: dict[str, Any]
    ) -> Any:
        """Synchronously allocate request_id, future, and correlation (no await)."""
        from optimus.acp.lifecycle import PermissionRequestHandle

        request_id = next(self._agent_request_ids)
        self.last_outbound_request_id = request_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._futures[request_id] = future
        return PermissionRequestHandle(
            channel=self,
            request_id=request_id,
            response_future=future,
            method=method,
            params=params,
        )

    async def _submit_payload(self, message: Mapping[str, Any], *, kind: str, admission_class: AdmissionClass = AdmissionClass.REQUIRED) -> SendOutcome | None:
        """Returns the dedicated writer's outcome; ``None`` on the direct path, which raises on failure."""
        progress = progress_submission.get()
        if self._dedicated_writer is None:
            if progress is not None and progress.control.claim_write_started(progress.send_key).value == "suppressed":
                progress.admission.set()
                return SendOutcome.SUPPRESSED
            try:
                await self._writer.write_line(message)
            except BaseException:
                if progress is not None:
                    progress.control.publish_authoritative(progress.send_key, SendOutcome.AMBIGUOUS)
                raise
            else:
                if progress is not None:
                    progress.control.publish_authoritative(progress.send_key, SendOutcome.FLUSHED)
            finally:
                if progress is not None:
                    progress.admission.set()
            return None
        from optimus.acp.outbound_writer import (
            EphemeralSendOwner,
            OutboundQueueItem,
            SendOwner,
            next_ephemeral_send_key,
        )

        owner: SendOwner
        if progress is None:
            ephemeral = EphemeralSendOwner()
            send_key = next_ephemeral_send_key(kind)
            ephemeral.create_queued(send_key)
            owner = ephemeral
        else:
            send_key = progress.send_key
            owner = progress.control
        source: concurrent.futures.Future[SendCompletion] = concurrent.futures.Future()
        item = OutboundQueueItem(
            payload=message,
            send_key=send_key,
            owner=owner,
            source_future=source,
            admission_class=progress.admission_class if progress is not None else admission_class,
        )
        if progress is not None:
            progress.admission.physical_future = source
        try:
            self._dedicated_writer.submit(item)
        except RuntimeError:
            if progress is None:
                raise
            owner.publish_authoritative(send_key, SendOutcome.SUPPRESSED)
            source.set_result(SendCompletion(send_key=send_key, outcome=SendOutcome.SUPPRESSED))
            return SendOutcome.SUPPRESSED
        finally:
            if progress is not None:
                progress.admission.set()
        loop = asyncio.get_running_loop()
        completion = await asyncio.shield(asyncio.wrap_future(source, loop=loop))
        if completion.outcome is SendOutcome.CONCLUSIVE_FAILURE:
            raise AcpOutboundError(code=INTERNAL_ERROR, message="outbound delivery failed")
        return completion.outcome

    async def notify(self, method: str, params: dict[str, Any], *, require_flushed: bool = False) -> None:
        # region agent log
        if debug_trace_enabled():
            acp_debug_log(
                location="server.py:NdjsonOutboundChannel.notify",
                message="outbound notification",
                data=lambda: {"method": method, "param_keys": sorted(params.keys())},
                hypothesis_id="H2",
            )
        # endregion
        outcome = await self._submit_payload(
            {"jsonrpc": "2.0", "method": method, "params": params},
            kind="notify",
            admission_class=AdmissionClass.REQUIRED if require_flushed else AdmissionClass.ORDINARY,
        )
        # Plan 12.1 mode updates pass require_flushed: an ambiguous or suppressed send
        # is not success, so the setter keeps its pending flag for a retry. Other
        # callers keep treating every outcome except a conclusive failure as sent.
        if require_flushed and outcome is not None and outcome is not SendOutcome.FLUSHED:
            raise AcpOutboundError(code=INTERNAL_ERROR, message="outbound delivery unconfirmed")

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = next(self._agent_request_ids)
        self.last_outbound_request_id = request_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._futures[request_id] = future
        # region agent log
        if debug_trace_enabled():
            acp_debug_log(
                location="server.py:NdjsonOutboundChannel.request",
                message="outbound request sent",
                data=lambda: {
                    "request_id": request_id,
                    "method": method,
                    "param_keys": sorted(params.keys()),
                    "has_toolCall": "toolCall" in params,
                },
                hypothesis_id="H2",
            )
        # endregion
        try:
            await self._submit_payload(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
                kind="request",
            )
            return await future
        finally:
            if self._futures.get(request_id) is future:
                self._futures.pop(request_id)
            if not future.done():
                future.cancel()

    def cancel_request(self, request_id: str | int, result: dict[str, Any]) -> None:
        future = self._futures.get(request_id)
        if future is not None and not future.done():
            future.set_result(result)

    def deliver_client_response(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        # region agent log
        if debug_trace_enabled():
            acp_debug_log(
                location="server.py:NdjsonOutboundChannel.deliver_client_response",
                message="client response delivered (post-mapping)",
                data=lambda: {
                    "request_id": request_id,
                    "has_result": "result" in message,
                    "has_error": "error" in message,
                    "mapped_to_cancelled": False,
                    "propagated_error": "error" in message,
                    "result_keys": sorted(message.get("result", {}).keys()) if isinstance(message.get("result"), dict) else [],
                },
                hypothesis_id="H1",
            )
        # endregion
        if request_id is None:
            return
        future = self._futures.pop(request_id, None)
        if future is not None and not future.done():
            if "result" in message and isinstance(message["result"], dict):
                future.set_result(message["result"])
            elif "error" in message:
                error_payload = message["error"]
                code = error_payload.get("code", INTERNAL_ERROR) if isinstance(error_payload, dict) else INTERNAL_ERROR
                msg = error_payload.get("message", "client error") if isinstance(error_payload, dict) else "client error"
                data = error_payload.get("data") if isinstance(error_payload, dict) else None
                data_dict = data if isinstance(data, dict) else None
                future.set_exception(AcpOutboundError(code=code, message=msg, data=data_dict))


#: Per-call observation budget for the serving process's Redis teardown stage. Test-injectable.
REDIS_SHUTDOWN_OBSERVATION_SECONDS = 10.0

# Client methods whose name may appear in a content-free diagnostic; anything else
# collapses to "unknown" so arbitrary client content is never echoed.
APPROVED_METHOD_CATEGORIES = frozenset(
    {
        "initialize",
        "session/new",
        "session/load",
        "session/prompt",
        "session/set_mode",
        "session/set_config_option",
    }
)


def redis_cleanup_payload(runtime: Any) -> dict[str, Any]:
    """The only fields the Redis diagnostic may carry: lifecycle state and stage outcomes.

    Read lazily by the sink; a runtime that cannot answer degrades to fixed sentinels so no
    arbitrary content reaches the diagnostic.
    """
    try:
        record = runtime.teardown_record
        state = runtime.state
        return {
            "state": state.value if hasattr(state, "value") else "unknown",
            "outcome": "unknown",
            "client": record.client.value if record is not None else "unknown",
            "pool": record.pool.value if record is not None else "unknown",
            "owner_terminated": bool(record.owner_terminated) if record is not None else False,
            "admitted_work_settled": bool(record.admitted_work_settled) if record is not None else False,
        }
    except Exception:  # noqa: BLE001 - diagnostic boundary; sentinels, never content
        return {
            "state": "unknown",
            "outcome": "unknown",
            "client": "unknown",
            "pool": "unknown",
            "owner_terminated": False,
            "admitted_work_settled": False,
        }


def report_redis_cleanup_incomplete(runtime: Any, outcome: str) -> None:
    """One content-free attempt to record that the Redis teardown did not complete cleanly.

    Contained like the MCP reporter: this runs inside ``finally``, where a raise would
    replace the cancellation or exception that initiated teardown.
    """

    def payload() -> dict[str, Any]:
        return {**redis_cleanup_payload(runtime), "outcome": outcome}

    try:
        acp_debug_log(
            location="server.py:serve_ndjson:redis_cleanup_incomplete",
            message="redis runtime cleanup incomplete at teardown",
            data=payload,
        )
    except Exception:
        return


class AcpStreamServer:
    """
    Handles Advanced Control Protocol (ACP) stream server functionality, allowing
    interaction between a client and server using JSON-RPC or NDJSON over various
    communication channels.

    This class facilitates processing of client requests and manages the interaction
    using provided or default JsonRpcDispatcher instances, supporting multiple
    communication patterns (streaming or newline-delimited JSON). Intended for
    scenarios requiring structured communication, such as IDE integrations, build
    automation, or custom tooling.

    :ivar dispatcher: JSON-RPC dispatcher instance used to process incoming
        requests and route them to the correct handling functions.
    :type dispatcher: JsonRpcDispatcher
    """
    def __init__(
        self,
        dispatcher: JsonRpcDispatcher | None = None,
        *,
        max_planning_turns: int | None = None,
        interactive_recovery: bool = True,
        client_mcp_runtime: Any | None = None,
        conversation_sanitizer_inputs: Any | None = None,
        redis_runtime: Any | None = None,
        route_policy: Any | None = None,
        context_attachment: Any | None = None,
        session_seeder: Any | None = None,
        failure_telemetry: Any | None = None,
        auto_router: Any | None = None,
        mcp_idle_seconds: int | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
        admission_limits: AdmissionLimits = DEFAULT_LIMITS,
    ) -> None:
        self._dispatcher = dispatcher or JsonRpcDispatcher()
        self._admission_limits = admission_limits
        self._ignored_notifications = 0
        # Correction plan v4, C4: the harness's workspace telemetry writer, passed into every ndjson session adapter
        # for its always-on refusal and fault records. None writes none.
        self._failure_telemetry = failure_telemetry
        # Plan 12.2 closure: the trusted planning/answer route policy (the shipped registry's for an
        # ordinary launch, a reviewed test composition's otherwise), passed into every ndjson session
        # adapter. None sends unbound requests (registry enforcement inactive).
        self._route_policy = route_policy
        # Plan 12.2: the attached Context Engine (the shipped ordinary attachment, or Stage C's) and Stage C's
        # one-time scenario seeder, passed into every ndjson session adapter. None: absent engine.
        self._context_attachment = context_attachment
        self._session_seeder = session_seeder
        # Plan 12.4 Task 4: an Auto launch's per-turn router, which binds each turn's route and attachment itself.
        self._auto_router = auto_router
        # Plan 9.96, Task 5 Step 2: resolved once by build_configured_server()
        # from the authorized agent environ and threaded down into
        # AcpDuplexAdapter via serve_ndjson — never read from os.environ here.
        self._max_planning_turns = max_planning_turns
        self._interactive_recovery = interactive_recovery  # Plan 12.3, resolved with it
        self._client_mcp_runtime = client_mcp_runtime
        self._mcp_idle_seconds = mcp_idle_seconds
        self._monotonic_clock = monotonic_clock
        self._mcp_shutdown_task: asyncio.Task[Any] | None = None
        self._writer_shutdown_task: asyncio.Task[Any] | None = None
        self._process_lifecycle: ProcessLifecycle | None = None
        self._shutdown_failures: set[str] = set()
        self._serving_failure: BaseException | None = None
        self._cleanup_started = False
        self._cleanup_control_failure: tuple[str, BaseException] | None = None
        self._mcp_shutdown_outcome: ClientMcpShutdownOutcome | None = None
        self._serving_dedicated: DedicatedOutboundWriter | None = None
        self._serving_dedicated_owned = False
        self._conversation_sanitizer_inputs = conversation_sanitizer_inputs
        # Seam 2, checkpoint B: the serving process retains the Redis runtime the
        # bootstrap built, and closes it LAST in its own teardown. Before this seam the
        # runtime was reachable only through the runner's store and sink, with no close
        # handle anywhere in the serving graph (Plan 11.26 S1: MISSING on merged).
        self._redis_runtime = redis_runtime
        self._request_tasks: set[asyncio.Task[Any]] = set()

    @property
    def client_mcp_runtime(self) -> Any | None:
        return self._client_mcp_runtime

    @property
    def redis_runtime(self) -> Any | None:
        return self._redis_runtime

    @property
    def route_policy(self) -> Any | None:
        return self._route_policy

    @property
    def context_attachment(self) -> Any | None:
        return self._context_attachment

    @property
    def cleanup_failure_stages(self) -> tuple[str, ...]:
        return tuple(sorted(self._shutdown_failures))

    @property
    def serving_failure(self) -> BaseException | None:
        return self._serving_failure

    @property
    def cleanup_started(self) -> bool:
        return self._cleanup_started

    @property
    def cleanup_control_failure(self) -> tuple[str, BaseException] | None:
        return self._cleanup_control_failure

    def _remember_cleanup_failures(self, failures: list[tuple[str, BaseException]]) -> None:
        self._shutdown_failures.update(stage for stage, _exc in failures if stage != "serve")
        if self._cleanup_control_failure is None:
            self._cleanup_control_failure = next(((stage, exc) for stage, exc in failures
                if stage != "serve" and not isinstance(exc, Exception)), None)

    @property
    def mcp_shutdown_outcome(self) -> ClientMcpShutdownOutcome | None:
        return self._mcp_shutdown_outcome

    def _cleanup_phase(self, stage: str) -> None:
        self._cleanup_started = True
        if self._process_lifecycle is not None:
            self._process_lifecycle.begin_cleanup()
            self._process_lifecycle.record(ShutdownObservation(False, stage, 1, self.cleanup_failure_stages))

    async def _finish_cleanup_task(self, task: asyncio.Task[Any], *, stage: str) -> Any:
        cancelled: asyncio.CancelledError | None = None
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as exc:
                cancelled = cancelled or exc
            except BaseException:
                break
        if cancelled is not None:
            try:
                task.result()
            except BaseException as exc:
                raise_preserving_failure(cleanup_failure([("serve", cancelled), (stage, exc)]))
            raise_preserving_failure(cancelled)
        return task.result()

    async def _close_writer_stage(self, writer: DedicatedOutboundWriter | StdioByteWriter) -> None:
        self._cleanup_phase("writer")
        if self._writer_shutdown_task is None:
            self._writer_shutdown_task = asyncio.create_task(asyncio.to_thread(writer.close_and_join), name="optimus-writer-shutdown")
        await self._finish_cleanup_task(self._writer_shutdown_task, stage="writer")

    def _remember_mcp_outcome(self, outcome: Any) -> None:
        if isinstance(outcome, ClientMcpShutdownOutcome):
            self._mcp_shutdown_outcome = outcome
            if not (outcome.sdk_closed and outcome.endpoint_closed and outcome.supervisor_closed):
                self._shutdown_failures.add("mcp")
        else:
            self._shutdown_failures.add("mcp")

    async def _close_unused_mcp_stage(self) -> None:
        if self._client_mcp_runtime is None or self._mcp_shutdown_task is not None:
            return
        self._cleanup_phase("mcp")
        self._mcp_shutdown_task = asyncio.create_task(asyncio.to_thread(self._client_mcp_runtime.close), name="optimus-mcp-startup-shutdown")
        try:
            self._remember_mcp_outcome(await self._finish_cleanup_task(self._mcp_shutdown_task, stage="mcp"))
        except BaseException:
            self._shutdown_failures.add("mcp")
            raise

    async def _close_redis_runtime_stage(self) -> None:
        """The LAST teardown stage: observe the retained runtime's single teardown.

        Observed asynchronously through ``close_async`` so the ACP event loop is never
        blocked on a thread join; the observation is bounded by
        ``REDIS_SHUTDOWN_OBSERVATION_SECONDS`` and an expired budget leaves the runtime
        CLOSING with ownership retained. The outcome is CONSUMED, like the client-MCP
        outcome above it: a clean record reports nothing, and an incomplete or failed
        teardown produces exactly one content-free diagnostic. Nothing raises out of
        this stage -- it runs inside ``finally``, where a raise would replace the
        cancellation or exception that initiated teardown -- but BaseException is never
        absorbed.
        """
        runtime = self._redis_runtime
        if runtime is None:
            return
        self._cleanup_phase("redis")
        from optimus.redis.runtime import RedisRuntimeShutdownIncomplete

        outcome = "clean"
        try:
            record = await runtime.close_async(timeout=REDIS_SHUTDOWN_OBSERVATION_SECONDS)
            if not record.is_clean:
                outcome = "failed"
        except RedisRuntimeShutdownIncomplete:
            # The observation budget expired; the teardown and its owner are retained.
            # Deliberately not `except TimeoutError`: a resource stage that failed WITH a
            # TimeoutError is republished by close_async as that error and is a
            # completed-but-failed teardown, not an incomplete one.
            outcome = "incomplete"
        except Exception:  # noqa: BLE001 - a resource-stage failure republished by close_async
            outcome = "failed"
        if outcome != "clean":
            if outcome == "failed":
                self._shutdown_failures.add("redis")
            report_redis_cleanup_incomplete(runtime, outcome)

    @property
    def conversation_sanitizer_inputs(self) -> Any | None:
        return self._conversation_sanitizer_inputs

    async def handle_one(self, reader: AsyncByteReader, writer: AsyncByteWriter) -> None:
        # reader/writer are typed by Protocol: no shared base class required.
        try:
            request = await read_message(reader)
            response = self._dispatcher.dispatch(request)
        except FramingError as exc:
            response = error_response(
                request_id=None,
                error=JsonRpcError(code=exc.code, message=str(exc)),
            )
        writer.write(encode_message(response))
        await writer.drain()

    async def serve(self, reader: AsyncByteReader, writer: AsyncByteWriter, *, lifecycle: ProcessLifecycle | None = None) -> None:
        # Seam 2, checkpoint B (round 2, R1): custody protection begins the moment this
        # server is entered. Nothing runs outside this try, so a failure anywhere --
        # setup, serving or an earlier cleanup -- still reaches the Redis stage below.
        self._process_lifecycle = lifecycle
        failures: list[tuple[str, BaseException]] = []
        try:
            try:
                await self._serve_framed(reader, writer)
            except BaseException as exc:
                self._serving_failure = exc
                failures.append(("serve", exc))
        finally:
            self._cleanup_phase("mcp")
            try:
                await self._close_unused_mcp_stage()
            except BaseException as exc:
                failures.append(("mcp", exc))
            try:
                if isinstance(writer, StdioByteWriter):
                    await self._close_writer_stage(writer)
            except BaseException as exc:
                failures.append(("writer", exc))
            if isinstance(reader, _StdioReadFacade):
                reader.request_close()
            try:
                await self._close_redis_runtime_stage()
            except BaseException as exc:
                failures.append(("redis", exc))
        self._remember_cleanup_failures(failures)
        if failures:
            raise_preserving_failure(cleanup_failure(failures))

    async def _serve_framed(self, reader: AsyncByteReader, writer: AsyncByteWriter) -> None:
        while True:
            try:
                request = await read_message(reader)
            except FramingError as exc:
                if str(exc) == "unexpected end of stream":
                    return
                response = error_response(
                    request_id=None,
                    error=JsonRpcError(code=exc.code, message=str(exc)),
                )
                writer.write(encode_message(response))
                await writer.drain()
                if str(exc) in {"body too large", "header too large"}:
                    return
                continue
            response = self._dispatcher.dispatch(request)
            writer.write(encode_message(response))
            await writer.drain()

    async def serve_ndjson(
        self,
        reader: NdjsonLineReader,
        writer: NdjsonLineWriter,
        *,
        dedicated_writer: DedicatedOutboundWriter | None = None,
        notice_control: NoticeControl | None = None,
        join_dedicated_writer: bool = True,
        lifecycle: ProcessLifecycle | None = None,
    ) -> None:
        # Seam 2, checkpoint B (round 2, R1): the retained Redis runtime is closed by THIS
        # finally, which encloses setup, serving and every earlier teardown stage. The
        # previous placement -- last statement inside the serving finally -- was skipped
        # whenever adapter construction or an earlier cleanup stage raised, stranding a
        # live owner with no teardown record. The stage order is unchanged on the normal
        # path (adapter, MCP runtime, owned writer, reader decision, then Redis); on a
        # failing path the earlier stages keep their own outcomes and the failure they
        # raised, and Redis is still closed afterwards -- never before them.
        self._process_lifecycle = lifecycle
        failures: list[tuple[str, BaseException]] = []
        try:
            try:
                await self._serve_ndjson(
                    reader,
                    writer,
                    dedicated_writer=dedicated_writer,
                    notice_control=notice_control,
                    join_dedicated_writer=join_dedicated_writer,
                )
            except BaseException as exc:
                if not self._cleanup_started:
                    self._serving_failure = exc
                failures.append(("serve", exc))
        finally:
            self._cleanup_phase("mcp")
            try:
                await self._close_unused_mcp_stage()
            except BaseException as exc:
                failures.append(("mcp", exc))
            try:
                if self._serving_dedicated_owned and self._serving_dedicated is not None and self._writer_shutdown_task is None:
                    await self._close_writer_stage(self._serving_dedicated)
            except BaseException as exc:
                failures.append(("writer", exc))
            if isinstance(reader, _StdioReadFacade):
                reader.request_close()
            try:
                await self._close_redis_runtime_stage()
            except BaseException as exc:
                failures.append(("redis", exc))
        self._remember_cleanup_failures(failures)
        if failures:
            raise_preserving_failure(cleanup_failure(failures))

    async def _serve_ndjson(
        self,
        reader: NdjsonLineReader,
        writer: NdjsonLineWriter,
        *,
        dedicated_writer: DedicatedOutboundWriter | None,
        notice_control: NoticeControl | None,
        join_dedicated_writer: bool,
    ) -> None:
        log_provenance_once()
        agent_runner = self._dispatcher.agent_runner
        if agent_runner is None:
            raise RuntimeError("agent runner not configured for ndjson ACP serving")
        workspace_root = self._dispatcher.workspace_root or Path.cwd()
        notice = notice_control or NoticeControl()
        physical = writer if hasattr(writer, "write_bytes") and hasattr(writer, "flush") else None
        owned_dedicated = dedicated_writer is None or (self._process_lifecycle is not None and join_dedicated_writer)
        dedicated = dedicated_writer
        if dedicated is None and physical is not None:
            dedicated = DedicatedOutboundWriter(physical, limits=self._admission_limits)  # type: ignore[arg-type]
            self._serving_dedicated = dedicated
            self._serving_dedicated_owned = join_dedicated_writer
            dedicated.start()
            owned_dedicated = True
        self._serving_dedicated = dedicated
        self._serving_dedicated_owned = owned_dedicated and join_dedicated_writer
        outbound = NdjsonOutboundChannel(writer, dedicated_writer=dedicated)
        sessions = InMemoryAcpSpecSessionStore()
        adapter = AcpDuplexAdapter(
            runner=agent_runner,
            workspace_root=workspace_root,
            sessions=sessions,
            outbound=outbound,
            max_planning_turns=self._max_planning_turns,
            interactive_recovery=self._interactive_recovery,
            client_mcp_runtime=self._client_mcp_runtime,
            sanitizer_inputs=self._conversation_sanitizer_inputs,
            notice_control=notice,
            settlement_sink=getattr(agent_runner, "event_sink", None),
            route_policy=self._route_policy,
            context_attachment=self._context_attachment,
            session_seeder=self._session_seeder,
            failure_telemetry=self._failure_telemetry,
            auto_router=self._auto_router,
            mcp_idle_seconds=self._mcp_idle_seconds,
            monotonic_clock=self._monotonic_clock,
        )
        limits = self._admission_limits
        message_queue: asyncio.Queue[tuple[dict[str, Any], Reservation]] = asyncio.Queue(maxsize=limits.pending_items)
        prompt_queue: asyncio.Queue[tuple[dict[str, Any], Reservation]] = asyncio.Queue(maxsize=limits.pending_items)
        pending_count = 0
        active = [0, 0]
        prompt_sessions: set[str] = set()
        inbound = AdmissionAccount(count=limits.pending_items + limits.active_prompts + limits.active_requests, bytes=limits.inbound_bytes)
        self._inbound_admission = inbound
        wake = asyncio.Event()
        reader_done = False
        reader_failure: Exception | None = None
        control_task: asyncio.Task[None] | None = None
        request_tasks: set[asyncio.Task[Any]] = set()
        serving_task = asyncio.current_task()
        serving_loop = asyncio.get_running_loop()
        stop_requested = False
        if dedicated is not None:
            def apply_required_stop() -> None:
                nonlocal stop_requested
                if reader_done or stop_requested:
                    return
                stop_requested = True
                if self._process_lifecycle is not None and self._process_lifecycle.bound:
                    self._process_lifecycle.request_stop(StopReason.ERROR)
                elif serving_task is not None and not serving_task.done():
                    serving_task.cancel()

            def required_failed() -> None:
                try:
                    serving_loop.call_soon_threadsafe(apply_required_stop)
                except RuntimeError:
                    return  # Loop loss cannot be repaired by a writer callback.
            dedicated.set_admission_failure_callback(required_failed)

        async def submit_via_notice(payload: Mapping[str, Any], *, handle: Any | None = None, observe: bool = True) -> None:
            if dedicated is None:
                await writer.write_line(payload)
                return
            response_handle = handle or notice.allocate_response_handle(ResponseKind.ORDINARY)
            ticket = response_handle.start_non_turn_response_send()
            if ticket.immediate_completion is not None:
                response_handle.finalize_once(ticket.immediate_completion)
                return
            assert ticket.source_future is not None
            item = OutboundQueueItem(
                payload=payload,
                send_key=ticket.send_key,
                owner=response_handle,
                source_future=ticket.source_future,
                writer_token=ticket.writer_token,
                handle=response_handle,
            )
            dedicated.submit(item)
            if not observe:
                def finalize(source: concurrent.futures.Future[SendCompletion]) -> None:
                    if not source.cancelled():
                        response_handle.finalize_once(source.result())
                ticket.source_future.add_done_callback(finalize)
                return
            try:
                loop = asyncio.get_running_loop()
                completion = await asyncio.shield(
                    asyncio.wrap_future(ticket.source_future, loop=loop)
                )
            except asyncio.CancelledError:
                # Server-task cancellation: do not wait for the writer future.
                response_handle.freeze_abandoned()
                response_handle.finalize_once(
                    SendCompletion(send_key=ticket.send_key, outcome=SendOutcome.SUPPRESSED)
                )
                raise
            response_handle.finalize_once(completion)

        async def submit_via_turn(payload: Mapping[str, Any], turn_control: TurnControl) -> bool:
            lease = turn_control.start_response_send()
            if not lease.granted or lease.send_key is None:
                return False
            if dedicated is None:
                turn_control.claim_write_started(lease.send_key)
                try:
                    await writer.write_line(payload)
                except BaseException:
                    turn_control.publish_authoritative(lease.send_key, SendOutcome.AMBIGUOUS)
                    raise
                turn_control.publish_authoritative(lease.send_key, SendOutcome.FLUSHED)
                return True
            source_future: concurrent.futures.Future[Any] = concurrent.futures.Future()
            item = OutboundQueueItem(
                payload=payload,
                send_key=lease.send_key,
                owner=turn_control,
                source_future=source_future,
                writer_token=None,
                handle=None,
            )
            try:
                dedicated.submit(item)
            except Exception:
                turn_control.publish_authoritative(lease.send_key, SendOutcome.CONCLUSIVE_FAILURE)
                raise
            try:
                loop = asyncio.get_running_loop()
                completion = await asyncio.shield(asyncio.wrap_future(source_future, loop=loop))
            except asyncio.CancelledError:
                turn_control.request_transport_teardown()
                raise
            return (completion.outcome is SendOutcome.FLUSHED
                    and turn_control.rpc_response_delivery is RpcResponseDelivery.FLUSHED)

        async def deliver_envelope(envelope: Any, ownership_slot: ResponseOwnershipSlot) -> bool:
            wire = envelope.response
            if isinstance(envelope, TurnResponseEnvelope):
                if ownership_slot.is_bound and ownership_slot.turn_control is not envelope.turn_control:
                    raise SettlementInvariantError("envelope turn control does not match ownership slot")
                return await submit_via_turn(wire, envelope.turn_control)
            if not isinstance(envelope, NonTurnResponseEnvelope):
                raise SettlementInvariantError("unknown response envelope kind")
            if ownership_slot.is_bound:
                raise SettlementInvariantError("non-turn envelope returned for bound ownership slot")
            await submit_via_notice(wire, handle=envelope.response_handle)
            return True

        async def read_lines() -> None:
            nonlocal pending_count, reader_done, reader_failure, control_task
            try:
                while not reader_done:
                    if isinstance(reader, StdioNdjsonLineReader) and reader.supports_limited_read:
                        line = await reader.readline_limited(limits.frame_bytes)
                    else:
                        line = await reader.readline()
                    if reader_done:
                        return
                    if line == b"":
                        return
                    if len(line.removesuffix(b"\n").removesuffix(b"\r")) > limits.frame_bytes:
                        raise FramingError("body too large", code=INVALID_REQUEST)
                    size = len(line)
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        message = json.loads(stripped.decode("utf-8"))
                    except json.JSONDecodeError as exc:
                        print(f"optimus.acp: invalid ndjson line: {sanitize_protocol_error_message(str(exc))}", file=sys.stderr)
                        return
                    if not isinstance(message, dict):
                        continue
                    if "method" in message and "id" not in message:
                        if message.get("method") == "session/cancel":
                            params = message.get("params")
                            session_id = params.get("sessionId") if isinstance(params, dict) else None
                            if isinstance(session_id, str):
                                cancelled_messages = []
                                for _ in range(prompt_queue.qsize()):
                                    queued, reservation = prompt_queue.get_nowait()
                                    queued_params = queued.get("params")
                                    if isinstance(queued_params, dict) and queued_params.get("sessionId") == session_id:
                                        pending_count -= 1
                                        cancelled_messages.append((queued.get("id"), reservation))
                                    else:
                                        prompt_queue.put_nowait((queued, reservation))
                                try:
                                    for request_id, _ in cancelled_messages:
                                        await submit_via_notice({"jsonrpc": "2.0", "id": request_id, "result": {"stopReason": "cancelled"}}, observe=False)
                                finally:
                                    for _, reservation in cancelled_messages:
                                        reservation.release()
                            if control_task is not None:
                                await asyncio.shield(control_task)
                            control_task = asyncio.create_task(adapter.handle_client_notification(message))
                            control_task.add_done_callback(lambda _task: wake.set())
                            wake.set()
                        else:
                            self._ignored_notifications = min(2**63 - 1, self._ignored_notifications + 1)
                            await asyncio.sleep(0)
                        continue
                    if "id" in message and ("result" in message or "error" in message) and "method" not in message:
                        if isinstance(message.get("id"), (str, int)):
                            if debug_trace_enabled():
                                acp_debug_log(
                                    location="server.py:serve_ndjson:inbound_client_response_raw",
                                    message="raw inbound id-bearing client response before deliver_client_response",
                                    data=_inbound_response_payload(message),
                                    hypothesis_id="H2-REPLY",
                                )
                            outbound.deliver_client_response(message)
                        continue
                    if "method" not in message or "id" not in message:
                        continue
                    params = message.get("params")
                    session_id = params.get("sessionId") if isinstance(params, dict) else None
                    if message.get("method") == "session/prompt" and isinstance(session_id, str):
                        prior = adapter._active_turns.get(session_id)
                        if prior is not None and prior.turn_control.rpc_response_delivery is not RpcResponseDelivery.FLUSHED:
                            envelope = await adapter.handle_client_request(message)
                            assert isinstance(envelope, NonTurnResponseEnvelope)
                            await submit_via_notice(envelope.response, handle=envelope.response_handle, observe=False)
                            continue
                    admission_reservation = None if pending_count >= limits.pending_items else inbound.try_reserve(1, size, AdmissionClass.ORDINARY)
                    if admission_reservation is None:
                        await submit_via_notice(error_response(message.get("id"), JsonRpcError(code=REQUEST_CANCELLED, message="Server busy", data={"reason": "QUEUE_FULL"})), observe=False)
                        continue
                    if message.get("method") == "session/prompt":
                        prompt_queue.put_nowait((message, admission_reservation))
                    else:
                        message_queue.put_nowait((message, admission_reservation))
                    pending_count += 1
                    wake.set()
                    await asyncio.sleep(0)  # One scheduler gets a turn even with an always-ready injected reader.
            except FramingError as exc:
                reader_failure = exc
            except Exception as exc:
                reader_failure = exc
                try:
                    print(f"optimus.acp: ndjson reader failed: {sanitize_protocol_error_message(str(exc))}", file=sys.stderr)
                except Exception:
                    return  # The retained reader failure remains primary if reporting fails.
            finally:
                reader_done = True
                wake.set()

        def approved_method_category(method: object) -> str:
            # Never copy arbitrary client content into a diagnostic: an unapproved method
            # collapses to "unknown" rather than being echoed.
            return method if isinstance(method, str) and method in APPROVED_METHOD_CATEGORIES else "unknown"

        def report_request_task_failure(operation_id: str, request_method: str) -> None:
            # One content-free diagnostic per escaped request-task failure. This runs from a
            # done-callback: it must never raise into the loop, deliver a response, retry work,
            # or alter settlement -- so it is fully contained and writes nothing but the
            # operation id and the approved method category.
            try:
                acp_debug_log(
                    location="server.py:serve_ndjson:request_task_failed",
                    message="request task failed",
                    data={"operation_id": operation_id, "request_method": request_method},
                )
                if not debug_trace_enabled():
                    # With trace off the failure would otherwise be silently lost; surface a
                    # content-free line so it is still observable.
                    print(
                        f"optimus.acp: request task failed operation_id={operation_id} method={request_method}",
                        file=sys.stderr,
                    )
            except Exception:
                return

        def on_request_task_done(task: asyncio.Task[Any], *, operation_id: str, request_method: str) -> None:
            # Both schedules pass through here: a task that fails while serving, and one whose
            # cancellation cleanup raises at shutdown. Retrieving the exception here also keeps
            # a "never retrieved" warning from escaping. Successful completion and ordinary
            # cancellation are not failures.
            request_tasks.discard(task)
            if task.cancelled():
                return
            if task.exception() is None:
                return
            report_request_task_failure(operation_id, request_method)

        def report_reader_incomplete() -> None:
            # One content-free attempt to record that the reader wrapper had not completed at
            # the ownership decision. Contained like the request-task reporter above: this runs
            # inside `finally`, where a raise would replace the cancellation or exception that
            # initiated teardown. It does not claim a physical thread was proven blocked.
            try:
                acp_debug_log(
                    location="server.py:serve_ndjson:reader_incomplete",
                    message="reader wrapper had not completed at the ownership decision",
                    data={"reader_state": "incomplete"},
                )
            except Exception:
                return

        def classify_mcp_cleanup(outcome: object) -> str:
            # "clean" | "incomplete" | "invalid". Only a genuine outcome instance whose
            # `complete` is exactly True is clean. None and a foreign object (even one that
            # declares itself complete) are invalid; a genuine non-complete outcome is
            # incomplete; an ABSENT runtime is handled by the caller instead. Reading
            # `complete` on a genuine instance is part of the diagnostic boundary: an
            # ordinary failure there is contained and classified as invalid, so the report
            # and the remaining teardown still run. BaseException is never absorbed.
            try:
                if not isinstance(outcome, ClientMcpShutdownOutcome):
                    return "invalid"
                return "clean" if outcome.complete is True else "incomplete"
            except Exception:
                return "invalid"

        def report_mcp_cleanup_incomplete(outcome: "ClientMcpShutdownOutcome | None", status: str) -> None:
            # One content-free attempt to record that client-MCP cleanup did not complete.
            # Contained like the reporters above -- this runs inside `finally`, where a raise
            # would replace the cancellation or exception that initiated teardown. The stage
            # fields are read lazily, by the sink, only with tracing enabled and inside its
            # failure boundary, so a failing field access is contained too and no field is
            # read at all with tracing off. Classification happened at the caller and is not
            # deferred. Only the three stage booleans and a real MCPSupervisorState value are
            # ever echoed; an invalid or foreign result degrades to fixed sentinels so no
            # arbitrary content can reach the diagnostic. The outcome is never changed by
            # logging.
            def payload() -> dict[str, Any]:
                if status == "incomplete" and outcome is not None:
                    state = outcome.supervisor_state
                    return {
                        "sdk_closed": outcome.sdk_closed is True,
                        "endpoint_closed": outcome.endpoint_closed is True,
                        "supervisor_closed": outcome.supervisor_closed is True,
                        "supervisor_state": state.value if isinstance(state, MCPSupervisorState) else "unknown",
                    }
                return {
                    "sdk_closed": False,
                    "endpoint_closed": False,
                    "supervisor_closed": False,
                    "supervisor_state": "unknown",
                }

            try:
                acp_debug_log(
                    location="server.py:serve_ndjson:mcp_cleanup_incomplete",
                    message="client MCP cleanup incomplete at teardown",
                    data=payload,
                )
            except Exception:
                return

        async def process_request(message: dict[str, Any], operation_id: str) -> None:
            request_id = message.get("id")
            method = message.get("method")
            pending_permission_id = outbound.last_outbound_request_id
            ownership_slot = ResponseOwnershipSlot()
            try:
                # region agent log
                if debug_trace_enabled():
                    acp_debug_log(
                        location="server.py:process_request:entry",
                        message="handling client request",
                        data=lambda: {
                            "request_id": request_id,
                            "method": method,
                            "pending_permission_id": pending_permission_id,
                            "operation_id": operation_id,
                        },
                        hypothesis_id="H4",
                    )
                # endregion
                envelope = await adapter.handle_client_request(message, ownership_slot=ownership_slot)
                wire = envelope.response
                # region agent log
                if debug_trace_enabled():
                    acp_debug_log(
                        location="server.py:process_request:exit",
                        message="client request handled",
                        data=lambda: {
                            "request_id": request_id,
                            "method": method,
                            "has_error": "error" in wire,
                            "stop_reason": wire.get("result", {}).get("stopReason")
                            if isinstance(wire.get("result"), dict)
                            else None,
                        },
                        hypothesis_id="H4",
                    )
                # endregion
                delivered = await deliver_envelope(envelope, ownership_slot)
                if isinstance(envelope, TurnResponseEnvelope):
                    adapter.note_turn_delivered(envelope.turn_control, cancelled=not delivered)
            except asyncio.CancelledError:
                if ownership_slot.turn_control is not None:
                    ownership_slot.turn_control.request_transport_teardown()
                raise
            except AcpOutboundError as exc:
                error_payload = error_response(
                    request_id=request_id,
                    error=JsonRpcError(code=exc.code, message=exc.message, data=exc.data),
                )
                if ownership_slot.turn_control is not None:
                    await submit_via_turn(error_payload, ownership_slot.turn_control)
                else:
                    await submit_via_notice(error_payload)
            except Exception as exc:
                # region agent log
                # Literal message; the exception text is deferred into the redacted payload.
                # The protocol/stderr formatting of the same exception below is separate.
                acp_debug_log(
                    location="server.py:process_request:exception",
                    message="client request failed",
                    data=_request_failure_payload(exc, request_id, method, pending_permission_id, lambda exc: str(exc)),
                    hypothesis_id="H4",
                )
                # endregion
                print(
                    f"optimus.acp: process_request failed id={request_id!r} method={method!r} "
                    f"pending_permission_id={pending_permission_id!r}: {sanitize_protocol_error_message(str(exc))}",
                    file=sys.stderr,
                )
                error_payload = error_response(
                    request_id=request_id,
                    error=JsonRpcError(code=INTERNAL_ERROR, message=sanitize_protocol_error_message(str(exc))),
                )
                if ownership_slot.turn_control is not None:
                    await submit_via_turn(error_payload, ownership_slot.turn_control)
                else:
                    await submit_via_notice(error_payload)

            finally:
                try:
                    control = ownership_slot.turn_control
                    if control is not None:
                        try:
                            current_task = asyncio.current_task()
                            if current_task is not None and current_task.cancelling():
                                control.request_transport_teardown()
                        finally:
                            control.finalize_once()
                finally:
                    params = message.get("params")
                    session_id = params.get("sessionId") if isinstance(params, dict) else None
                    if method == "session/prompt" and isinstance(session_id, str):
                        prompt_sessions.discard(session_id)
                    wake.set()

        async def owned_request(message: dict[str, Any], operation_id: str) -> None:
            workers: set[asyncio.Task[Any]] = set()
            token = request_worker_custody.set(workers)
            try:
                await process_request(message, operation_id)
            finally:
                request_worker_custody.reset(token)
                cancelled: asyncio.CancelledError | None = None
                for worker in tuple(workers):
                    while not worker.done():
                        try:
                            await asyncio.shield(worker)
                        except asyncio.CancelledError as exc:
                            cancelled = exc
                        except BaseException:
                            break
                if cancelled is not None:
                    raise cancelled

        adapter.start_idle_mcp_sweeper()
        reader_task = asyncio.create_task(read_lines())
        primary_failure: BaseException | None = None
        try:
            while True:
                await wake.wait()
                wake.clear()
                if control_task is not None:
                    await asyncio.shield(control_task)
                if reader_done:
                    if reader_failure is not None:
                        if self._process_lifecycle is not None:
                            self._process_lifecycle.request_stop(StopReason.ERROR)
                        raise reader_failure
                    break
                for index, (target, capacity) in enumerate(((message_queue, limits.active_requests), (prompt_queue, limits.active_prompts))):
                    # Complete the rotation even at capacity so deferred prompts keep FIFO order.
                    for _ in range(target.qsize()):
                        # Keep concrete receivers visible to the source-bound queue inventory.
                        message, reservation = message_queue.get_nowait() if index == 0 else prompt_queue.get_nowait()
                        params = message.get("params")
                        session_id = params.get("sessionId") if isinstance(params, dict) else None
                        if active[index] >= capacity or (index == 1 and isinstance(session_id, str)
                                and session_id in prompt_sessions):
                            if index == 0:
                                message_queue.put_nowait((message, reservation))
                            else:
                                prompt_queue.put_nowait((message, reservation))
                            continue
                        if index == 1 and isinstance(session_id, str):
                            prompt_sessions.add(session_id)
                        pending_count -= 1
                        active[index] += 1
                        def release_request(task: asyncio.Task[Any], *, reservation: Reservation = reservation, index: int = index) -> None:
                            reservation.release()
                            active[index] -= 1
                            wake.set()
                    # Mint the operation id once here, before the task exists, so the same id
                    # can be bound into the completion observer without a late-bound loop
                    # variable, and threaded into process_request for its own diagnostics.
                        operation_id = uuid.uuid4().hex
                        request_method = approved_method_category(message.get("method"))
                        task = asyncio.create_task(owned_request(message, operation_id))
                        request_tasks.add(task)
                        task.add_done_callback(release_request)
                        task.add_done_callback(
                            functools.partial(
                                on_request_task_done, operation_id=operation_id, request_method=request_method
                            )
                        )
        except BaseException as exc:
            primary_failure = exc
            self._serving_failure = exc
        finally:
            reader_done = True
            if dedicated is not None:
                dedicated.set_admission_failure_callback(None)
            inbound.close()
            for target in (message_queue, prompt_queue):
                while not target.empty():
                    _, reservation = target.get_nowait()
                    reservation.release()
            self._cleanup_phase("mcp")
            failures: list[tuple[str, BaseException]] = [] if primary_failure is None else [("serve", primary_failure)]
            # Transport-loss ordering: abandon notices before cancelling request tasks.
            notice.mark_transport_abandoned()
            for turn in list(adapter._active_turns.values()):  # noqa: SLF001
                turn.turn_control.request_transport_teardown()
            adapter._cancel_loop_work()  # loop-affine permissions and reservations precede worker teardown
            for task in list(request_tasks):
                task.cancel()
            mcp_outcome: Any = None
            mcp_failed = False
            async def shutdown_mcp() -> None:
                nonlocal mcp_outcome, mcp_failed
                try:
                    if control_task is not None:
                        if not control_task.done():
                            control_task.cancel()
                        await asyncio.gather(control_task, return_exceptions=True)
                    if request_tasks:
                        await asyncio.gather(*request_tasks, return_exceptions=True)
                except BaseException as exc:
                    failures.append(("request", exc))
                    mcp_failed = True
                try:
                    await adapter.aclose()
                except BaseException as exc:
                    failures.append(("adapter", exc))
                    mcp_failed = True
                try:
                    if self._client_mcp_runtime is not None:
                        mcp_outcome = await asyncio.to_thread(self._client_mcp_runtime.close)
                        self._remember_mcp_outcome(mcp_outcome)
                except BaseException as exc:
                    failures.append(("mcp", exc))
                    self._shutdown_failures.add("mcp")
                    mcp_failed = True
            self._mcp_shutdown_task = asyncio.create_task(shutdown_mcp(), name="optimus-mcp-shutdown")
            teardown_cancelled: asyncio.CancelledError | None = None
            while not self._mcp_shutdown_task.done():
                try:
                    await asyncio.shield(self._mcp_shutdown_task)
                except asyncio.CancelledError as exc:
                    if teardown_cancelled is None:
                        teardown_cancelled = exc
                except BaseException:
                    break  # Retrieve the task's original failure below, then finish the owned stages.
            try:
                self._mcp_shutdown_task.result()
            except BaseException as exc:
                failures.append(("mcp", exc))
                mcp_failed = True
            # Client-MCP cleanup outcome. The runtime attempts every stage and returns an
            # aggregate result; consuming it here means an incomplete-but-non-raising cleanup
            # (a supervisor still draining, a contained stage failure) is reported instead of
            # passing silently. Only an absent runtime is an implicit clean/no-resource case.
            # The report is made right here, before the later stages, so it is attempted
            # whenever the runtime returned; later stages keep their existing order.
            try:
                if self._client_mcp_runtime is not None:
                    mcp_status = classify_mcp_cleanup(mcp_outcome)
                    if mcp_failed and mcp_status == "clean":
                        mcp_status = "incomplete"
                    if mcp_status != "clean":
                        report_mcp_cleanup_incomplete(
                            mcp_outcome if mcp_status == "incomplete" and isinstance(mcp_outcome, ClientMcpShutdownOutcome) else None,
                            mcp_status,
                        )
            except BaseException as exc:
                failures.append(("mcp", exc))
            try:
                if dedicated is not None and owned_dedicated and join_dedicated_writer:
                    await self._close_writer_stage(dedicated)
            except BaseException as exc:
                failures.append(("writer", exc))
            # Reader ownership at teardown. The cooperative path is EOF: `read_lines` put its
            # sentinel and returned, so `reader_task` is already done -- await it (immediate,
            # surfacing any reader error) and complete the full shutdown. But when teardown is
            # driven by cancellation or an exception, the wrapper may not have completed and a
            # physical `readline` can still be running inside the default executor. Awaiting it
            # would park teardown on input that may never arrive, so instead stop the async
            # reader and record that it had not completed. The blocking read stays owned by the
            # executor until it returns on its own (e.g. when the client closes stdin): we do
            # not close shared stdin, do not reclassify incomplete input as EOF, and do not
            # claim a bounded process exit -- only that this await no longer stalls teardown.
            try:
                if isinstance(reader, _StdioReadFacade):
                    reader.request_close()
                if reader_task.done():
                    await reader_task
                else:
                    reader_task.cancel()
                    report_reader_incomplete()
            except BaseException as exc:
                failures.append(("reader", exc))
            if teardown_cancelled is not None:
                failures.append(("serve", teardown_cancelled))
            self._remember_cleanup_failures(failures)
            if failures:
                raise_preserving_failure(cleanup_failure(failures))
            # Seam 2, checkpoint B: the Redis runtime is closed LAST by the enclosing
            # `serve_ndjson` finally, after every stage above that may still submit work
            # to it -- and still closed when one of those stages raises.
