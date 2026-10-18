"""Closure plan v3: the ordinary composition compacts a real conversation end to end, offline.

The adapter runs with the shipped registry's ordinary attachment: the plain engine, the one shared numeric policy
and Haiku 5.5's summarizer route through the real ``GatewayClient`` on a fake transport (no Gateway, provider or
network). Answers come from a fake runner.

Compaction keeps the newest whole turns within its 32,768-token tail exact and summarizes every older turn. Two
notes turns of 24 KiB each each fit that tail alone, so the second turn needs no maintenance; the third turn's
history (both records) exceeds it, so that turn, and only that turn, summarizes the first notes turn, with between
1 and 18 calls, each bound to the shipped registry, and its answer is delivered. The question asks for a fact that
exists only in the summarized turn. This is the schedule the later ordinary-launch check uses; the live check, not
this test, proves the real host, Gateway, provider and the summary's content.
"""

from __future__ import annotations

from typing import Any

from context_engine.summary import WRAPPER_OPEN
from optimus.acp.context_attachment import ordinary_attachment
from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient, GatewayRequest
from optimus.runtime.modes import ExecutionMode
from optimus_model_policy.binding import trusted_snapshot
from optimus_model_policy.experimental import SHIPPED_DEFAULTS_HASH
from tests.unit.acp.test_context_engine_admission import SUMMARY, make_adapter, new_session, prompt, session_of, texts

HAIKU = "anthropic/claude-haiku-5.5"
NOTES_BYTES = 24 * 1024
SECRET = "synthetic-shared-secret"  # pragma: allowlist secret - synthetic test value
FACT = "The release code name chosen in the first planning notes is TANGERINE-47."


def synthetic_notes(n: int, size: int = NOTES_BYTES) -> str:
    """Deterministic plain-text planning notes of exactly ``size`` UTF-8 bytes; notes 1 carries one unique fact."""
    lines = [f"Planning notes, part {n}."] + ([FACT] if n == 1 else [])
    k = 0
    while sum(len(line) + 1 for line in lines) < size:
        lines.append(f"Note {n}.{k}: the calculator keeps amounts as decimals, rounds at the end of step {k % 97}, and logs the result.")
        k += 1
    text = "\n".join(lines)
    return text[:size]


class SummaryTransport:
    """A fake Gateway transport: every request is a summary request answered with a valid summary."""

    def __init__(self) -> None:
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict[str, Any]:
        self.requests.append(request)
        n = len(self.requests)
        return {
            "output_text": SUMMARY,
            "finish_reason": "stop",
            "gateway_usage": {"gateway_request_id": f"gw-s{n}", "provider": "openrouter", "billing_units": 1, "cost_usd": "0.0035"},
        }


def _client(transport: SummaryTransport) -> GatewayClient:
    settings = OptimusGatewaySettings.from_env(
        {"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765", "OPTIMUS_API_KEY": SECRET}  # pragma: allowlist secret - synthetic test fixture
    )
    return GatewayClient(settings=settings, transport=transport)


async def test_two_notes_turns_then_a_question_compact_on_the_ordinary_attachment(tmp_path) -> None:
    snapshot = trusted_snapshot()
    assert snapshot is not None
    transport = SummaryTransport()
    attachment = ordinary_attachment(snapshot=snapshot, model_id=HAIKU, gateway_client=_client(transport), shared_secret=SECRET)
    assert attachment is not None
    adapter, outbound, runner = make_adapter(tmp_path, attachment)
    session_id = await new_session(adapter, tmp_path, mode="chat")

    for n in (1, 2):
        response = await prompt(adapter, outbound, session_id, synthetic_notes(n) + "\n\nReply with OK only.", f"notes-{n}")
        assert response["result"]["stopReason"] == "end_turn"
        assert transport.requests == [], f"turn {n}: the prior history fits the compaction tail, so no maintenance"

    response = await prompt(adapter, outbound, session_id, "What release code name was chosen in the first planning notes?", "question")

    assert response["result"]["stopReason"] == "end_turn"
    assert 1 <= len(transport.requests) <= 18, "only this turn maintains, within the turn-wide allowance"
    summarized = "".join(request.payload["input"] for request in transport.requests)
    assert FACT in summarized and "Planning notes, part 1." in summarized, "notes 1 is what the summary covers"
    assert "Planning notes, part 2." not in summarized, "notes 2 is the exact tail, never summarized"
    for request in transport.requests:
        binding = request.payload["route_binding"]
        assert binding["registry_hash"] == SHIPPED_DEFAULTS_HASH and request.payload["model"] == HAIKU
    checkpoint = session_of(adapter, session_id).context_checkpoint
    assert checkpoint is not None and checkpoint.covered_turn_ids == (1,), "the view's summary of turn 1 is published"
    asked = runner.requests[-1]
    envelope = asked.conversation_envelope
    assert asked.execution_mode is ExecutionMode.CHAT and WRAPPER_OPEN in envelope, "the answer reads the compaction view"
    assert "Planning notes, part 2." in envelope, "notes 2 reaches the answer exactly"
    assert FACT not in envelope and "Planning notes, part 1." not in envelope, "raw notes 1 does not survive beside its summary"
    assert texts(outbound)[-1] == "Answer 3."
    # Limitation: the fake SUMMARY and fake "Answer 3." show the plumbing only. Whether a real summary keeps
    # TANGERINE-47 and the real answer names it is the later ordinary-launch check's acceptance criterion.
