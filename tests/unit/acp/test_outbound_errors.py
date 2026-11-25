import asyncio
import json

import pytest

from optimus.acp import errors
from optimus.acp.debug_trace import configure_debug_trace
from optimus.acp.errors import INTERNAL_ERROR, INVALID_PARAMS, REQUEST_CANCELLED, AcpOutboundError
from optimus.acp.server import NdjsonOutboundChannel


class FakeWriter:
    def __init__(self) -> None:
        self.lines: list[dict] = []

    async def write_line(self, message):
        self.lines.append(message)


@pytest.mark.parametrize(
    "reply",
    [
        {"error": {"code": INVALID_PARAMS, "message": "peer-detail-marker", "data": {"nested": "peer-payload-marker"}}},
        {"error": {"code": REQUEST_CANCELLED, "message": "peer cancellation"}},
        {"error": {"code": True}},
        {"error": {"code": "not a code"}},
        {"error": "not an error object"},
        {"result": ["not an object"]},
        {"result": {"present": True}, "error": {"code": INVALID_PARAMS}},
    ],
    ids=["known-code", "peer-cancel", "boolean-code", "string-code", "malformed-error", "malformed-result", "mixed"],
)
async def test_matching_peer_failure_settles_outbound_request_with_fixed_facts(reply, tmp_path):
    trace = tmp_path / "peer-reply.ndjson"
    configure_debug_trace(enabled=True, log_path=trace)
    channel = NdjsonOutboundChannel(FakeWriter())
    handle = channel.allocate_permission_request("session/request_permission", {"sessionId": "s1"})
    channel.deliver_client_response({"jsonrpc": "2.0", "id": handle.request_id, **reply})

    assert handle.response_future.done(), "the matching reply must settle its future"
    assert handle.request_id not in channel._futures
    with pytest.raises(AcpOutboundError) as raised:
        await handle.response_future
    assert raised.value.code == INTERNAL_ERROR
    assert raised.value.message == "client rejected outbound request"
    assert raised.value.data == {"reason": "CLIENT_REJECTED_OUTBOUND"}
    row = json.loads(trace.read_text(encoding="utf-8"))
    assert row["location"] == "server.py:NdjsonOutboundChannel.deliver_client_response"
    assert row["data"]["propagated_error"] is True


async def test_unmatched_and_boolean_peer_ids_leave_the_valid_reply_pending():
    channel = NdjsonOutboundChannel(FakeWriter())
    handle = channel.allocate_permission_request("session/request_permission", {"sessionId": "s1"})
    for request_id in (True, str(handle.request_id), handle.request_id + 1):
        channel.deliver_client_response({"id": request_id, "error": {"code": INVALID_PARAMS}})
    assert not handle.response_future.done()

    result = {"outcome": {"outcome": "cancelled"}}
    channel.deliver_client_response({"id": handle.request_id, "result": result})
    assert await handle.response_future == result
    assert handle.request_id not in channel._futures

async def test_deliver_client_response_user_cancel_still_returns_cancelled_outcome():
    writer = FakeWriter()
    channel = NdjsonOutboundChannel(writer)
    request_task = asyncio.create_task(channel.request("session/request_permission", {"sessionId": "s1"}))
    await asyncio.sleep(0)
    request_id = writer.lines[0]["id"]
    channel.cancel_request(request_id, {"outcome": {"outcome": "cancelled"}})
    result = await request_task
    assert result == {"outcome": {"outcome": "cancelled"}}


async def test_allocate_permission_request_is_synchronous_correlation():
    writer = FakeWriter()
    channel = NdjsonOutboundChannel(writer)
    handle = channel.allocate_permission_request(
        "session/request_permission", {"sessionId": "s1"}
    )
    assert handle.request_id in channel._futures
    assert not handle.response_future.done()
    handle.cancel()
    assert handle.request_id not in channel._futures
    assert handle.response_future.result() == {"outcome": {"outcome": "cancelled"}}


@pytest.mark.parametrize("message", ["outbound delivery failed", "outbound delivery unconfirmed"])
def test_host_delivery_error_retains_its_own_wire_reason(message):
    response = errors.outbound_error_response(7, AcpOutboundError(code=INTERNAL_ERROR, message=message))
    assert response == {"jsonrpc": "2.0", "id": 7, "error": {"code": INTERNAL_ERROR, "message": message}}


def test_peer_error_stays_named_and_drops_data_when_the_sanitizer_fails(monkeypatch):
    def unavailable(_value):
        raise RuntimeError("sanitizer unavailable")

    monkeypatch.setattr(errors, "sanitize_for_persistence", unavailable)
    response = errors.outbound_error_response(7, errors.AcpPeerResponseError())
    assert response == {"jsonrpc": "2.0", "id": 7, "error": {"code": INTERNAL_ERROR, "message": "internal error"}}
