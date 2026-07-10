import asyncio

import pytest

from optimus.acp.errors import INVALID_PARAMS, AcpOutboundError
from optimus.acp.server import NdjsonOutboundChannel


class FakeWriter:
    def __init__(self) -> None:
        self.lines: list[dict] = []

    async def write_line(self, message):
        self.lines.append(message)


async def test_deliver_client_response_propagates_json_rpc_error():
    writer = FakeWriter()
    channel = NdjsonOutboundChannel(writer)
    request_task = asyncio.create_task(channel.request("session/request_permission", {"sessionId": "s1"}))
    await asyncio.sleep(0)
    request_id = writer.lines[0]["id"]
    channel.deliver_client_response(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": INVALID_PARAMS,
                "message": "Invalid params",
                "data": {"error": "missing field `toolCall`"},
            },
        }
    )
    with pytest.raises(AcpOutboundError) as exc_info:
        await request_task
    assert exc_info.value.code == INVALID_PARAMS
    assert "toolCall" in exc_info.value.message or exc_info.value.data is not None


async def test_deliver_client_response_user_cancel_still_returns_cancelled_outcome():
    writer = FakeWriter()
    channel = NdjsonOutboundChannel(writer)
    request_task = asyncio.create_task(channel.request("session/request_permission", {"sessionId": "s1"}))
    await asyncio.sleep(0)
    request_id = writer.lines[0]["id"]
    channel.cancel_request(request_id, {"outcome": {"outcome": "cancelled"}})
    result = await request_task
    assert result == {"outcome": {"outcome": "cancelled"}}
