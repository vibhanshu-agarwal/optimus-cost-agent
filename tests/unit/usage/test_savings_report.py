"""Plan 12.9 Task 4: the host's `/savings` report — its command, its bounded Gateway read and its Markdown (ADR-034, D1-D3).

Responses come from the Gateway's own `report_body` over synthetic facts, so rendering is tested against what the Gateway
actually sends. Synthetic identities only; no model is named."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from optimus.config.gateway import OptimusGatewaySettings
from optimus.usage import savings_report as sr
from optimus_security import usage_report_contract as urc
from tests.unit.optimus_gateway.test_usage_report import _facts, _page, _payload, _references, _request


def _report(**facts):
    return _page(_facts(**facts), _request(), _references())


# --- The command -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "attachments", "parsed"), [
    ("/savings", False, sr.SavingsCommand()),
    ("  /savings  ", False, sr.SavingsCommand()),
    ("/savings turn s:3", False, sr.SavingsCommand(turn_id="s:3")),
    ("/savings next " + urc.seal_cursor(b"k" * 32, {"a": 1}), False, sr.SavingsCommand(cursor=urc.seal_cursor(b"k" * 32, {"a": 1}))),
    ("/savings", True, sr.USAGE),  # the command takes no attachments
    ("/savings please", False, sr.USAGE),
    ("/savings turn", False, sr.USAGE),
    ("/savings next not-a-cursor", False, sr.USAGE),
    ("/savings turn a b", False, sr.USAGE),
    ("/save", False, None),  # another word: an ordinary prompt
    ("what are /savings?", False, None),
    ("", False, None),
])
def test_only_the_savings_command_is_recognized_and_malformed_ones_answer_usage(text, attachments, parsed):
    assert sr.parse_command(text, attachments=attachments) == parsed


# --- Rendering -------------------------------------------------------------------------------------------------------


def test_a_definitive_report_shows_measured_cost_the_auto_columns_and_the_separate_b2_b3_b4_sections():
    markdown = sr.render_savings_report(_report())

    for label in ("measured", "coverage_complete", "history", "auto", "b1", "auto_question", "b2", "b2_unavailable", "b3",
                  "b3_unavailable", "cache_writes"):
        assert urc.LABELS[label] in markdown, label
    assert "USD 0.5021 across 3 requests in 2 turns" in markdown  # the Gateway's own decimal text, never recomputed
    assert markdown.count("| ref-") == 2 and "USD -0.0002" in markdown  # negative savings stay signed
    assert urc.LABELS["b4"] not in markdown  # no benchmark configured, no B4 section
    assert "/savings next" not in markdown


def test_an_incomplete_report_names_its_reasons_and_shows_no_savings():
    markdown = sr.render_savings_report(_page(_facts(uncommitted=1), _request(expected_turns=None), _references()))

    assert urc.LABELS["coverage_incomplete"].split("{")[0] in markdown
    assert "records are still being delivered" in markdown and "the host's turn count is unknown" in markdown
    assert urc.LABELS["not_definitive"] in markdown and "%" not in markdown.split(urc.LABELS["b2"])[0].split("Status |")[1]


def test_untrusted_identifiers_are_escaped_bounded_and_cannot_break_the_table():
    hostile = "t|1*_[x](http://evil)\n<script>`" + "x" * 200
    markdown = sr.render_savings_report(_page(_facts([(_payload("a1", hostile), False, False)], epochs={hostile: ("complete",)},
                                                     selections={hostile: ("auto",)}), _request(expected_turns=1), _references()))

    row = next(line for line in markdown.splitlines() if line.startswith("| t"))
    assert row.count(" | ") == 6, "the hostile identifier adds no table column"
    assert "\n<script>" not in markdown and "](http://evil)" not in markdown and "…" in row


def test_a_continuation_is_offered_and_unallocated_overhead_is_shown_apart():
    markdown = sr.render_savings_report(_page(_facts(unallocated=("0.01",)), _request(), _references(5)))

    assert "More of this report: `/savings next " in markdown and "References 1–3 of 5" in markdown
    assert "Not part of any session" in markdown and "USD 0.01 across 1 requests" in markdown


# --- The Gateway request ---------------------------------------------------------------------------------------------


class _Post:
    def __init__(self, status=200, body=None, error=None):
        self.status, self.body, self.error, self.sent = status, body, error, []

    def __call__(self, raw):
        self.sent.append(json.loads(raw))
        if self.error is not None:
            raise self.error
        return self.status, self.body


def test_the_request_carries_the_hosts_turn_count_and_frontier_and_a_turn_report_expects_one_turn():
    post = _Post(body=_report())
    reports = sr.SavingsReports(post, lambda session: (4, (("f" * 32, 9),)))

    reports.markdown("s", sr.SavingsCommand())
    reports.markdown("s", sr.SavingsCommand(turn_id="s:2"))

    assert post.sent[0]["expected_turns"] == 4 and post.sent[0]["frontier"] == [{"stream_id": "f" * 32, "sequence": 9}]
    assert (post.sent[1]["turn_id"], post.sent[1]["expected_turns"]) == ("s:2", 1)
    assert post.sent[0]["page_size"] == sr.PAGE_SIZE and post.sent[0]["reference_ids"] is None


@pytest.mark.parametrize(("post", "text"), [
    (_Post(503, urc.error_body("LEDGER_UNAVAILABLE")[1]), "The usage ledger is unavailable"),
    (_Post(503, urc.error_body("ACCOUNTING_NOT_CONFIGURED")[1]), "Usage accounting is not configured"),
    (_Post(409, urc.error_body("REPORT_CHANGED")[1]), "the continuation no longer applies"),
    (_Post(500, {"oops": True}), "could not prepare a usage report"),
    (_Post(200, {"schema_version": 1, "status": "ok"}), "not in the expected form"),
    (_Post(error=sr.ReportTransportError("unreachable")), "could not be reached"),
    (_Post(error=sr.ReportTransportError("too_large")), "too large"),
    (_Post(error=sr.ReportTransportError("timeout")), "took too long"),
])
def test_every_failure_is_stated_and_nothing_from_a_bad_reply_is_shown(post, text):
    assert text in sr.SavingsReports(post, lambda s: (0, ())).markdown("s", sr.SavingsCommand())


@pytest.fixture
def gateway():
    """A local HTTP server answering the report route as each case sets it."""
    behaviour: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            behaviour["auth"] = self.headers.get("Authorization")
            if behaviour.get("drip_headers"):  # a status line, then header lines each well inside the socket timeout
                self.wfile.write(b"HTTP/1.1 200 OK" + bytes([13, 10]))
                for n in range(20):
                    self.wfile.write(b"X-Drip-%d: 1" % n + bytes([13, 10]))
                    self.wfile.flush()
                    time.sleep(0.2)
                return
            status, chunks, pause = behaviour["reply"]
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(sum(len(c) for c in chunks)))
            self.end_headers()
            for chunk in chunks:
                self.wfile.write(chunk)
                self.wfile.flush()
                time.sleep(pause)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = OptimusGatewaySettings(gateway_url=f"http://127.0.0.1:{server.server_address[1]}", optimus_api_key="opt_live_k")  # pragma: allowlist secret
    yield settings, behaviour
    server.shutdown()
    server.server_close()


def test_the_bounded_read_returns_a_report_with_the_hosts_key(gateway):
    settings, behaviour = gateway
    behaviour["reply"] = (200, [json.dumps(_report()).encode()], 0)

    status, body = sr.gateway_post(settings)(urc.build_request(None))

    assert status == 200 and urc.validate_report(body) and behaviour["auth"] == "Bearer opt_live_k"


def test_a_reply_over_the_response_bound_is_refused(gateway):
    settings, behaviour = gateway
    behaviour["reply"] = (200, [b'"' + b"x" * (urc.MAX_RESPONSE_BYTES + 10) + b'"'], 0)

    with pytest.raises(sr.ReportTransportError, match="too_large"):
        sr.gateway_post(settings)(b"{}")


def test_a_reply_that_drips_in_stops_at_the_total_deadline(gateway):
    settings, behaviour = gateway
    behaviour["reply"] = (200, [b" "] * 50 + [b"{}"], 0.1)  # each byte well inside the socket timeout, five seconds in all

    started = time.monotonic()
    with pytest.raises(sr.ReportTransportError, match="timeout"):
        sr.gateway_post(settings, timeout=0.5)(b"{}")
    assert time.monotonic() - started < 2.0


def test_an_unreachable_gateway_is_a_transport_error():
    settings = OptimusGatewaySettings(gateway_url="http://127.0.0.1:9", optimus_api_key="opt_live_k")  # pragma: allowlist secret

    with pytest.raises(sr.ReportTransportError, match="unreachable"):
        sr.gateway_post(settings, timeout=10)(b"{}")  # a refused connection, well inside the deadline



# --- Checkpoint B round 94 ------------------------------------------------------------------------------------------


def test_headers_that_drip_in_stop_at_the_total_deadline(gateway):
    settings, behaviour = gateway
    behaviour["drip_headers"] = True

    started = time.monotonic()
    with pytest.raises(sr.ReportTransportError, match="timeout"):
        sr.gateway_post(settings, timeout=0.6)(b"{}")
    assert time.monotonic() - started < 1.5, "the watchdog ends the exchange at its deadline"


def test_a_read_stalled_near_the_deadline_stops_at_it(gateway):
    settings, behaviour = gateway
    behaviour["reply"] = (200, [b'{"a": ', b"1}"], 3)  # half the body, then a stall far past the deadline

    started = time.monotonic()
    with pytest.raises(sr.ReportTransportError, match="timeout"):
        sr.gateway_post(settings, timeout=0.5)(b"{}")
    assert time.monotonic() - started < 1.5


def test_the_transport_budget_is_the_plans_fifteen_seconds():
    assert sr.READ_SECONDS == 15.0 and sr.CAPABILITIES_SECONDS <= 5.0


def test_unknown_unallocated_charges_are_stated_not_hidden():
    markdown = sr.render_savings_report(_page(_facts(unallocated=(None,)), _request(), _references()))

    assert "known USD 0 across 1 requests, 1 of them with unknown cost." in markdown
