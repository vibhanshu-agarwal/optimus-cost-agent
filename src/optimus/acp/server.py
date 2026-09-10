from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import json
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from optimus.acp.debug_trace import acp_debug_log, debug_trace_enabled, log_provenance_once
from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.errors import (
    INTERNAL_ERROR,
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
from optimus.acp.outbound_writer import DedicatedOutboundWriter, OutboundQueueItem
from optimus.acp.settlement import SendOutcome, SettlementInvariantError
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore
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


class StdioByteReader:
    def __init__(self, stream: object) -> None:
        self._stream = stream

    async def read(self, size: int) -> bytes:
        return await asyncio.to_thread(self._stream.read, size)


class StdioByteWriter:
    def __init__(self, stream: object) -> None:
        self._stream = stream

    def write(self, data: bytes) -> None:
        self._stream.write(data)

    async def drain(self) -> None:
        await asyncio.to_thread(self._stream.flush)


class StdioNdjsonLineReader:
    def __init__(self, stream: object) -> None:
        self._stream = stream

    async def readline(self) -> bytes:
        return await asyncio.to_thread(self._stream.readline)


class StdioNdjsonLineWriter:
    def __init__(self, stream: object) -> None:
        self._stream = stream

    def write_bytes(self, data: bytes) -> None:
        self._stream.write(data)

    def flush(self) -> None:
        self._stream.flush()

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

    async def _submit_payload(self, message: Mapping[str, Any], *, kind: str) -> None:
        if self._dedicated_writer is None:
            await self._writer.write_line(message)
            return
        from optimus.acp.outbound_writer import (
            EphemeralSendOwner,
            OutboundQueueItem,
            next_ephemeral_send_key,
        )

        owner = EphemeralSendOwner()
        send_key = next_ephemeral_send_key(kind)
        owner.create_queued(send_key)
        source = concurrent.futures.Future()
        item = OutboundQueueItem(
            payload=message,
            send_key=send_key,
            owner=owner,
            source_future=source,
        )
        self._dedicated_writer.submit(item)
        loop = asyncio.get_running_loop()
        completion = await asyncio.shield(asyncio.wrap_future(source, loop=loop))
        if completion.outcome is SendOutcome.CONCLUSIVE_FAILURE:
            raise AcpOutboundError(code=INTERNAL_ERROR, message="outbound delivery failed")

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        # region agent log
        if debug_trace_enabled():
            acp_debug_log(
                location="server.py:NdjsonOutboundChannel.notify",
                message="outbound notification",
                data=lambda: {"method": method, "param_keys": sorted(params.keys())},
                hypothesis_id="H2",
            )
        # endregion
        await self._submit_payload(
            {"jsonrpc": "2.0", "method": method, "params": params},
            kind="notify",
        )

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
        await self._submit_payload(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            kind="request",
        )
        return await future

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
        client_mcp_runtime: Any | None = None,
        conversation_sanitizer_inputs: Any | None = None,
        redis_runtime: Any | None = None,
    ) -> None:
        self._dispatcher = dispatcher or JsonRpcDispatcher()
        # Plan 9.96, Task 5 Step 2: resolved once by build_configured_server()
        # from the authorized agent environ and threaded down into
        # AcpDuplexAdapter via serve_ndjson — never read from os.environ here.
        self._max_planning_turns = max_planning_turns
        self._client_mcp_runtime = client_mcp_runtime
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

    async def serve(self, reader: AsyncByteReader, writer: AsyncByteWriter) -> None:
        # Seam 2, checkpoint B (round 2, R1): custody protection begins the moment this
        # server is entered. Nothing runs outside this try, so a failure anywhere --
        # setup, serving or an earlier cleanup -- still reaches the Redis stage below.
        try:
            await self._serve_framed(reader, writer)
        finally:
            await self._close_redis_runtime_stage()

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
    ) -> None:
        # Seam 2, checkpoint B (round 2, R1): the retained Redis runtime is closed by THIS
        # finally, which encloses setup, serving and every earlier teardown stage. The
        # previous placement -- last statement inside the serving finally -- was skipped
        # whenever adapter construction or an earlier cleanup stage raised, stranding a
        # live owner with no teardown record. The stage order is unchanged on the normal
        # path (adapter, MCP runtime, owned writer, reader decision, then Redis); on a
        # failing path the earlier stages keep their own outcomes and the failure they
        # raised, and Redis is still closed afterwards -- never before them.
        try:
            await self._serve_ndjson(
                reader,
                writer,
                dedicated_writer=dedicated_writer,
                notice_control=notice_control,
                join_dedicated_writer=join_dedicated_writer,
            )
        finally:
            await self._close_redis_runtime_stage()

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
        owned_dedicated = dedicated_writer is None
        dedicated = dedicated_writer
        if dedicated is None and physical is not None:
            dedicated = DedicatedOutboundWriter(physical)  # type: ignore[arg-type]
            dedicated.start()
            owned_dedicated = True
        outbound = NdjsonOutboundChannel(writer, dedicated_writer=dedicated)
        sessions = InMemoryAcpSpecSessionStore()
        adapter = AcpDuplexAdapter(
            runner=agent_runner,
            workspace_root=workspace_root,
            sessions=sessions,
            outbound=outbound,
            max_planning_turns=self._max_planning_turns,
            client_mcp_runtime=self._client_mcp_runtime,
            sanitizer_inputs=self._conversation_sanitizer_inputs,
            notice_control=notice,
            settlement_sink=getattr(agent_runner, "event_sink", None),
        )
        message_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        request_tasks: set[asyncio.Task[Any]] = set()

        async def submit_via_notice(payload: Mapping[str, Any], *, handle: Any | None = None) -> None:
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

        async def submit_via_turn(payload: Mapping[str, Any], turn_control: TurnControl) -> None:
            lease = turn_control.start_response_send()
            if not lease.granted or lease.send_key is None:
                return
            if dedicated is None:
                await writer.write_line(payload)
                turn_control.publish_authoritative(lease.send_key, SendOutcome.FLUSHED)
                return
            source_future: concurrent.futures.Future[Any] = concurrent.futures.Future()
            item = OutboundQueueItem(
                payload=payload,
                send_key=lease.send_key,
                owner=turn_control,
                source_future=source_future,
                writer_token=None,
                handle=None,
            )
            dedicated.submit(item)
            try:
                loop = asyncio.get_running_loop()
                await asyncio.shield(asyncio.wrap_future(source_future, loop=loop))
            except asyncio.CancelledError:
                return

        async def deliver_envelope(envelope: Any, ownership_slot: ResponseOwnershipSlot) -> None:
            wire = envelope.response
            if isinstance(envelope, TurnResponseEnvelope):
                if ownership_slot.is_bound and ownership_slot.turn_control is not envelope.turn_control:
                    raise SettlementInvariantError("envelope turn control does not match ownership slot")
                await submit_via_turn(wire, envelope.turn_control)
                return
            if not isinstance(envelope, NonTurnResponseEnvelope):
                raise SettlementInvariantError("unknown response envelope kind")
            if ownership_slot.is_bound:
                raise SettlementInvariantError("non-turn envelope returned for bound ownership slot")
            await submit_via_notice(wire, handle=envelope.response_handle)

        async def read_lines() -> None:
            try:
                while True:
                    line = await reader.readline()
                    if line == b"":
                        await message_queue.put(None)
                        return
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        await message_queue.put(json.loads(stripped.decode("utf-8")))
                    except json.JSONDecodeError as exc:
                        print(f"optimus.acp: invalid ndjson line: {sanitize_protocol_error_message(str(exc))}", file=sys.stderr)
                        await message_queue.put(None)
                        return
            except Exception as exc:
                print(f"optimus.acp: ndjson reader failed: {sanitize_protocol_error_message(str(exc))}", file=sys.stderr)
                await message_queue.put(None)

        def approved_method_category(method: object) -> str:
            # Never copy arbitrary client content into a diagnostic: an unapproved method
            # collapses to "unknown" rather than being echoed.
            return method if method in ("initialize", "session/new", "session/load", "session/prompt") else "unknown"

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

        def report_mcp_cleanup_incomplete(outcome: object, status: str) -> None:
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
                if status == "incomplete":
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
                await deliver_envelope(envelope, ownership_slot)
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
                    data=lambda exc=exc: {
                        "request_id": request_id,
                        "method": method,
                        "pending_permission_id": pending_permission_id,
                        "exception_type": type(exc).__name__,
                        "exception_message": str(exc),
                    },
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

        reader_task = asyncio.create_task(read_lines())
        try:
            while True:
                message = await message_queue.get()
                if message is None:
                    break
                if "method" in message and "id" not in message:
                    await adapter.handle_client_notification(message)
                    continue
                if "id" in message and ("result" in message or "error" in message) and "method" not in message:
                    # region agent log
                    if debug_trace_enabled():
                        acp_debug_log(
                            location="server.py:serve_ndjson:inbound_client_response_raw",
                            message="raw inbound id-bearing client response before deliver_client_response",
                            data=lambda message=message: {
                                "id": message.get("id"),
                                "has_result": "result" in message,
                                "has_error": "error" in message,
                                "error": message.get("error") if "error" in message else None,
                                "result": message.get("result") if "result" in message else None,
                            },
                            hypothesis_id="H2-REPLY",
                        )
                    # endregion
                    outbound.deliver_client_response(message)
                    continue
                if "method" in message and "id" in message:
                    # Mint the operation id once here, before the task exists, so the same id
                    # can be bound into the completion observer without a late-bound loop
                    # variable, and threaded into process_request for its own diagnostics.
                    operation_id = uuid.uuid4().hex
                    request_method = approved_method_category(message.get("method"))
                    task = asyncio.create_task(process_request(message, operation_id))
                    request_tasks.add(task)
                    task.add_done_callback(
                        functools.partial(
                            on_request_task_done, operation_id=operation_id, request_method=request_method
                        )
                    )
        finally:
            # Transport-loss ordering: abandon notices before cancelling request tasks.
            notice.mark_transport_abandoned()
            for turn in list(adapter._active_turns.values()):  # noqa: SLF001
                turn.turn_control.request_transport_teardown()
            for task in list(request_tasks):
                task.cancel()
            if request_tasks:
                await asyncio.gather(*request_tasks, return_exceptions=True)
            adapter.close_all()
            # Client-MCP cleanup outcome. The runtime attempts every stage and returns an
            # aggregate result; consuming it here means an incomplete-but-non-raising cleanup
            # (a supervisor still draining, a contained stage failure) is reported instead of
            # passing silently. Only an absent runtime is an implicit clean/no-resource case.
            # The report is made right here, before the later stages, so it is attempted
            # whenever the runtime returned; later stages keep their existing order.
            if self._client_mcp_runtime is not None:
                mcp_outcome = self._client_mcp_runtime.close()
                mcp_status = classify_mcp_cleanup(mcp_outcome)
                if mcp_status != "clean":
                    report_mcp_cleanup_incomplete(mcp_outcome, mcp_status)
            if dedicated is not None and owned_dedicated and join_dedicated_writer:
                dedicated.close_and_join()
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
            if reader_task.done():
                await reader_task
            else:
                reader_task.cancel()
                report_reader_incomplete()
            # Seam 2, checkpoint B: the Redis runtime is closed LAST by the enclosing
            # `serve_ndjson` finally, after every stage above that may still submit work
            # to it -- and still closed when one of those stages raises.
