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
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from optimus.config.gateway import OptimusGatewaySettings
from optimus_security import usage_report_contract as urc

PAGE_SIZE = 25  # detail rows per rendered page (agent-selected); the Gateway bounds it again
READ_SECONDS = 20.0  # the Gateway's own deadlines total 15 s
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
    """POST to the report route with the host's Gateway URL and key, reading at most the contract's response bound."""
    settings.validate_trusted_gateway()
    url = settings.gateway_url.rstrip("/") + urc.PATH

    def post(body: bytes) -> tuple[int, Any]:
        headers = {**settings.auth_headers(), "Content-Type": "application/json", "Accept": "application/json"}
        deadline = time.monotonic() + timeout
        try:
            with urlopen(Request(url, data=body, headers=headers, method="POST"), timeout=timeout) as response:
                return response.status, _bounded_json(response, deadline)
        except HTTPError as exc:
            with exc:
                return exc.code, _bounded_json(exc, deadline)
        except TimeoutError:
            raise ReportTransportError("timeout") from None
        except (URLError, OSError):
            raise ReportTransportError("unreachable") from None

    return post


def _bounded_json(stream: Any, deadline: float) -> Any:
    """At most the contract's response bound, by a total deadline: a reply that drips in stops at it (each read waits
    at most the socket timeout, so the read ends within the deadline plus one timeout)."""
    raw = bytearray()
    while len(raw) <= urc.MAX_RESPONSE_BYTES:
        if time.monotonic() > deadline:
            raise ReportTransportError("timeout")
        chunk = stream.read1(64 * 1024) if hasattr(stream, "read1") else stream.read(64 * 1024)
        if not chunk:
            break
        raw += chunk
    if len(raw) > urc.MAX_RESPONSE_BYTES:
        raise ReportTransportError("too_large")
    try:
        return json.loads(bytes(raw))
    except (ValueError, UnicodeDecodeError):
        raise ReportTransportError("malformed") from None


Scope = Callable[[str], tuple[int, tuple[tuple[str, int], ...]]]


class SavingsReports:
    """One host's `/savings` source: the Gateway route and this host's own capture scope."""

    def __init__(self, post: Post, scope: Scope) -> None:
        self._post, self._scope = post, scope

    def markdown(self, session_id: str, command: SavingsCommand) -> str:
        """The rendered report or its stated failure; never raises for a Gateway or ledger state."""
        expected_turns, frontier = self._scope(session_id)
        request = urc.ReportRequest(session_id, command.turn_id, None, PAGE_SIZE, command.cursor,
                                    1 if command.turn_id is not None else expected_turns, frontier or None)
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
            return render_savings_report(urc.validate_report(body))
        except urc.ContractError:
            return _MALFORMED


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


def _totals_line(name: str, totals: Mapping[str, Any]) -> str:
    unknown = f", {totals['unknown_attempts']} with unknown cost" if totals["unknown_attempts"] else ""
    return (f"- **{name}:** {_usd(totals['known_usd'])} across {totals['attempts']} requests in {totals['turns']} turns"
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
        lines.append(f"- **Not part of any session** (startup checks and probes in this process): "
                     f"{_usd(unallocated['known_usd'])} across {unallocated['attempts']} requests.")
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
        lines += ["", f"References {comparisons['offset'] + 1}–{shown} of {comparisons['total']}. "
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
