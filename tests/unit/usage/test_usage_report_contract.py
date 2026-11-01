"""Plan 12.9 Task 1: the usage-report contract (requests, responses, cursors, B2/B3 never carrying an amount)."""

from __future__ import annotations

import copy
import json

import pytest

from optimus_security import usage_report_contract as ur

_KEY = b"k" * 32


def _report_request(**changes) -> dict:
    request = {"schema_version": 1, "operation": "report", "session_id": "s", "turn_id": None, "reference_ids": None,
               "page_size": 20, "cursor": None, "expected_turns": 3}
    request.update(changes)
    return request


def _column(ref_id="ref-a") -> dict:
    return {"reference_id": ref_id, "display": "Reference A", "snapshot_id": "hex:" + "0" * 64,
            "source": "https://example.test/p", "price_as_of": "2026-11-01", "baseline_known_usd": "0.00154",
            "priced_attempts": 2, "unpriced": [], "complete": True, "reasons": [], "savings_usd": "-0.00024",
            "savings_percent": "-15.6"}


def _totals() -> dict:
    return {"known_usd": "0.0013", "attempts": 2, "unknown_attempts": 0, "conflicts": 0, "late": 0, "turns": 1,
            "definitive": True, "reasons": []}


def _report() -> dict:
    return {
        "schema_version": 1, "status": "ok", "ledger_instance": "a" * 32, "as_of": "2026-11-01T00:00:00+00:00",
        "revision": "hex:" + "1" * 64, "scope": {"session_id": "s", "turn_id": None}, "session": _totals(),
        "auto": _totals(), "attribution": {"auto_turns": 1, "fixed_turns": 0, "unattributed_turns": 0},
        "comparisons": {"offset": 0, "total": 1, "columns": [_column()]}, "detail": [], "next_cursor": None,
        "b2": {"state": "unavailable"}, "b3": {"state": "unavailable"}, "benchmark": None,
    }


def test_a_report_request_round_trips():
    request = ur.ReportRequest("s", "t1", ("ref-a", "ref-b"), 50, None, 4)

    assert ur.parse_request(ur.build_request(request)) == request


def test_the_capabilities_request_round_trips_and_lists_the_report_context_feature():
    assert ur.parse_request(ur.build_request(None)) is None
    assert ur.FEATURE_REPORT_CONTEXT in ur.validate_capabilities(ur.capabilities_body())


@pytest.mark.parametrize(
    "request_",
    [
        _report_request(extra=1),
        _report_request(schema_version=2),
        _report_request(page_size=0),
        _report_request(page_size=101),
        _report_request(page_size=True),
        _report_request(session_id=""),
        _report_request(reference_ids=["ref-a", "ref-a"]),
        _report_request(reference_ids=["Ref A"]),
        _report_request(cursor="not-a-cursor"),
        _report_request(expected_turns=-1),
        # No caller-chosen user, path, database or credential can ride along.
        _report_request(database="other"),
        {"schema_version": 1, "operation": "capabilities", "dsn": "postgres://x"},
        {"schema_version": 1, "operation": "drop"},
    ],
)
def test_malformed_requests_are_refused(request_):
    with pytest.raises(ur.ContractError):
        ur.parse_request(json.dumps(request_).encode())


def test_an_oversized_request_is_refused_before_parsing():
    with pytest.raises(ur.ContractError) as raised:
        ur.parse_request(b" " * (ur.MAX_REQUEST_BYTES + 1))
    assert raised.value.code == "too_large"


def test_a_cursor_opens_only_under_its_key_and_unaltered():
    cursor = ur.seal_cursor(_KEY, {"session_id": "s", "revision": "hex:1", "reference_offset": 3, "after": None})

    assert ur.open_cursor(_KEY, cursor)["reference_offset"] == 3
    with pytest.raises(ur.ContractError):
        ur.open_cursor(b"x" * 32, cursor)
    body, mac = cursor.split(".")
    with pytest.raises(ur.ContractError):
        ur.open_cursor(_KEY, body[:-1] + ("A" if body[-1] != "A" else "B") + "." + mac)


def test_a_report_response_validates():
    assert ur.validate_report(_report())["comparisons"]["columns"][0]["savings_usd"] == "-0.00024"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r["b2"].update(savings_usd="1"),  # B2 never carries an amount
        lambda r: r["b3"].update(state="measured"),
        lambda r: r.update(b1_plus_b2="1"),  # nothing combines B1 and B2
        lambda r: r["comparisons"].update(columns=[_column(f"ref-{i}") for i in range(ur.REFERENCE_GROUP + 1)]),
        lambda r: r["session"].update(known_usd="-1"),  # a known total is non-negative; unknowns are counted
        lambda r: r["session"].update(reasons=["looks_fine"]),
        lambda r: r["comparisons"]["columns"][0].update(unpriced=[{"reason": "guessed", "attempts": 1, "tokens": 1}]),
        lambda r: r.update(raw_payload={}),
    ],
)
def test_report_responses_outside_the_contract_are_refused(mutate):
    report = copy.deepcopy(_report())
    mutate(report)
    with pytest.raises(ur.ContractError):
        ur.validate_report(report)


def test_zero_one_and_many_reference_groups_fit_the_page_bound():
    for count in (0, 1, ur.REFERENCE_GROUP):
        report = _report()
        report["comparisons"] = {"offset": 0, "total": 7, "columns": [_column(f"ref-{i}") for i in range(count)]}
        ur.validate_report(report)


def test_every_error_code_has_a_body_without_detail():
    for code, status in ur.ERROR_CODES.items():
        assert ur.error_body(code) == (status, {"schema_version": 1, "status": "error", "code": code})
