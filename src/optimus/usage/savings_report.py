"""The `/savings` report on the ACP host (Plan 12.9; ADR-034, D1-D3): its Gateway request and its Markdown.

The host never reads Postgres. It asks the Gateway's `POST /v1/observability/usage-report` with its existing URL and key,
sending what only it knows: how many turns it ran in the session and its capture stream's frontier
(`DurableCapture.report_scope`), so the Gateway can say whether the session's totals are complete. The reply is read
with a deadline and a byte cap of its own (never the model transport's unbounded read) and validated against
`usage_report_contract` before anything is shown.

Rendering only lays out what the Gateway computed: amounts are the reply's decimal text, never recomputed here.
Untrusted identifiers are escaped and shortened. The exact labels are the contract's.
"""

from __future__ import annotations

import json
import re
import socket
import ssl
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from optimus.config.gateway import OptimusGatewaySettings
from optimus_security import usage_report_contract as urc

PAGE_SIZE = 25  # detail rows per rendered page (agent-selected); the Gateway bounds it again
READ_SECONDS = 15.0  # the host transport's whole budget (plan v2 design 2), connection to last body byte
CAPABILITIES_SECONDS = 5.0  # capture delivery's negotiation (agent-selected): it must never hold a delivery pass long
_IDENTIFIER_CHARS = 64

COMMAND = "savings"
COMMAND_DESCRIPTION = "Show this session's measured cost and the Auto comparison with configured reference models"
COMMAND_HINT = "[turn <run-id> | next <continuation>]"
USAGE = ("Usage: `/savings` for this session, `/savings turn <run-id>` for one turn, or `/savings next <continuation>` "
         "to continue a report. The command takes no attachments.")

_REASONS = {
    "epoch_missing": "a turn's coverage record is missing", "epoch_open": "a turn is still open",
    "epoch_incomplete": "a turn's coverage is incomplete", "turn_not_captured": "a turn has not reached the ledger",
    "unknown_cost": "a request's cost is unknown", "receipt_conflict": "contradictory receipts",
    "late_receipt": "a receipt arrived after its turn closed", "delivery_pending": "records are still being delivered",
    "scope_too_large": "the scope is larger than one report can total", "attribution_unavailable":
        "some turns are not recorded as Auto or fixed", "expected_turns_unknown": "the host's turn count is unknown",
    "frontier_unknown": "the host's delivery position is unknown", "stream_gap": "a capture stream has a gap",
}
_COLUMN_REASONS = {
    "source_missing": "no price source", "source_date_missing": "no price date", "unpriced_attempts": "some requests cannot be priced",
    "actual_incomplete": "the measured total is not complete", "no_attempts": "no Auto requests",
}
_UNPRICED = {
    "tokens_unreported": "tokens not reported", "cached_split_unreported": "cached split not reported",
    "reasoning_split_unreported": "reasoning split not reported", "categories_inconsistent": "inconsistent token counts",
    "price_missing_input": "no input price", "price_missing_cached_input": "no cached-input price",
    "price_missing_output": "no output price",
}
_FAILURES = {
    "ACCOUNTING_NOT_CONFIGURED": "Usage accounting is not configured for this Gateway, so there is no ledger to report from.",
    "LEDGER_UNAVAILABLE": "The usage ledger is unavailable right now. Model work is unaffected; try again later.",
    "REPORT_BUSY": "The Gateway is already preparing other reports. Try again in a moment.",
    "REPORT_TIMEOUT": "The usage report took too long and was stopped. Try again, or ask for one turn with `/savings turn <run-id>`.",
    "REPORT_CHANGED": "The ledger changed since this report began, so the continuation no longer applies. Run `/savings` again.",
    "REQUEST_INVALID": "The Gateway did not accept this report request.",
    "REQUEST_TOO_LARGE": "The report request was too large.",
    "UNAUTHORIZED": "The Gateway refused this host's key.",
}


_NOT_PREPARED = "The Gateway could not prepare a usage report."
_MALFORMED = "The Gateway's usage report was too large or not in the expected form, so nothing from it is shown."


@dataclass(frozen=True)
class SavingsCommand:
    turn_id: str | None = None
    cursor: str | None = None


def parse_command(text: str, *, attachments: bool) -> SavingsCommand | str | None:
    """None: not this command (ordinary prompt). A `SavingsCommand`, or the usage text for a malformed one."""
    words = text.split()
    if not words or words[0] != f"/{COMMAND}":
        return None
    if attachments:
        return USAGE
    if len(words) == 1:
        return SavingsCommand()
    if len(words) == 3 and words[1] == "turn" and 0 < len(words[2]) <= urc.MAX_STRING:
        return SavingsCommand(turn_id=words[2])
    if len(words) == 3 and words[1] == "next" and urc.is_cursor(words[2]):
        return SavingsCommand(cursor=words[2])
    return USAGE


class ReportTransportError(Exception):
    """The Gateway could not be reached, or its reply was not a report this contract knows."""


Post = Callable[[bytes], tuple[int, Any]]


def gateway_post(settings: OptimusGatewaySettings, *, timeout: float = READ_SECONDS) -> Post:
    """POST to the report route with the host's Gateway URL and key, reading at most the contract's response bound.

    One deadline covers the whole exchange, enforced on the socket this function owns: the connection, the send and
    every receive each get exactly the time left, so slow headers, late headers then a stalled body, or a body that
    drips in all end at the deadline and the calling thread returns (`ReportTransportError`). A watchdog cannot give
    that bound: shutting a socket down from another thread does not wake a receive already blocked on it everywhere.
    The request asks the Gateway to close the connection, and its reply carries a Content-Length."""
    settings.validate_trusted_gateway()
    parts = urlsplit(settings.gateway_url.rstrip("/") + urc.PATH)
    host, port = parts.hostname or "", parts.port or (443 if parts.scheme == "https" else 80)

    def post(body: bytes) -> tuple[int, Any]:
        deadline = time.monotonic() + timeout

        def left() -> float:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ReportTransportError("timeout")
            return remaining

        headers = {**settings.auth_headers(), "Host": f"{host}:{port}", "Content-Type": "application/json",
                   "Accept": "application/json", "Content-Length": str(len(body)), "Connection": "close"}
        head = f"POST {parts.path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in headers.items()) + "\r\n"
        sock = _connect(host, port, left)
        try:
            if parts.scheme == "https":
                sock.settimeout(left())
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            sock.settimeout(left())
            sock.sendall(head.encode("latin-1") + body)
            return _bounded_reply(sock, left)
        except TimeoutError:
            raise ReportTransportError("timeout") from None
        except OSError:
            raise ReportTransportError("unreachable") from None
        finally:
            sock.close()

    return post


# The only hosts a trusted Gateway URL may name (`config.gateway._validate_loopback_gateway_url`), as numeric
# addresses: nothing is resolved, so no resolver can spend the deadline.
_LOOPBACK_ADDRESSES: Mapping[str, tuple[tuple[socket.AddressFamily, str], ...]] = {
    "127.0.0.1": ((socket.AF_INET, "127.0.0.1"),),
    "::1": ((socket.AF_INET6, "::1"),),
    "localhost": ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")),
}
_new_socket = socket.socket  # a seam for the connection-budget test


def _connect(host: str, port: int, left: Callable[[], float]) -> socket.socket:
    """A connection to the first loopback address that accepts, every attempt sharing the one remaining budget."""
    addresses = _LOOPBACK_ADDRESSES.get(host.lower())
    if addresses is None:
        raise ReportTransportError("unreachable")
    failure = "unreachable"
    for family, address in addresses:
        try:
            sock = _new_socket(family, socket.SOCK_STREAM)
        except OSError:
            continue  # this family is unavailable, or no socket could be allocated: try the next address
        try:
            sock.settimeout(left())
            sock.connect((address, port))
            return sock
        except TimeoutError:
            sock.close()
            failure = "timeout"
        except OSError:
            sock.close()
        except BaseException:
            sock.close()
            raise
    raise ReportTransportError(failure)


_HEAD_BYTES = 64 * 1024  # status line and headers


def _bounded_reply(sock: socket.socket, left: Callable[[], float]) -> tuple[int, Any]:
    """The reply's status and JSON body, read within the deadline and the contract's response bound."""
    raw = bytearray()
    length: int | None = None
    body_start = -1
    while True:
        sock.settimeout(left())
        chunk = sock.recv(64 * 1024)
        if not chunk:
            break
        raw += chunk
        if body_start < 0:
            body_start = raw.find(b"\r\n\r\n")
            if body_start < 0:
                if len(raw) > _HEAD_BYTES:
                    raise ReportTransportError("malformed")
                continue
            body_start += 4
            if body_start > _HEAD_BYTES:
                raise ReportTransportError("malformed")  # the cap holds however the head was split across receives
            status, length = _head(bytes(raw[:body_start]))
        if len(raw) - body_start > urc.MAX_RESPONSE_BYTES:
            raise ReportTransportError("too_large")
        if length is not None and len(raw) - body_start >= length:
            break
    if body_start < 0:
        raise ReportTransportError("malformed")
    payload = bytes(raw[body_start:]) if length is None else bytes(raw[body_start:body_start + length])
    if length is not None and len(payload) < length:
        raise ReportTransportError("malformed")  # the connection closed before the declared body arrived
    try:
        return status, json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        raise ReportTransportError("malformed") from None


_STATUS = re.compile(r"HTTP/1\.[01] ([0-9]{3})(?: .*)?")
_LENGTH = re.compile(r"[0-9]{1,10}")


def _head(head: bytes) -> tuple[int, int | None]:
    """The status and declared length, from ASCII digits only (`str.isdigit` also admits digits `int` refuses)."""
    lines = head.decode("latin-1").split("\r\n")
    status = _STATUS.fullmatch(lines[0])
    if status is None:
        raise ReportTransportError("malformed")
    fields = {name.strip().lower(): value.strip() for name, _, value in (line.partition(":") for line in lines[1:] if line)}
    if "chunked" in fields.get("transfer-encoding", "").lower():
        raise ReportTransportError("malformed")  # the Gateway always sends a Content-Length
    declared = fields.get("content-length")
    if declared is not None and _LENGTH.fullmatch(declared) is None:
        raise ReportTransportError("malformed")
    if declared is not None and int(declared) > urc.MAX_RESPONSE_BYTES:
        raise ReportTransportError("too_large")
    return int(status.group(1)), None if declared is None else int(declared)


Scope = Callable[[str], tuple[int, tuple[tuple[str, int], ...]]]


class SavingsReports:
    """One host's `/savings` source: the Gateway route and this host's own capture scope."""

    _CONTINUATIONS = 256  # remembered continuations (agent-selected); a forgotten one continues as a session report

    def __init__(self, post: Post, scope: Scope) -> None:
        self._post, self._scope = post, scope
        self._lock = threading.Lock()
        self._continued: OrderedDict[tuple[str, str], str | None] = OrderedDict()  # (session, cursor) -> its turn scope

    def markdown(self, session_id: str, command: SavingsCommand) -> str:
        """The rendered report or its stated failure; never raises for a Gateway or ledger state. A continuation repeats
        the scope of the report that offered it (the cursor binds it, so a different scope answers REPORT_CHANGED)."""
        turn_id = command.turn_id
        if command.cursor is not None:
            with self._lock:
                turn_id = self._continued.get((session_id, command.cursor))
        expected_turns, frontier = self._scope(session_id)
        request = urc.ReportRequest(session_id, turn_id, None, PAGE_SIZE, command.cursor,
                                    1 if turn_id is not None else expected_turns, frontier or None)
        try:
            status, body = self._post(urc.build_request(request))
        except ReportTransportError as exc:
            if str(exc) == "unreachable":
                return "The Gateway could not be reached for a usage report. Model work is unaffected; try again later."
            return _FAILURES["REPORT_TIMEOUT"] if str(exc) == "timeout" else _MALFORMED
        if status != 200:
            code = body.get("code") if isinstance(body, Mapping) else None
            return _FAILURES.get(code, _NOT_PREPARED) if isinstance(code, str) else _NOT_PREPARED
        try:
            report = urc.validate_report(body)
        except urc.ContractError:
            return _MALFORMED
        if report["next_cursor"] is not None:
            with self._lock:
                self._continued[(session_id, report["next_cursor"])] = turn_id
                while len(self._continued) > self._CONTINUATIONS:
                    self._continued.popitem(last=False)
        return render_savings_report(report)


def _text(value: object, limit: int = _IDENTIFIER_CHARS) -> str:
    """Untrusted text for a Markdown table cell: control characters dropped, Markdown escaped, length bounded."""
    text = re.sub(r"[\x00-\x1f\x7f]", "", str(value))
    text = text if len(text) <= limit else text[: limit - 1] + "…"
    return re.sub(r"([\\`*_{}\[\]<>()#+!|~])", r"\\\1", text)


def _usd(value: str | None) -> str:
    return "unknown" if value is None else f"USD {value}"


def _reasons(codes: Sequence[str], names: Mapping[str, str]) -> str:
    return "; ".join(names.get(code, code) for code in codes)


def _coverage(totals: Mapping[str, Any]) -> str:
    if totals["definitive"]:
        return urc.LABELS["coverage_complete"]
    return urc.LABELS["coverage_incomplete"].format(reasons=_reasons(totals["reasons"], _REASONS))


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _totals_line(name: str, totals: Mapping[str, Any]) -> str:
    unknown = f", {totals['unknown_attempts']} with unknown cost" if totals["unknown_attempts"] else ""
    return (f"- **{name}:** {_usd(totals['known_usd'])} across {_count(totals['attempts'], 'request')} in {_count(totals['turns'], 'turn')}"
            f"{unknown}. {_coverage(totals)}.")


def render_savings_report(report: Mapping[str, Any]) -> str:
    """Markdown for one validated report page."""
    scope = report["scope"]
    title = "this session" if scope["turn_id"] is None else f"turn {_text(scope['turn_id'])}"
    lines = [f"## Usage and savings for {title}", "", f"### {urc.LABELS['measured']}",
             _totals_line("Session", report["session"]), _totals_line("Auto turns", report["auto"])]
    attribution = report["attribution"]
    lines.append(f"- **Turns:** {attribution['auto_turns']} Auto, {attribution['fixed_turns']} fixed, "
                 f"{attribution['unattributed_turns']} not recorded either way.")
    unallocated = report["unallocated"]
    if unallocated["attempts"]:
        unknown = unallocated["unknown_attempts"]
        lines.append(f"- **Not part of any session** (startup checks and probes in this process): known "
                     f"{_usd(unallocated['known_usd'])} across {_count(unallocated['attempts'], 'request')}"
                     + (f", {unknown} of them with unknown cost." if unknown else "."))
    lines += ["", urc.LABELS["history"]]

    comparisons = report["comparisons"]
    if comparisons["columns"]:
        lines += ["", f"### {urc.LABELS['auto']}", urc.LABELS["b1"], "", urc.LABELS["auto_question"], ""]
        lines += ["| Reference | Prices as of | At reference prices | Savings | Savings % | Status |", "|---|---|---|---|---|---|"]
        for column in comparisons["columns"]:
            status = "complete" if column["complete"] else _reasons(column["reasons"], _COLUMN_REASONS)
            if column["unpriced"]:
                status += " (" + ", ".join(f"{u['attempts']} {_UNPRICED.get(u['reason'], u['reason'])}" for u in column["unpriced"]) + ")"
            savings = _usd(column["savings_usd"]) if column["savings_usd"] is not None else urc.LABELS["not_definitive"]
            percent = f"{column['savings_percent']}%" if column["savings_percent"] is not None else "—"
            lines.append(f"| {_text(column['display'])} | {column['price_as_of'] or 'unknown'} | "
                         f"{_usd(column['baseline_known_usd'])} | {savings} | {percent} | {_text(status, 200)} |")
        shown = comparisons["offset"] + len(comparisons["columns"])
        first = comparisons["offset"] + 1
        lines += ["", (f"Reference {first} of {comparisons['total']}. " if first == shown else f"References {first}–{shown} of {comparisons['total']}. ")
                  + urc.LABELS["cache_writes"]]

    lines += ["", f"### {urc.LABELS['b2']}", urc.LABELS["b2_unavailable"], "", f"### {urc.LABELS['b3']}",
              urc.LABELS["b3_unavailable"]]
    benchmark = report["benchmark"]
    if benchmark is not None:
        lines += ["", f"### {urc.LABELS['b4']}", _text(benchmark["text"], 512),
                  f"*{_text(benchmark['limitations'], 512)}* Source: {_text(benchmark['source'], 300)}"
                  + (f", {benchmark['as_of']}." if benchmark["as_of"] else ".")]

    if report["detail"]:
        lines += ["", "### Requests", "| Turn | Stage | Outcome | Selection | Model | Cost | Tokens in / cached / out |",
                  "|---|---|---|---|---|---|---|"]
        for row in report["detail"]:
            tokens = " / ".join("?" if row[k] is None else str(row[k]) for k in ("input_tokens", "cached_tokens", "output_tokens"))
            flags = " (late)" if row["late"] else ""
            flags += " (conflict)" if row["conflict"] else ""
            lines.append(f"| {_text(row['turn_id'])} | {_text(row['stage'])} | {_text(row['outcome'])}{flags} | "
                         f"{row['selection'] or 'unknown'} | {_text(row['resolved_model'] or row['requested_model'] or 'unknown')} | "
                         f"{_usd(row['cost_usd'])} | {tokens} |")
    if report["next_cursor"] is not None:
        lines += ["", f"More of this report: `/savings next {report['next_cursor']}`"]
    lines += ["", f"_Ledger {report['ledger_instance'][:8]}, as of {report['as_of']}._"]
    return "\n".join(lines)
