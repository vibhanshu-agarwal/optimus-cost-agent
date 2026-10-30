"""Finite admission and physical writer custody at saturation."""

import asyncio
import io
import threading
from dataclasses import replace

import pytest

from optimus.acp.outbound_writer import DedicatedOutboundWriter, EphemeralSendOwner
from optimus.acp.server import StdioNdjsonLineReader
from optimus.acp.settlement import SendOutcome
from tests.unit.acp.test_outbound_writer import ControllableTransport, _item


def test_count_and_bytes_reserve_control_and_release_once():
    from optimus.acp.admission import AdmissionAccount, AdmissionClass

    account = AdmissionAccount(count=2, bytes=128, reserved_count=1, reserved_bytes=32)
    ordinary = account.try_reserve(2, 96, AdmissionClass.ORDINARY)
    assert ordinary is not None
    assert account.try_reserve(1, 1, AdmissionClass.ORDINARY) is None
    required = account.try_reserve(1, 32, AdmissionClass.REQUIRED)
    assert required is not None
    assert account.try_reserve(1, 1, AdmissionClass.REQUIRED) is None
    ordinary.release()
    ordinary.release()
    assert (account.count, account.bytes) == (1, 32)
    required.release()
    assert (account.count, account.bytes) == (0, 0)
    borrowed = account.try_reserve(3, 128, AdmissionClass.REQUIRED)
    assert borrowed is not None
    borrowed.release()


def test_admission_diagnostics_are_bounded_transitions(caplog):
    from optimus.acp.admission import AdmissionAccount, AdmissionClass
    account = AdmissionAccount(count=1, bytes=8)
    with caplog.at_level("INFO", logger="optimus.acp.admission"):
        first = account.try_reserve(1, 8, AdmissionClass.ORDINARY)
        for _ in range(10):
            assert account.try_reserve(1, 1, AdmissionClass.ORDINARY) is None
        first.release()
        second = account.try_reserve(1, 1, AdmissionClass.ORDINARY)
        second.release()
        account.close()
        account.close()
    assert account.rejected == 10
    assert [record.args[1] for record in caplog.records] == ["full", "recovered", "closing"]


def test_cancelled_source_never_claims_a_physical_write_and_releases_once():
    from optimus.acp.lifecycle import WriterToken
    from optimus.acp.settlement import SendState
    transport = ControllableTransport()
    owner = EphemeralSendOwner()
    released = []
    item = _item(owner, payload={}, token=WriterToken(lambda: released.append(True)))
    assert item.source_future.cancel()
    writer = DedicatedOutboundWriter(transport)
    writer.start()
    try:
        writer.submit(item)
    finally:
        writer.close_and_join()
    assert transport.writes == []
    assert owner._slots[item.send_key].authoritative is SendState.SUPPRESSED
    assert released == [True]
    assert writer._admission.bytes == 0


def test_serialization_failure_releases_source_and_token_without_claiming_write():
    from optimus.acp.lifecycle import WriterToken
    transport = ControllableTransport()
    released = []
    owner = EphemeralSendOwner()
    item = _item(owner, payload={"bad": object()}, token=WriterToken(lambda: released.append(True)))
    writer = DedicatedOutboundWriter(transport)
    writer.start()
    try:
        assert writer.submit(item).result().outcome is SendOutcome.CONCLUSIVE_FAILURE
        assert writer._admission.bytes == 0
        assert released == [True]
        assert transport.writes == []
        assert not writer.admission_failure.done()
    finally:
        writer.close_and_join()


@pytest.mark.parametrize("extra", [0, 1])
async def test_real_stdio_default_frame_boundary(extra):
    from optimus.acp.admission import DEFAULT_LIMITS
    from optimus.acp.framing import FramingError
    size = DEFAULT_LIMITS.frame_bytes
    reader = StdioNdjsonLineReader(io.BytesIO(b"x" * (size + extra) + b"\n"))
    try:
        if extra:
            with pytest.raises(FramingError, match="body too large"):
                await reader.readline_limited(size)
        else:
            assert len(await reader.readline_limited(size)) == size + 1
    finally:
        reader.request_close()
        assert await asyncio.to_thread(reader.observe_closed, 2)


async def test_close_marker_is_admitted_with_full_payload_queue():
    from optimus.acp.admission import AdmissionClass, AdmissionLimits

    limits = replace(AdmissionLimits(), outbound_items=2, control_items=1, outbound_bytes=128, control_bytes=32)
    transport = ControllableTransport()
    transport.allow_write.clear()
    writer = DedicatedOutboundWriter(transport, limits=limits)
    writer.start()
    owner = EphemeralSendOwner()
    try:
        accepted = [_item(owner, payload={"id": n}) for n in range(3)]
        for item in accepted[:2]:
            item.admission_class = AdmissionClass.ORDINARY
            writer.submit(item)
        assert await asyncio.to_thread(transport.write_entered.wait, 2)
        rejected = _item(owner, payload={"id": 4})
        rejected.admission_class = AdmissionClass.ORDINARY
        assert writer.submit(rejected).result().outcome is SendOutcome.SUPPRESSED
        writer.submit(accepted[2])
        required = _item(owner, payload={"id": 5})
        assert writer.submit(required).result().outcome is SendOutcome.CONCLUSIVE_FAILURE
        writer.request_close()
        heartbeat = asyncio.create_task(asyncio.sleep(0, result=True))
        assert await asyncio.wait_for(heartbeat, 1)
        assert not writer.observe_closed(0)
        assert writer._queue.maxsize == 4
        transport.allow_write.set()
        assert await asyncio.to_thread(writer.observe_closed, 2)
        assert [item.source_future.result().outcome for item in accepted] == [SendOutcome.FLUSHED] * 3
        assert writer._admission.bytes == 0
    finally:
        transport.allow_write.set()
        writer.close_and_join()


def test_writer_serializes_once_before_admission(monkeypatch):
    import optimus.acp.outbound_writer as module

    transport = ControllableTransport()
    writer = DedicatedOutboundWriter(transport)
    writer.start()
    original = module.json.dumps
    calls = []

    def encode(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(module.json, "dumps", encode)
    try:
        item = _item(EphemeralSendOwner(), payload={"id": 1})
        writer.submit(item)
        assert item.encoded_payload == b'{"id":1}\n'
        assert item.source_future.result(2).outcome is SendOutcome.FLUSHED
        assert len(calls) == 1
    finally:
        writer.close_and_join()


async def test_real_stdio_bounded_read_discards_oversize_without_returning_fragments():
    from optimus.acp.framing import FramingError

    class LimitedStream(io.BytesIO):
        def readline(self, size=-1):
            assert 0 < size <= 34
            return super().readline(size)

    reader = StdioNdjsonLineReader(LimitedStream(b"x" * 80 + b"\n{}\n"))
    try:
        with pytest.raises(FramingError, match="body too large"):
            await reader.readline_limited(32)
        assert await reader.readline_limited(32) == b"{}\n"
    finally:
        reader.request_close()
        assert await asyncio.to_thread(reader.observe_closed, 2)


async def test_cancel_and_correlated_reply_bypass_full_application_queue(tmp_path, monkeypatch):
    from optimus.acp import server
    from optimus.acp.admission import AdmissionLimits
    from optimus.acp.lifecycle import NonTurnResponseEnvelope, NoticeControl, ResponseKind
    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter, configured_test_agent_server

    configured = configured_test_agent_server(tmp_path, output_text="READ example.py\n")
    configured.server._admission_limits = replace(AdmissionLimits(), pending_items=2, active_prompts=1, active_requests=1)
    class YieldingWriter(MemoryLineWriter):
        async def write_line(self, message):
            if message.get("result", {}).get("stopReason") == "cancelled":
                held.set()
                await active_finished.wait()
                for _ in range(3):
                    await asyncio.sleep(0)
            await super().write_line(message)
    reader, writer = InteractiveLineReader(), YieldingWriter()
    entered = []
    held = asyncio.Event()
    active_finished = asyncio.Event()
    cancelled = asyncio.Event()
    replied = asyncio.Event()
    async def handle(self, message, ownership_slot=None):
        entered.append(message["id"])
        if message["method"] == "session/prompt":
            await held.wait()
            active_finished.set()
        return NonTurnResponseEnvelope(response={"jsonrpc": "2.0", "id": message["id"], "result": {}},
                                       response_handle=NoticeControl().allocate_response_handle(ResponseKind.ORDINARY))
    async def cancel(self, message):
        cancelled.set()
    def reply(self, message):
        replied.set()
    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_request", handle)
    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_notification", cancel)
    monkeypatch.setattr(server.NdjsonOutboundChannel, "deliver_client_response", reply)
    serving = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    async def feed(message):
        await reader.send(message)
        await asyncio.sleep(0.01)
    try:
        for n in range(3):
            await feed({"id": n, "method": "session/prompt", "params": {"sessionId": "s"}})
        assert entered == [0]
        created = []
        create_task = asyncio.create_task
        def tracked_create_task(coro, **kwargs):
            created.append(coro)
            return create_task(coro, **kwargs)
        monkeypatch.setattr(asyncio, "create_task", tracked_create_task)
        for n in range(10):
            await feed({"id": 20 + n, "method": "session/prompt", "params": {"sessionId": "s"}})
        assert created == []
        monkeypatch.setattr(asyncio, "create_task", create_task)
        await feed({"id": 3, "method": "session/prompt", "params": {"sessionId": "s"}})
        assert any(m.get("error", {}).get("data") == {"reason": "QUEUE_FULL"} for m in writer.messages)
        await feed({"method": "session/cancel", "params": {"sessionId": "s"}})
        await feed({"id": 10000, "result": {}})
        await asyncio.wait_for(cancelled.wait(), 1)
        await asyncio.wait_for(replied.wait(), 1)
        await feed({"id": 4, "method": "session/set_mode", "params": {}})
        assert 4 in entered
        assert 1 not in entered and 2 not in entered
        assert sum(m.get("result", {}).get("stopReason") == "cancelled" for m in writer.messages) == 2
    finally:
        held.set()
        reader.close()
        await asyncio.wait_for(serving, 2)


async def test_queued_and_active_payload_share_one_byte_reservation(tmp_path, monkeypatch):
    from optimus.acp import server
    from optimus.acp.admission import AdmissionLimits
    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter, configured_test_agent_server
    configured = configured_test_agent_server(tmp_path, output_text="done")
    configured.server._admission_limits = replace(AdmissionLimits(), active_prompts=1)
    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    entered = asyncio.Event()
    hold = asyncio.Event()
    async def handle(self, message, ownership_slot=None):
        entered.set()
        await hold.wait()
    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_request", handle)
    serving = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    try:
        await reader.send({"id": 1, "method": "session/prompt"})
        await asyncio.wait_for(entered.wait(), 1)
        account = configured.server._inbound_admission
        assert account.count == 1 and account.bytes > 0
        first_bytes = account.bytes
        await reader.send({"id": 2, "method": "session/prompt"})
        for _ in range(100):
            if account.count == 2:
                break
            await asyncio.sleep(0)
        assert account.count == 2 and account.bytes == 2 * first_bytes
    finally:
        reader.close()
        await asyncio.wait_for(serving, 2)
    assert account.count == account.bytes == 0


async def test_full_required_capacity_abandons_without_error_response_growth(tmp_path):
    from optimus.acp.admission import AdmissionLimits
    from optimus.acp.process_lifecycle import ProcessLifecycle, StopReason
    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter, configured_test_agent_server
    configured = configured_test_agent_server(tmp_path, output_text="done")
    reader = InteractiveLineReader()
    transport = ControllableTransport()
    transport.allow_write.clear()
    writer = DedicatedOutboundWriter(transport, limits=replace(AdmissionLimits(), outbound_items=1, control_items=1))
    writer.start()
    owner = EphemeralSendOwner()
    writer.submit(_item(owner, payload={"id": 10}))
    writer.submit(_item(owner, payload={"id": 11}))
    lifecycle = ProcessLifecycle()
    serving = asyncio.create_task(configured.server.serve_ndjson(reader, MemoryLineWriter(), dedicated_writer=writer, join_dedicated_writer=False, lifecycle=lifecycle))
    lifecycle.bind(asyncio.get_running_loop(), serving)
    try:
        await reader.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": 1}})
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(serving, 2)
        assert writer._admission.count == 2
        assert writer.admission_failure.done()
        assert lifecycle.reason is StopReason.ERROR
        assert writer._admission_failure_callback is None
    finally:
        reader.close()
        transport.allow_write.set()
        writer.close_and_join()


async def test_active_prompt_reservation_survives_cancelled_worker_observation(tmp_path, monkeypatch):
    from optimus.acp import server
    from optimus.acp.admission import AdmissionLimits
    from optimus.acp.lifecycle import NonTurnResponseEnvelope, TurnControl
    from optimus.acp.spec import AcpPromptTurn, AcpSpecSession
    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter, configured_test_agent_server
    configured = configured_test_agent_server(tmp_path, output_text="done")
    configured.server._admission_limits = replace(AdmissionLimits(), active_prompts=1)
    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    physical_entered, release = threading.Event(), threading.Event()
    entries = []
    def worker():
        physical_entered.set()
        assert release.wait(5)
    async def handle(self, message, ownership_slot=None):
        entries.append(message["id"])
        if message["id"] == 1:
            session = AcpSpecSession(session_id="s", cwd=tmp_path)
            turn = AcpPromptTurn(session_id="s", turn_seq=1, turn_control=TurnControl(session_id="s", turn_seq=1))
            call = asyncio.create_task(self._in_worker(session, turn, worker))
            assert await asyncio.to_thread(physical_entered.wait, 2)
            call.cancel()
            with pytest.raises(asyncio.CancelledError):
                await call
        return NonTurnResponseEnvelope(response={"id": message["id"], "result": {}})
    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_request", handle)
    serving = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    try:
        await reader.send({"id": 1, "method": "session/prompt"})
        await asyncio.wait_for(writer.wait_for_response(1), 2)
        await reader.send({"id": 2, "method": "session/prompt"})
        await reader.send({"id": 3, "method": "session/set_mode"})
        await asyncio.wait_for(writer.wait_for_response(3), 2)
        assert entries == [1, 3]
        async def setter_retired():
            while configured.server._inbound_admission.count > 2:
                await asyncio.sleep(0)
        await asyncio.wait_for(setter_retired(), 2)
        assert configured.server._inbound_admission.count == 2
        release.set()
        await asyncio.wait_for(writer.wait_for_response(2), 2)
    finally:
        release.set()
        reader.close()
        await asyncio.wait_for(serving, 3)


@pytest.mark.parametrize("permission_capture_order", ["request", "reverse"])
async def test_eight_permission_held_prompts_leave_setter_pool_usable(tmp_path, monkeypatch, permission_capture_order):
    from optimus.acp.lifecycle import TurnControl
    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter, configured_test_agent_server
    allocated = []
    initialize = TurnControl.__init__
    def track_turn(self, *args, **kwargs):
        initialize(self, *args, **kwargs)
        allocated.append(self)
    monkeypatch.setattr(TurnControl, "__init__", track_turn)
    configured = configured_test_agent_server(tmp_path, output_text="WRITE example.py\ncontent")
    reader = InteractiveLineReader()
    class Writer(MemoryLineWriter):
        def __init__(self):
            super().__init__()
            self.permissions = []
            self.changed = asyncio.Event()
        async def write_line(self, message):
            await super().write_line(message)
            if message.get("method") == "session/request_permission":
                self.permissions.append(dict(message))
                self.changed.set()
    writer = Writer()
    serving = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    sessions = []
    async def request(request_id, method, params):
        await reader.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return await asyncio.wait_for(writer.wait_for_response(request_id), 3)
    try:
        await request(1, "initialize", {"protocolVersion": 1})
        for n in range(9):
            response = await request(10 + n, "session/new", {"cwd": str(tmp_path), "mcpServers": []})
            sessions.append(response["result"]["sessionId"])
        for n, session_id in enumerate(sessions[:8]):
            await reader.send({"jsonrpc": "2.0", "id": 100 + n, "method": "session/prompt", "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Write example.py"}]}})
        async def permissions_ready():
            while len(writer.permissions) < 8:
                writer.changed.clear()
                if len(writer.permissions) < 8:
                    await writer.changed.wait()
        await asyncio.wait_for(permissions_ready(), 5)
        # Concurrent planning can present permission requests in either order.
        writer.permissions.sort(key=lambda message: sessions.index(message["params"]["sessionId"]),
                                reverse=permission_capture_order == "reverse")
        assert {message["params"]["sessionId"] for message in writer.permissions} == set(sessions[:8])
        assert configured.fake_gateway_call_count == 8
        assert len(allocated) == 8
        busy = await request(199, "session/prompt", {"sessionId": sessions[0], "prompt": [{"type": "text", "text": "Must remain busy"}]})
        assert busy["error"]["message"] == "a turn is already in progress"
        await reader.send({"jsonrpc": "2.0", "id": 200, "method": "session/prompt", "params": {"sessionId": sessions[8], "prompt": [{"type": "text", "text": "Must not run"}]}})
        setter = await request(201, "session/set_mode", {"sessionId": sessions[8], "modeId": "chat"})
        assert "result" in setter
        await reader.send({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": sessions[8]}})
        cancelled = await asyncio.wait_for(writer.wait_for_response(200), 2)
        assert cancelled["result"]["stopReason"] == "cancelled"
        assert configured.fake_gateway_call_count == 8
        assert len(allocated) == 8
        assert not (tmp_path / "example.py").exists()
        permission, = (message for message in writer.permissions if message["params"]["sessionId"] == sessions[0])
        await reader.send({"jsonrpc": "2.0", "id": permission["id"], "result": {"outcome": {"outcome": "cancelled"}}})
        assert (await asyncio.wait_for(writer.wait_for_response(100), 2))["result"]["stopReason"] == "cancelled"
    finally:
        reader.close()
        await asyncio.wait_for(serving, 5)


async def test_explicit_limited_seam_preserves_legacy_readline():
    class Legacy:
        def readline(self):
            return b"legacy\n"
    stream = io.BytesIO(b"limited\n")
    def limited(size):
        return stream.readline(size)
    reader = StdioNdjsonLineReader(Legacy(), limited_readline=limited)
    try:
        assert await reader.readline_limited(32) == b"limited\n"
        assert await reader.readline() == b"legacy\n"
    finally:
        reader.request_close()
        assert await asyncio.to_thread(reader.observe_closed, 2)


async def test_ignored_notification_flood_is_counted_without_admission(tmp_path):
    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter, configured_test_agent_server
    configured = configured_test_agent_server(tmp_path, output_text="done")
    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    serving = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    try:
        for _ in range(100):
            await reader.send({"jsonrpc": "2.0", "method": "unknown/notification"})
        await reader.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": 1}})
        assert "result" in await asyncio.wait_for(writer.wait_for_response(1), 2)
        assert configured.server._ignored_notifications == 100
        configured.server._ignored_notifications = 2**63 - 1
        await reader.send({"jsonrpc": "2.0", "method": "unknown/notification"})
        await reader.send({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": 1}})
        await asyncio.wait_for(writer.wait_for_response(2), 2)
        assert configured.server._ignored_notifications == 2**63 - 1
        assert configured.server._inbound_admission.rejected == 0
    finally:
        reader.close()
        await asyncio.wait_for(serving, 3)


@pytest.mark.parametrize("count,size", [(2, 1), (1, 96)])
def test_required_first_cannot_let_ordinary_consume_remaining_reserve(count, size):
    from optimus.acp.admission import AdmissionAccount, AdmissionClass
    account = AdmissionAccount(count=2, bytes=128, reserved_count=1, reserved_bytes=32)
    first = account.try_reserve(count, size, AdmissionClass.REQUIRED)
    assert first is not None
    assert account.try_reserve(1, 1, AdmissionClass.ORDINARY) is None
    last = account.try_reserve(1, 1, AdmissionClass.REQUIRED)
    assert last is not None
    first.release()
    last.release()


def test_cancelled_required_at_capacity_does_not_signal_transport_failure():
    from optimus.acp.admission import AdmissionLimits
    transport = ControllableTransport()
    transport.allow_write.clear()
    writer = DedicatedOutboundWriter(transport, limits=replace(AdmissionLimits(), outbound_items=1, control_items=1))
    writer.start()
    owner = EphemeralSendOwner()
    try:
        for n in range(2):
            writer.submit(_item(owner, payload={"id": n}))
        item = _item(owner, payload={"id": 3})
        assert item.source_future.cancel()
        writer.submit(item)
        assert not writer.admission_failure.done()
    finally:
        transport.allow_write.set()
        writer.close_and_join()


async def test_optional_notification_uses_ordinary_capacity():
    from optimus.acp.admission import AdmissionClass
    from optimus.acp.lifecycle import SendCompletion
    from optimus.acp.server import NdjsonOutboundChannel
    from tests.integration.acp.test_server_stream import MemoryLineWriter
    items = []
    class Capture:
        def submit(self, item):
            items.append(item)
            item.source_future.set_result(SendCompletion(send_key=item.send_key, outcome=SendOutcome.FLUSHED))
    channel = NdjsonOutboundChannel(MemoryLineWriter(), dedicated_writer=Capture())
    await channel.notify("session/update", {"update": {"sessionUpdate": "usage_update"}})
    await channel.notify("session/update", {"update": {"sessionUpdate": "current_mode_update"}}, require_flushed=True)
    assert [item.admission_class for item in items] == [AdmissionClass.ORDINARY, AdmissionClass.REQUIRED]


async def test_ndjson_crlf_exact_limit_and_oversize_truthful_failure(tmp_path):
    from optimus.acp.admission import AdmissionLimits
    from optimus.acp.framing import FramingError
    from tests.integration.acp.test_server_stream import MemoryLineWriter, configured_test_agent_server
    reader = StdioNdjsonLineReader(io.BytesIO(b"x" * 32 + b"\r\n"))
    try:
        assert len(await reader.readline_limited(32)) == 34
    finally:
        reader.request_close()
        assert await asyncio.to_thread(reader.observe_closed, 2)
    configured = configured_test_agent_server(tmp_path, output_text="done")
    configured.server._admission_limits = replace(AdmissionLimits(), frame_bytes=32)
    reader = StdioNdjsonLineReader(io.BytesIO(b"x" * 33 + b"\n"))
    try:
        with pytest.raises(FramingError, match="body too large"):
            await configured.server.serve_ndjson(reader, MemoryLineWriter())
    finally:
        reader.request_close()
        assert await asyncio.to_thread(reader.observe_closed, 2)
