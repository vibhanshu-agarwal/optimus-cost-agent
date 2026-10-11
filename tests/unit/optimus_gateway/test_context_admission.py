"""Plan 12.2 Task 5: the Gateway recomputes capacity on the final upstream request.

The host's own estimate is never trusted: the Gateway measures the text it will actually send (after
Chat Completions flattening), counts the bound output cap once against the smallest verified window
and refuses over-capacity requests before any upstream call. Equality is admitted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from optimus_gateway.chat_completions import handle_chat_completions_request
from optimus_gateway.responses import handle_responses_request
from tests.unit.optimus_gateway.model_policy_support import (
    AUTH,
    CAP,
    LIMIT_BYTES,
    RecordingUpstream,
    binding,
    gateway_config,
    model_policy,
    verified_snapshot,
)


@pytest.fixture
def snapshot(tmp_path: Path):
    return verified_snapshot(tmp_path)


def _responses(snapshot, text: str, *, output_cap: int = CAP) -> tuple[int, dict[str, Any], RecordingUpstream]:
    upstream = RecordingUpstream()
    status, body = handle_responses_request(
        authorization_header=AUTH,
        request_body={"model": "cn/alpha", "input": text, "route_binding": binding(snapshot, input_text=text, output_cap=output_cap)},
        config=gateway_config(model_policy(snapshot)),
        upstream_client=upstream,
    )
    return status, body, upstream


def test_input_at_exactly_usable_capacity_is_admitted(snapshot) -> None:
    status, _, upstream = _responses(snapshot, "x" * LIMIT_BYTES)
    assert status == 200
    assert len(upstream.calls) == 1


def test_one_byte_over_usable_capacity_is_refused(snapshot) -> None:
    status, body, upstream = _responses(snapshot, "x" * (LIMIT_BYTES + 2))  # +2 bytes = +1 token
    assert (status, body["code"]) == (400, "INPUT_EXCEEDS_CAPACITY")
    assert upstream.calls == []


def test_the_output_cap_is_counted_once_against_the_window(snapshot) -> None:
    """At the limit, reserving one more output token leaves one token less for input."""
    status, body, upstream = _responses(snapshot, "x" * LIMIT_BYTES, output_cap=CAP + 1)
    assert (status, body["code"]) == (400, "INPUT_EXCEEDS_CAPACITY")
    assert upstream.calls == []


@pytest.mark.parametrize(("cap", "code"), [(0, "OUTPUT_RESERVE_INVALID"), (-1, "OUTPUT_RESERVE_INVALID"), (20001, "OUTPUT_RESERVE_EXCEEDS_ROUTE")])
def test_output_cap_must_fit_every_endpoint_in_the_allow_set(snapshot, cap: int, code: str) -> None:
    """cn/alpha's allow-set has endpoints with max outputs 32768 and 20000: the smaller one governs."""
    status, body, upstream = _responses(snapshot, "hi", output_cap=cap)
    assert (status, body["code"]) == (400, code)
    assert upstream.calls == []


def test_capacity_counts_utf8_bytes_not_characters(snapshot) -> None:
    two_byte = "é"
    assert _responses(snapshot, two_byte * (LIMIT_BYTES // 2))[0] == 200
    status, body, upstream = _responses(snapshot, two_byte * (LIMIT_BYTES // 2 + 1))
    assert (status, body["code"]) == (400, "INPUT_EXCEEDS_CAPACITY")
    assert upstream.calls == []


def test_chat_flattening_growth_is_measured_on_the_final_text(snapshot) -> None:
    """Two messages whose contents total exactly the limit gain a joining newline when flattened, so
    the final upstream text is one byte over; the Gateway refuses it even though each part fits."""
    half = LIMIT_BYTES // 2
    first, second = "a" * half, "b" * (LIMIT_BYTES - half)
    flattened = f"{first}\n{second}"
    for messages, expected in (
        ([{"role": "user", "content": first + second}], 200),
        ([{"role": "system", "content": first}, {"role": "user", "content": second}], 400),
    ):
        upstream = RecordingUpstream()
        text = first + second if expected == 200 else flattened
        status, body = handle_chat_completions_request(
            authorization_header=AUTH,
            request_body={"model": "cn/alpha", "messages": messages, "route_binding": binding(snapshot, input_text=text)},
            config=gateway_config(model_policy(snapshot)),
            upstream_client=upstream,
        )
        assert status == expected, body
        if expected == 400:
            assert body["code"] == "INPUT_EXCEEDS_CAPACITY"
            assert upstream.calls == []
        else:
            assert len(upstream.calls) == 1


def test_escaped_json_material_is_measured_as_sent(snapshot) -> None:
    """Characters JSON escapes on the wire (quotes, backslashes, control characters) are measured
    as the UTF-8 text the provider receives, so escaping cannot shrink the estimate."""
    payload = '{"path": "C:\\\\work\\\\a.py", "note": "tab\\there"}\n'
    repeated = (payload * (LIMIT_BYTES // len(payload.encode()) + 1))[: LIMIT_BYTES + 2]
    status, body, upstream = _responses(snapshot, repeated)
    assert (status, body["code"]) == (400, "INPUT_EXCEEDS_CAPACITY")
    assert upstream.calls == []
