"""Plan 12.2 diagnosability correction plan v4 (operator-approved 2026-10-21), the Gateway side.

C1: the persisted log line projects every id, upstream metadata value and refusal text to a recognized form;
the wire body is unchanged. C2: a Stage C ledger write failure is named in the log line of the request that hit
it and of every later halted refusal, never in a response body. C6: every module-authored reason slugs. C7:
malformed framing is a logged 400 and a failed log write never breaks a reply. C9: every failed legacy attempt is
logged with its own cause and shares one request-scoped Gateway id with the outcome.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import re
import socket
import sys
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import optimus_gateway.responses as gateway_responses
from optimus_gateway import request_diagnostics
from optimus_gateway.responses import assert_gateway_usage_contract, handle_responses_request, model_request_log_line
from optimus_gateway.server import serve_gateway
from optimus_gateway.upstream_client import UpstreamAttemptFailure, UrllibOpenAICompatibleClient
from optimus_model_policy import stage_c
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.stage_c import StageCGuard
from optimus_security.failure_facts import UNRECOGNIZED, slug
from tests.unit.optimus_gateway.model_policy_support import (
    AUTH,
    PROVIDER_KEY,
    RecordingUpstream,
    Wire,
    binding,
    gateway_config,
    http_reply,
    model_policy,
    ok_completion_body,
    verified_snapshot,
)
from tests.unit.optimus_gateway.test_server import _config

REPO = Path(__file__).resolve().parents[3]
HAIKU = "anthropic/claude-haiku-5.5"
_URL = "https://openrouter.ai/api/v1"
BARE_KEY = "sk-or-v1-" + "0123456789abcdef" * 4  # pragma: allowlist secret - synthetic credential-shaped canary
PROSE = "private note CANARY"
GW = r"gw-[0-9a-f]{32}"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway_responses, "_sleep", lambda _seconds: None)


def _host_route_id() -> str:
    return f"session-{uuid.uuid4().hex}:1:answer:1:{uuid.uuid4().hex}"


def _logged(policy: Any, run: Any, path: str = "/v1/responses") -> tuple[int, dict[str, Any], dict[str, Any], str]:
    """One request inside its request diagnostic context, as the server runs it: the reply, then its log line."""
    request_diagnostics.begin()
    try:
        status, body = run()
        line = model_request_log_line(path, status, body, policy=policy)
    finally:
        request_diagnostics.end()
    return status, body, json.loads(line), line


def _reply(*, reply_id: str = "gen-1760001234-AbCd", provider: str = "Anthropic", finish: str = "stop") -> bytes:
    return json.dumps(
        {
            "id": reply_id,
            "model": HAIKU,
            "choices": [{"message": {"content": "ok"}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11, "cost": "0.00001"},
            "openrouter_metadata": {
                "attempt": 1,
                "endpoints": {"total": 1, "available": [{"provider": provider, "model": HAIKU, "selected": True}]},
                "pipeline": [],
            },
        }
    ).encode()


def _enforced_over_wire(monkeypatch: pytest.MonkeyPatch, reply: bytes, *, request_id: str | None = None):
    """The enforced route through the real client and parser over the socket double."""
    Wire(reply=http_reply(200, reply)).install(monkeypatch)
    policy = model_policy(profiles.compose_test_profile_snapshot("qualification"))
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url=_URL, sleep=lambda _s: None)
    route_id = request_id or _host_route_id()

    def run():
        return handle_responses_request(
            authorization_header=AUTH,
            request_body={"model": HAIKU, "input": "hi", "route_binding": binding(policy.snapshot, model=HAIKU, input_text="hi", output_cap=32_768, request_id=route_id)},
            config=gateway_config(policy),
            upstream_client=client,
        )

    return (*_logged(policy, run), route_id)


# --- C1: projections through the real paths; the wire is unchanged --------------------------------------------------


def test_real_ids_and_recognized_metadata_survive_in_the_log(monkeypatch) -> None:
    status, body, line, _raw, route_id = _enforced_over_wire(monkeypatch, _reply())
    assert status == 200
    [attempt] = line["route_attempts"]
    assert attempt["provider_request_id"] == "gen-1760001234-AbCd"
    assert attempt["gateway_request_id"] == body["route_attempts"][0]["gateway_request_id"]
    assert line["route_request_id"] == route_id
    assert (line["usage"]["resolved_provider"], line["usage"]["resolved_model"]) == ("Anthropic", HAIKU)


def test_a_bare_credential_as_the_reply_id_never_reaches_the_log(monkeypatch) -> None:
    _status, body, line, raw, _route = _enforced_over_wire(monkeypatch, _reply(reply_id=BARE_KEY))
    assert BARE_KEY not in raw
    assert line["route_attempts"][0]["provider_request_id"] == UNRECOGNIZED
    assert body["route_attempts"][0]["provider_request_id"] == BARE_KEY  # the wire is unchanged


def test_a_prose_provider_is_projected_in_the_log_and_unchanged_on_the_wire(monkeypatch) -> None:
    status, body, line, raw, _route = _enforced_over_wire(monkeypatch, _reply(provider=PROSE))
    assert (status, body["code"]) == (422, "EMPIRICAL_PROVIDER_MISMATCH")
    assert PROSE in body["error"]  # the wire error is unchanged
    assert "private note" not in raw.lower()
    assert line["usage"]["resolved_provider"] == UNRECOGNIZED
    assert "'unrecognized'" in line["error"] and "'Anthropic'" in line["error"]


def test_a_registry_provider_keeps_its_slug_in_the_mismatch_log(monkeypatch) -> None:
    """Codex round 19 finding 2: a trusted registry provider slug that is not the route's survives in the log."""
    status, body, line, _raw, _route = _enforced_over_wire(monkeypatch, _reply(provider="openai"))
    assert (status, body["code"]) == (422, "EMPIRICAL_PROVIDER_MISMATCH")
    assert "'openai'" in line["error"] and line["usage"]["resolved_provider"] == "openai"


def test_a_prose_finish_status_is_projected_in_the_log_and_unchanged_on_the_wire(monkeypatch) -> None:
    status, body, line, raw, _route = _enforced_over_wire(monkeypatch, _reply(finish=PROSE))
    assert (status, body["code"]) == (422, "FINISH_STATUS_UNVERIFIED")
    assert PROSE.casefold() in body["error"]
    assert "private note" not in raw.lower()
    assert "'unrecognized'" in line["error"]


def test_a_prose_binding_request_id_is_projected_in_the_log(monkeypatch) -> None:
    status, body, line, raw, _route = _enforced_over_wire(monkeypatch, _reply(), request_id=PROSE)
    assert status == 200
    assert body["gateway_usage"]["route_request_id"] == PROSE  # the wire is unchanged
    assert line["route_request_id"] == UNRECOGNIZED and "private note" not in raw.lower()


def test_a_legacy_unsupported_model_is_logged_as_fixed_text() -> None:
    def run():
        return handle_responses_request(
            authorization_header=AUTH, request_body={"model": PROSE, "input": "hi"}, config=gateway_config(None), upstream_client=RecordingUpstream()
        )

    status, body, line, raw = _logged(None, run)
    assert (status, body["error"]) == (400, f"unsupported gateway model: {PROSE}")  # the wire is unchanged
    assert line["error"] == "unsupported gateway model" and "private note" not in raw.lower()


def test_a_bare_credential_in_a_refusal_text_is_redacted_from_the_log() -> None:
    line = model_request_log_line("/v1/responses", 400, {"error": f"refused {BARE_KEY}", "code": "X"})
    assert BARE_KEY not in line


# The reviewed interpolations in refusal texts (Codex rounds 14-15): ints, Gateway codes, constant names and
# trusted constants. Anything else must be projected for the log (`log_detail=`) or logged as fixed text. Each entry is
# keyed by call site, as file, enclosing qualified name and position among that name's refusal calls, and by the
# expression (R-13 item 4, #237 6322536508), so an interpolation reviewed at one site never covers another.
_REVIEWED_INTERPOLATIONS = {
    ("src/optimus_gateway/model_policy.py", "admit_request", 5, "policy.route_stop.code"),
    ("src/optimus_gateway/model_policy.py", "check_experimental_reply", 3, "route.provider_name"),
    ("src/optimus_gateway/model_policy.py", "check_experimental_reply", 5, "attempt"),
    ("src/optimus_gateway/model_policy.py", "check_experimental_reply", 6, "', '.join(pipeline)"),
    ("src/optimus_gateway/model_policy.py", "check_experimental_reply", 7, "admitted.decision.input_tokens"),
    ("src/optimus_gateway/model_policy.py", "check_experimental_reply", 7, "result.input_tokens"),
    ("src/optimus_gateway/models.py", "GatewayServiceConfig.__post_init__", 1, "self.bind_host"),
    ("src/optimus_gateway/models.py", "GatewayServiceConfig.__post_init__", 3, "_GATEWAY_PROVIDER"),
    ("src/optimus_gateway/models.py", "GatewayServiceConfig.__post_init__", 3, "self.provider"),
    ("src/optimus_gateway/models.py", "GatewayServiceConfig.__post_init__", 5, "self.provider"),
    ("src/optimus_gateway/models.py", "GatewayServiceConfig.from_env", 1, "_GATEWAY_PROVIDER"),
    ("src/optimus_gateway/models.py", "GatewayServiceConfig.from_env", 1, "provider"),
    ("src/optimus_gateway/models.py", "GatewayServiceConfig.from_env", 2, "max_calls_name"),
    ("src/optimus_gateway/models.py", "_required_env", 1, "name"),
    ("src/optimus_gateway/providers.py", "build_upstream_client", 1, "config.provider"),
    ("src/optimus_gateway/responses.py", "assert_gateway_usage_contract", 1, "field"),
    ("src/optimus_gateway/tool_provider_http.py", "request_bytes.call", 1, "label"),
    ("src/optimus_gateway/tool_provider_http.py", "request_bytes.call", 2, "label"),
    ("src/optimus_gateway/tool_provider_http.py", "request_bytes.call", 3, "label"),
    ("src/optimus_gateway/tool_provider_http.py", "request_bytes.call", 4, "label"),
    ("src/optimus_gateway/tool_provider_http.py", "request_bytes.call", 5, "label"),
    ("src/optimus_gateway/tool_provider_http.py", "request_json.call", 1, "label"),
    ("src/optimus_gateway/tool_provider_http.py", "request_json.call", 2, "label"),
    ("src/optimus_gateway/tool_provider_http.py", "request_json.call", 3, "label"),
    ("src/optimus_gateway/tool_provider_http.py", "request_json.call", 4, "label"),
    ("src/optimus_gateway/tool_provider_http.py", "request_json.call", 5, "label"),
    ("src/optimus_gateway/tool_provider_http.py", "request_json.call", 6, "label"),
    ("src/optimus_gateway/upstream_client.py", "_optional_header_nonnegative_int", 1, "name"),
    ("src/optimus_gateway/upstream_client.py", "_optional_header_nonnegative_int", 2, "name"),
    ("src/optimus_gateway/upstream_client.py", "_optional_string", 1, "description"),
    ("src/optimus_gateway/upstream_client.py", "_required_nonnegative_int", 1, "field"),
    ("src/optimus_gateway/upstream_client.py", "_urlopen_json", 1, "label"),
    ("src/optimus_gateway/upstream_client.py", "_urlopen_json", 2, "exc.code"),
    ("src/optimus_gateway/upstream_client.py", "_urlopen_json", 2, "label"),
    ("src/optimus_gateway/upstream_client.py", "_urlopen_json", 3, "exc.code"),
    ("src/optimus_gateway/upstream_client.py", "_urlopen_json", 3, "label"),
    ("src/optimus_gateway/upstream_client.py", "_urlopen_json", 4, "fact.get('cause', fact['class'])"),
    ("src/optimus_gateway/upstream_client.py", "_urlopen_json", 4, "label"),
    ("src/optimus_gateway/upstream_client.py", "_urlopen_json", 5, "label"),
    ("src/optimus_gateway/upstream_client.py", "_urlopen_json", 6, "label"),
    ("src/optimus_model_policy/binding.py", "RouteBinding.from_wire", 3, "version"),
    ("src/optimus_model_policy/binding.py", "_exact_keys", 1, "sorted(missing)"),
    ("src/optimus_model_policy/binding.py", "_exact_keys", 2, "len(unknown)"),
    ("src/optimus_model_policy/binding.py", "_hex_digest", 1, "field"),
    ("src/optimus_model_policy/registry.py", "Policy.unambiguous_and_frozen", 1, "model_id"),
    ("src/optimus_model_policy/registry.py", "Policy.unambiguous_and_frozen", 2, "model_id"),
    ("src/optimus_model_policy/registry.py", "Policy.unambiguous_and_frozen", 2, "seen[folded]"),
    ("src/optimus_model_policy/stage_c.py", "StageCGuard._apply", 6, "kind"),
    ("src/optimus_model_policy/stage_c.py", "StageCGuard.admit", 5, "r.attempts"),
    ("src/optimus_model_policy/stage_c.py", "StageCGuard.admit", 5, "self.envelope.max_attempts"),
    ("src/optimus_model_policy/stage_c.py", "StageCGuard.admit", 6, "r.charged"),
    ("src/optimus_model_policy/stage_c.py", "StageCGuard.admit", 6, "self.envelope.limit_usd"),
    ("src/optimus_model_policy/stage_c.py", "StageCGuard.admit", 7, "self._write_failure"),
}
_FIXED_TEXT_IN_THE_LOG = {("src/optimus_gateway/model_mapping.py", "resolve_model_id", 1, "normalized")}
# A refusal with `log_detail` (C1): its positional text reaches the response only, so its interpolations are pinned
# here; the log records `log_detail`, whose interpolations must each be a projection or a trusted constant.
_WIRE_ONLY_UNDER_LOG_DETAIL = {
    ("src/optimus_gateway/model_policy.py", "check_experimental_reply", 3, "provider"),
    ("src/optimus_gateway/model_policy.py", "check_finish_status", 1, "finish_reason"),
}
_LOG_PROJECTIONS = {
    ("src/optimus_gateway/model_policy.py", "check_experimental_reply", 3, "recognized_provider(provider, policy)"),
    ("src/optimus_gateway/model_policy.py", "check_experimental_reply", 3, "route.provider_name"),
    ("src/optimus_gateway/model_policy.py", "check_finish_status", 1, "bounded(finish_reason, RECOGNIZED_FINISH)"),
}
# Message arguments the control cannot read (`_unresolved`), each reviewed (R-13 item 4): a fixed code, a trusted
# constant, or a re-raised text that this control checks where it was made.
_UNRESOLVED_ARGUMENTS = {
    # `guard_request`'s `_refuse` codes, all literals in `optimus_model_policy/capacity.py`.
    ("src/optimus_gateway/model_policy.py", "admit_request", 6, "decision.reason or 'CAPACITY_REFUSED'"),
    # `_router_evidence` keeps only the RuntimeErrors its own helpers raise in `upstream_client.py`, checked here.
    ("src/optimus_gateway/model_policy.py", "check_experimental_reply", 1, "unreadable"),
    # A BindingError from `RouteBinding.from_wire`, whose code and detail are made in `binding.py`, checked here.
    ("src/optimus_gateway/model_policy.py", "parse_route_binding", 3, "exc.code"),
    ("src/optimus_gateway/model_policy.py", "parse_route_binding", 3, "exc.detail"),
    # A StageCRefusal from `StageCGuard.admit`, made in `stage_c.py`, checked here (Stage C test profiles only).
    ("src/optimus_gateway/responses.py", "_run_enforced_completion", 2, "exc.code"),
    ("src/optimus_gateway/responses.py", "_run_enforced_completion", 2, "exc.detail"),
    # The final transient failure's text: the operation's own refusals (`_urlopen_json`, `tool_provider_http.py`).
    ("src/optimus_gateway/upstream_client.py", "call_with_upstream_retry", 1, "str(exc)"),
    # The guard's halt reason: its own `_halt` texts (attempt numbers, charges) or its ledger's (Stage C test only).
    ("src/optimus_model_policy/stage_c.py", "StageCGuard.admit", 1, "r.halted"),
    # A name from the constant `STAGE_C_PROFILES`.
    ("src/optimus_model_policy/stage_c.py", "compose_stage_c_envelope", 2, "name"),
    # A reviewed profile constant, and an exception class name.
    ("src/optimus_model_policy/test_profiles.py", "compose_test_profile_snapshot", 2, "profile.unavailable_reason or 'not available'"),
    ("src/optimus_model_policy/test_profiles.py", "compose_test_profile_snapshot", 3, "type(exc).__name__"),
}
_REFUSALS = {"ModelPolicyRefusal", "BindingError", "StageCRefusal", "ValueError", "RuntimeError", "RetryableUpstreamError", "ModelRequestValidationError"}


_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _scope_nodes(scope: ast.AST) -> list[ast.AST]:
    """The nodes of `scope` itself: a nested function, lambda or class is another scope, so only its own node counts."""
    found, pending = [], list(ast.iter_child_nodes(scope))
    while pending:
        node = pending.pop()
        found.append(node)
        if not isinstance(node, _NESTED_SCOPES):
            pending.extend(ast.iter_child_nodes(node))
    return found


def _plain_assignments(name: str, scope: ast.AST) -> list[ast.expr] | None:
    """The values `name` gets from plain `name = value` statements in `scope`, or None when anything else there binds it:
    a parameter, `+=`, an annotated, unpacking or walrus assignment, a loop, `with`, `except`, an import, `global` or
    `nonlocal`, a nested definition or a pattern. Only then can its text be read from its assignments."""
    if isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef) and name in {node.arg for node in ast.walk(scope.args) if isinstance(node, ast.arg)}:
        return None
    values: list[ast.expr] = []
    stores = 0
    for node in _scope_nodes(scope):
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Store):
            stores += 1
        elif isinstance(node, ast.Assign):
            values += [node.value for target in node.targets if isinstance(target, ast.Name) and target.id == name]
        elif isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if node.name == name:
                return None
        elif isinstance(node, ast.MatchMapping) and node.rest == name:
            return None
        elif isinstance(node, ast.alias) and (node.asname or node.name.split(".")[0]) == name:
            return None
        elif isinstance(node, ast.Global | ast.Nonlocal) and name in node.names:
            return None
    return values if stores == len(values) else None


def _interpolations(expr: ast.expr, scope: ast.AST, depth: int = 0) -> list[str]:
    """The interpolated expressions of a message argument: an f-string's values, including any nested in a format spec
    (`f"{x:{width}}"`), either branch of a conditional, both sides of a concatenation, and a name's plain f-string
    assignments in the same scope, two hops deep (`message = f"…"`, `error = RuntimeError(message)`)."""
    if isinstance(expr, ast.JoinedStr):
        found = []
        for value in expr.values:
            if isinstance(value, ast.FormattedValue):
                found.append(ast.unparse(value.value))
                if value.format_spec is not None:
                    found += _interpolations(value.format_spec, scope, depth)
        return found
    if isinstance(expr, ast.IfExp):
        return _interpolations(expr.body, scope, depth) + _interpolations(expr.orelse, scope, depth)
    if isinstance(expr, ast.BinOp):
        return _interpolations(expr.left, scope, depth) + _interpolations(expr.right, scope, depth)
    if isinstance(expr, ast.Name) and depth < 2:
        return [found for value in _plain_assignments(expr.id, scope) or [] for found in _interpolations(value, scope, depth + 1)]
    return []


def _unresolved(expr: ast.expr, scope: ast.AST, depth: int = 0) -> list[str]:
    """The parts of a message argument whose text the control cannot read: anything but a literal, an f-string (its
    values are `_interpolations`), either branch of a conditional, both sides of a concatenation, and a name bound in its
    scope only by plain assignments of those (`_plain_assignments`), two hops deep. Each is reported as written."""
    if isinstance(expr, ast.Constant | ast.JoinedStr):
        return []
    if isinstance(expr, ast.IfExp):
        return _unresolved(expr.body, scope, depth) + _unresolved(expr.orelse, scope, depth)
    if isinstance(expr, ast.BinOp):
        return _unresolved(expr.left, scope, depth) + _unresolved(expr.right, scope, depth)
    if isinstance(expr, ast.Name) and depth < 2:
        assigned = _plain_assignments(expr.id, scope)
        if assigned and not any(_unresolved(value, scope, depth + 1) for value in assigned):
            return []
    return [ast.unparse(expr)]


def _refusal_calls(tree: ast.Module) -> list[tuple[ast.Call, ast.AST, str, int]]:
    """Every call of a refusal class anywhere in the module, raised directly or wrapped (`_with_failure(…)`), with its
    innermost enclosing function as the scope that resolves its names, and its site: the enclosing qualified name and its
    position among that name's refusal calls (the launch-inventory key, `tests/support/child_launch_inventory.py`)."""
    found: list[tuple[ast.Call, ast.AST, str, int]] = []
    ordinals: dict[str, int] = {}

    def visit(node: ast.AST, scope: ast.AST, qualname: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner, inner_name = scope, qualname
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                inner_name = f"{qualname}.{child.name}" if qualname else child.name
                if not isinstance(child, ast.ClassDef):
                    inner = child
            if isinstance(child, ast.Call):
                func = child.func
                name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
                if name in _REFUSALS:
                    site = qualname or "<module>"
                    ordinals[site] = ordinals.get(site, 0) + 1
                    found.append((child, scope, site, ordinals[site]))
            visit(child, inner, inner_name)

    visit(tree, tree, "")
    return found


def _tracked_sources() -> dict[str, str]:
    from tools.tracked_repository_files import tracked_repository_files

    paths = tracked_repository_files(REPO, pathspecs=("src/optimus_gateway", "src/optimus_model_policy"))
    return {path.relative_to(REPO).as_posix(): path.read_text(encoding="utf-8") for path in paths if path.suffix == ".py"}


def _control_findings(sources: dict[str, str]) -> tuple[list[str], set[tuple[str, str, int, str]]]:
    unreviewed, seen = [], set()
    for relative, text in sources.items():
        for call, scope, function, ordinal in _refusal_calls(ast.parse(text)):
            log_detail = [keyword.value for keyword in call.keywords if keyword.arg == "log_detail"]
            # The message: every argument but the `status` and `log_detail` keywords, so `detail=…` and `**kwargs` count.
            texts = (*call.args, *(keyword.value for keyword in call.keywords if keyword.arg not in {"status", "log_detail"}))
            positional = {(relative, function, ordinal, found) for argument in texts for found in _interpolations(argument, scope)}
            logged = {(relative, function, ordinal, found) for value in log_detail for found in _interpolations(value, scope)}
            unresolved = {
                (relative, function, ordinal, found) for argument in (*texts, *log_detail) for found in _unresolved(argument, scope)
            }
            seen |= positional | logged | unresolved
            allowed = _WIRE_ONLY_UNDER_LOG_DETAIL | _REVIEWED_INTERPOLATIONS if log_detail else _REVIEWED_INTERPOLATIONS | _FIXED_TEXT_IN_THE_LOG
            unreviewed += [f"{relative}:{call.lineno} {key[3]}" for key in sorted(positional - allowed)]
            unreviewed += [f"{relative}:{call.lineno} log_detail {key[3]}" for key in sorted(logged - _LOG_PROJECTIONS)]
            unreviewed += [f"{relative}:{call.lineno} unresolved {key[3]}" for key in sorted(unresolved - _UNRESOLVED_ARGUMENTS)]
    return unreviewed, seen


def _edited(relative: str, old: str, new: str) -> dict[str, str]:
    sources = _tracked_sources()
    assert sources[relative].count(old) == 1, old
    sources[relative] = sources[relative].replace(old, new)
    return sources


@pytest.mark.parametrize(
    ("relative", "old", "new"),
    (
        pytest.param(  # `body` is assigned a call, so the control cannot read what it holds
            "src/optimus_gateway/tool_provider_http.py",
            'raise RuntimeError(f"{label} response was not an object")\n        return body',
            'raise RuntimeError(f"{label} response was not an object", body)\n        return body',
            id="an-unresolved-argument",
        ),
        pytest.param(  # `name` is reviewed elsewhere in this file, never at this site
            "src/optimus_gateway/upstream_client.py",
            'RetryableUpstreamError(f"{label} request timed out")',
            'RetryableUpstreamError(f"{label} request timed out {name}")',
            id="a-new-interpolation-at-a-reviewed-site",
        ),
        pytest.param(  # the same reviewed `label`, in a refusal call the review never saw
            "src/optimus_gateway/tool_provider_http.py",
            'raise RuntimeError(f"{label} response was not an object")\n        return body',
            'raise RuntimeError(f"{label} response was not an object")\n'
            '        if not body:\n            raise RuntimeError(f"{label} response was empty")\n        return body',
            id="a-second-refusal-call-in-a-reviewed-function",
        ),
        pytest.param(  # the message passed by keyword, not by position
            "src/optimus_gateway/model_policy.py",
            'ModelPolicyRefusal("BINDING_REQUIRED", "requests must bind the trusted model registry")',
            'ModelPolicyRefusal("BINDING_REQUIRED", detail=str(raw))',
            id="a-keyword-message-argument",
        ),
        pytest.param(  # a reviewed f-string name, extended in place
            "src/optimus_gateway/upstream_client.py",
            'message = f"{label} request failed ({exc.code})"\n',
            'message = f"{label} request failed ({exc.code})"\n        message += str(exc)\n',
            id="an-augmented-assignment",
        ),
        pytest.param(  # a parameter, assigned a literal on one path only
            "src/optimus_gateway/models.py",
            'raise ValueError(f"{name} is required")\n',
            'if name.startswith("_"):\n            name = "a private variable"\n        raise ValueError(name)\n',
            id="a-parameter-assigned-on-one-path",
        ),
        pytest.param(  # a reviewed f-string name, rebound by an annotated assignment
            "src/optimus_gateway/upstream_client.py",
            'message = f"{label} request failed ({exc.code})"\n',
            'message = f"{label} request failed ({exc.code})"\n        message: str = str(exc)\n',
            id="an-annotated-rebinding",
        ),
        pytest.param(  # an interpolation nested in a reviewed field's format spec
            "src/optimus_gateway/upstream_client.py",
            'RetryableUpstreamError(f"{label} request timed out")',
            'RetryableUpstreamError(f"{label:{exc}} request timed out")',
            id="a-nested-format-field",
        ),
        pytest.param(  # a literal assigned only inside a nested function, which is another scope
            "src/optimus_gateway/tool_provider_http.py",
            'raise RuntimeError(f"{label} response was not an object")\n        return body',
            'def unrelated() -> None:\n                reason = "fixed"\n\n            raise RuntimeError(reason)\n        return body',
            id="an-assignment-in-a-nested-scope",
        ),
    ),
)
def test_the_refusal_text_control_fails_an_unreviewed_change(relative: str, old: str, new: str) -> None:
    """R-13 item 4 (#237 6322536508): reviewed entries are keyed by call site and expression text, and an argument the
    control cannot resolve must be pinned, so each of these edits to a reviewed function is reported."""
    assert _control_findings(_tracked_sources())[0] == []
    assert _control_findings(_edited(relative, old, new))[0] != []


def test_every_interpolated_refusal_text_is_reviewed_or_projected_for_the_log() -> None:
    unreviewed, seen = _control_findings(_tracked_sources())
    assert unreviewed == []
    # Not vacuous, and no stale entry: the wrapped and assigned sites (`_with_failure(…)`, `message = f"…"`) are seen,
    # and every reviewed, projected or pinned entry still names a live site.
    assert {("src/optimus_gateway/upstream_client.py", "exc.code"), ("src/optimus_gateway/model_policy.py", "attempt")} <= {
        (key[0], key[3]) for key in seen
    }
    pinned = _REVIEWED_INTERPOLATIONS | _FIXED_TEXT_IN_THE_LOG | _WIRE_ONLY_UNDER_LOG_DETAIL | _LOG_PROJECTIONS | _UNRESOLVED_ARGUMENTS
    assert pinned - seen == set()


def test_the_wire_bodies_match_the_72947dba_baseline(tmp_path) -> None:
    """Codex round 19 finding 5: the complete response bodies of the C1, C2 and C9 scenarios equal those checkpoint 4
    returned. `wire_baseline_72947dba.json` came from a clone of `72947dba` running these same scenarios, and
    `generate_wire_baseline.py` beside it regenerates it byte for byte; the bare-key canary is stored as a placeholder."""
    from tests.unit.optimus_gateway import wire_baseline_scenarios as scenarios

    source = (REPO / "tests/unit/optimus_gateway/wire_baseline_scenarios.py").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(source).hexdigest() == WIRE_BASELINE_SCENARIOS_SHA256, "regenerate the baseline from 72947dba"
    baseline = json.loads((REPO / "tests/unit/optimus_gateway/wire_baseline_72947dba.json").read_text(encoding="utf-8"))
    current = json.loads(json.dumps(scenarios.run_all(tmp_path), sort_keys=True).replace(scenarios.BARE_KEY, "<BARE_KEY>"))
    assert sorted(current) == sorted(baseline) and len(baseline) == 15
    assert {name: body for name, body in current.items() if body != baseline[name]} == {}


# The scenario module the baseline was generated from (generate_wire_baseline.py at 72947dba), LF-normalized.
WIRE_BASELINE_SCENARIOS_SHA256 = "d18ebe5a8ca7bcb4c67fb1bfd7cfc482c07aaf6b8c7d0bf936506f9514948daa"  # pragma: allowlist secret - a file digest


# --- C2: the ledger write fact is log-only --------------------------------------------------------------------------


class _Disk:
    """An fsync that fails, once armed, after ``ok`` more successful calls."""

    def __init__(self) -> None:
        self.armed = False
        self.ok = 0

    def __call__(self, _fd: int) -> None:
        if not self.armed:
            return
        if self.ok > 0:
            self.ok -= 1
            return
        raise OSError(28, f"No space left: {PROSE}")


class _Arming(RecordingUpstream):
    def __init__(self, disk: _Disk, *, ok: int, attempts: list[UpstreamAttemptFailure | None] | None = None) -> None:
        super().__init__(attempts=attempts)
        self._disk, self._ok = disk, ok

    def create_message_once(self, **kwargs: Any):
        self._disk.armed, self._disk.ok = True, self._ok
        return super().create_message_once(**kwargs)


@pytest.fixture
def ledger(tmp_path: Path):
    clock = lambda: datetime(2026, 10, 12, 9, 0, tzinfo=UTC)  # noqa: E731
    path = stage_c.stage_c_ledger_path(tmp_path / "runtime")
    envelope = stage_c.compose_stage_c_envelope(ledger=path)
    stage_c.initialize_stage_c_ledger(path, envelope, clock=clock)
    disk = _Disk()
    guard = StageCGuard.open(path, envelope, clock=clock, fsync=disk)
    policy = model_policy(verified_snapshot(tmp_path))
    yield policy, guard, disk
    guard.close()


def _guarded(policy, guard, upstream, request_id: str):
    config = dataclasses.replace(gateway_config(policy), stage_c_guard=guard)
    return lambda: handle_responses_request(
        authorization_header=AUTH,
        request_body={"model": "cn/alpha", "input": "plan the change", "route_binding": binding(policy.snapshot, input_text="plan the change", request_id=request_id)},
        config=config,
        upstream_client=upstream,
    )


def test_a_settlement_write_failure_is_logged_on_its_own_request_and_every_later_halt(ledger) -> None:
    policy, guard, disk = ledger
    status, body, line, raw = _logged(policy, _guarded(policy, guard, _Arming(disk, ok=0), _host_route_id()))
    assert status == 200 and "ledger_write_failure" not in json.dumps(body)
    assert line["ledger_write_failure"] == {"class": "OSError", "errno": 28}
    assert "private note" not in raw.lower()

    status, body, line, _raw = _logged(policy, _guarded(policy, guard, RecordingUpstream(), _host_route_id()))
    assert (status, body["code"]) == (503, "STAGE_C_HALTED")
    assert "ledger_write_failure" not in json.dumps(body)
    assert body["error"] == "model policy refused the request (STAGE_C_HALTED): ledger write failed (OSError errno 28)"  # unchanged
    assert line["ledger_write_failure"] == {"class": "OSError", "errno": 28}


def test_a_failed_halt_append_after_an_existing_halt_reason_keeps_both_facts_in_the_log(ledger) -> None:
    policy, guard, disk = ledger
    uncertain = UpstreamAttemptFailure("uncertain", failure={"kind": "http"}, http_status=502)
    _logged(policy, _guarded(policy, guard, _Arming(disk, ok=1, attempts=[uncertain]), _host_route_id()))  # the settle is durable, the halt is not

    status, body, line, _raw = _logged(policy, _guarded(policy, guard, RecordingUpstream(), _host_route_id()))
    assert (status, body["code"]) == (503, "STAGE_C_HALTED")
    assert body["error"].endswith("attempt 1 has an unknown charge")  # the wire detail is unchanged
    assert line["error"].endswith("attempt 1 has an unknown charge")
    assert line["ledger_write_failure"] == {"class": "OSError", "errno": 28}


# --- C6: every module-authored reason slugs --------------------------------------------------------------------------


def _module_reasons(relative: str, names: set[str]) -> list[str]:
    """Every literal or formatted reason raised as one of ``names`` in the module. An f-string is formatted with every
    lower-case string constant the module passes as a call argument: its field names (``"input token count"``),
    descriptions and labels."""
    tree = ast.parse((REPO / relative).read_text(encoding="utf-8"))
    constants = sorted(
        {
            arg.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            for arg in node.args
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and re.fullmatch(r"[a-z0-9 _.-]{1,60}", arg.value)
        }
    )
    reasons = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call) or not node.exc.args:
            continue
        func = node.exc.func
        if (func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)) not in names:
            continue
        message = node.exc.args[0]
        if isinstance(message, ast.Constant) and isinstance(message.value, str):
            reasons.append(message.value)
        elif isinstance(message, ast.JoinedStr):
            literal = "".join(part.value if isinstance(part, ast.Constant) else "{}" for part in message.values)
            reasons.extend(literal.replace("{}", value) for value in constants if literal.count("{}") == 1)
    return reasons


def test_every_upstream_and_usage_contract_reason_slugs_to_a_reason() -> None:
    reasons = _module_reasons("src/optimus_gateway/upstream_client.py", {"RuntimeError"})
    reasons += _module_reasons("src/optimus_gateway/responses.py", {"ValueError"})
    assert "upstream response missing choices[0]" in reasons
    assert [reason for reason in reasons if slug(reason) == UNRECOGNIZED] == []
    with pytest.raises(ValueError) as caught:
        assert_gateway_usage_contract({})
    assert slug(str(caught.value)) != UNRECOGNIZED


# --- C7 and C9: through the real server --------------------------------------------------------------------------


def _serve(upstream_client: Any = None):
    server = serve_gateway(config=_config(), upstream_client=upstream_client)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, thread, str(host), int(port)


def _stop(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _raw_post(host: str, port: int, path: str, body: bytes, *, length: str | None = None) -> tuple[int, dict[str, Any]]:
    """A POST over a plain socket (never ``socket.create_connection``, which the socket double replaces), so a test
    can send any framing."""
    head = f"POST {path} HTTP/1.1\r\nHost: {host}\r\nAuthorization: Bearer http-test-secret\r\nContent-Type: application/json\r\n"
    head += f"Content-Length: {len(body) if length is None else length}\r\nConnection: close\r\n\r\n"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(10)
        client.connect((host, port))
        client.sendall(head.encode("ascii") + body)
        received = b""
        while chunk := client.recv(65536):
            received += chunk
    status_line, _, rest = received.partition(b"\r\n")
    _headers, _, payload = rest.partition(b"\r\n\r\n")
    return int(status_line.split()[1]), json.loads(payload or b"{}")


def _log(capsys) -> list[dict[str, Any]]:
    return [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.startswith("{")]


@pytest.mark.parametrize("path", ["/v1/responses", "/v1/chat/completions"])
@pytest.mark.parametrize(
    ("body", "length", "error"),
    [(b"\xff\xfe{}", None, "invalid JSON"), (b"{}", "abc", "invalid content length"), (b"{}", "-5", "invalid content length")],
    ids=["invalid-utf8", "non-integer-length", "negative-length"],
)
def test_malformed_framing_is_a_logged_400_on_both_model_routes(capsys, path: str, body: bytes, length: str | None, error: str) -> None:
    server, thread, host, port = _serve(RecordingUpstream())
    try:
        status, reply = _raw_post(host, port, path, body, length=length)
    finally:
        _stop(server, thread)
    assert (status, reply) == (400, {"error": error})
    assert [(line["path"], line["status"], line["error"]) for line in _log(capsys) if line["event"] == "model_request"] == [(path, 400, error)]


class _ClosedStream:
    def write(self, _text: str) -> int:
        raise ValueError("I/O operation on closed file.")

    def flush(self) -> None:
        raise ValueError("I/O operation on closed file.")


def test_a_closed_log_stream_never_breaks_the_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("optimus_gateway.server.handle_responses_request", lambda **_kwargs: (200, {"output_text": "ok"}))
    server, thread, host, port = _serve(RecordingUpstream())
    try:
        monkeypatch.setattr(sys, "stderr", _ClosedStream())
        status, reply = _raw_post(host, port, "/v1/responses", b"{}")
    finally:
        monkeypatch.undo()
        _stop(server, thread)
    assert (status, reply) == (200, {"output_text": "ok"})


def _legacy_post(host: str, port: int) -> tuple[int, dict[str, Any]]:
    return _raw_post(host, port, "/v1/responses", json.dumps({"model": "anthropic/claude-haiku-4.5", "input": "hi"}).encode())


@pytest.mark.parametrize(
    ("wire", "status", "facts"),
    [
        (Wire(connect=ConnectionRefusedError(10061, PROSE), connect_failures=1, reply=http_reply(200, ok_completion_body())), 200,
         [{"kind": "transport", "class": "URLError", "cause": "ConnectionRefusedError", "errno": 10061}]),
        (Wire(replies=[http_reply(503, b"{}"), http_reply(200, ok_completion_body())]), 200, [{"kind": "http", "status": 503}]),
        (Wire(replies=[TimeoutError(110, PROSE), http_reply(200, ok_completion_body())]), 200, [{"kind": "transport", "class": "TimeoutError", "errno": 110}]),
        (Wire(reply=http_reply(200, b"\xff\xfe not utf-8")), 502, [{"kind": "invalid_utf8"}]),
        (Wire(reply=http_reply(200, b"{not json")), 502, [{"kind": "invalid_json"}]),
        (Wire(reply=http_reply(200, b'{"choices": []}')), 502, [{"kind": "schema", "reason": "upstream_response_missing_id"}]),
    ],
    ids=["transport-then-ok", "503-then-ok", "timeout-then-ok", "invalid-utf8", "invalid-json", "schema"],
)
def test_every_failed_legacy_attempt_is_logged_with_its_cause_and_the_request_id(monkeypatch, capsys, wire: Wire, status: int, facts: list) -> None:
    server, thread, host, port = _serve()  # the production upstream client and its retry observer
    wire.install(monkeypatch)
    try:
        replied, body = _legacy_post(host, port)
    finally:
        _stop(server, thread)
    log = _log(capsys)
    attempts = [line for line in log if line["event"] == "model_attempt"]
    [outcome] = [line for line in log if line["event"] == "model_request"]
    assert replied == status
    assert [line["failure"] for line in attempts] == facts
    ids = {line["gateway_request_id"] for line in attempts} | {outcome["gateway_request_id"]}
    assert len(ids) == 1 and re.fullmatch(GW, ids.pop())
    if status == 200:
        assert body["gateway_usage"]["gateway_request_id"] == outcome["gateway_request_id"]
    else:
        assert body["error"] in {"upstream response was invalid JSON", "upstream response missing id"}  # the wire text is unchanged
    assert "private note" not in json.dumps(log).lower()


def test_the_request_context_is_cleared_when_the_request_ends() -> None:
    request_diagnostics.begin()
    request_diagnostics.note(gateway_request_id=f"gw-{uuid.uuid4().hex}")
    assert request_diagnostics.noted()
    request_diagnostics.end()
    assert request_diagnostics.noted() == {}
    request_diagnostics.note(ledger_write_failure={"class": "OSError"})  # outside a request: ignored
    assert request_diagnostics.noted() == {}


def test_concurrent_legacy_requests_keep_their_own_request_ids(monkeypatch, capsys) -> None:
    server, thread, host, port = _serve()
    Wire(connect=ConnectionRefusedError(10061, "refused"), connect_failures=2, reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    results: list[tuple[int, dict[str, Any]]] = []
    try:
        workers = [threading.Thread(target=lambda: results.append(_legacy_post(host, port))) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=20)
    finally:
        _stop(server, thread)
    log = _log(capsys)
    outcomes = {line["gateway_request_id"] for line in log if line["event"] == "model_request"}
    assert len(outcomes) == 2
    assert {line["gateway_request_id"] for line in log if line["event"] == "model_attempt"} <= outcomes
    assert {body["gateway_usage"]["gateway_request_id"] for _status, body in results} == outcomes
