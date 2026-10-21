"""Complete Gateway response bodies for the correction plan v4 scenarios (C1, C2, C9; Codex round 19 finding 5).

This module uses only APIs present both at checkpoint 4 (`72947dba`) and at the head under test, and it fixes every
id and clock. The same code therefore produced the kept baseline (`wire_baseline_72947dba.json`, generated from a
clone of `72947dba`) and produces the bodies compared against it. The correction must leave every body unchanged.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import optimus_gateway.responses as gateway_responses
from optimus_gateway.responses import handle_responses_request
from optimus_gateway.upstream_client import UpstreamAttemptFailure, UrllibOpenAICompatibleClient
from optimus_model_policy import stage_c
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.stage_c import StageCGuard
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

HAIKU = "anthropic/claude-haiku-5.5"
URL = "https://openrouter.ai/api/v1"
BARE_KEY = "sk-or-v1-" + "0123456789abcdef" * 4  # pragma: allowlist secret - synthetic credential-shaped canary
PROSE = "private note CANARY"
ROUTE_ID = "session-" + "1" * 32 + ":1:answer:1:" + "2" * 32
T0 = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


class _Ids:
    """A deterministic `uuid` stand-in for the Gateway's response module."""

    def __init__(self) -> None:
        self.issued = 0

    def uuid4(self) -> uuid.UUID:
        self.issued += 1
        return uuid.UUID(int=self.issued)


def _body(result: tuple[int, dict[str, Any]]) -> list[Any]:
    status, body = result
    return [status, json.loads(json.dumps(body, sort_keys=True, default=str))]


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


def _enforced(mp: pytest.MonkeyPatch, reply: bytes, *, request_id: str = ROUTE_ID) -> list[Any]:
    Wire(reply=http_reply(200, reply)).install(mp)
    policy = model_policy(profiles.compose_test_profile_snapshot("qualification"))
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url=URL, sleep=lambda _s: None)
    return _body(
        handle_responses_request(
            authorization_header=AUTH,
            request_body={"model": HAIKU, "input": "hi", "route_binding": binding(policy.snapshot, model=HAIKU, input_text="hi", output_cap=32_768, request_id=request_id)},
            config=gateway_config(policy),
            upstream_client=client,
        )
    )


def _legacy(mp: pytest.MonkeyPatch, wire: Wire | None, *, model: str = "anthropic/claude-haiku-4.5") -> list[Any]:
    if wire is not None:
        wire.install(mp)
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url=URL, sleep=lambda _s: None)
    return _body(handle_responses_request(authorization_header=AUTH, request_body={"model": model, "input": "hi"}, config=gateway_config(None), upstream_client=client))


class _Disk:
    """An fsync that fails, once armed, after ``ok`` more successful calls."""

    def __init__(self) -> None:
        self.armed, self.ok = False, 0

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

    def create_message_once(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        self._disk.armed, self._disk.ok = True, self._ok
        return super().create_message_once(**kwargs)


def _guarded_pair(root: Path, first: Callable[[_Disk], RecordingUpstream]) -> list[Any]:
    """Two requests on one Stage C ledger: the first arms the failing disk, the second meets the halted guard."""
    path = stage_c.stage_c_ledger_path(root / "runtime")
    envelope = stage_c.compose_stage_c_envelope(ledger=path)
    stage_c.initialize_stage_c_ledger(path, envelope, clock=lambda: T0)
    disk = _Disk()
    guard = StageCGuard.open(path, envelope, clock=lambda: T0, fsync=disk)
    policy = model_policy(verified_snapshot(root))
    config = dataclasses.replace(gateway_config(policy), stage_c_guard=guard)
    bodies = []
    try:
        for n, upstream in enumerate((first(disk), RecordingUpstream()), start=1):
            request_id = "session-" + "3" * 32 + f":{n}:answer:1:" + "4" * 32
            request = {"model": "cn/alpha", "input": "plan the change", "route_binding": binding(policy.snapshot, input_text="plan the change", request_id=request_id)}
            bodies.append(_body(handle_responses_request(authorization_header=AUTH, request_body=request, config=config, upstream_client=upstream)))
    finally:
        guard.close()
    return bodies


def _uncertain() -> UpstreamAttemptFailure:
    return UpstreamAttemptFailure("uncertain", http_status=502, failure={"kind": "http"})


SCENARIOS: dict[str, Callable[[pytest.MonkeyPatch, Path], Any]] = {
    "c1_positive": lambda mp, _root: _enforced(mp, _reply()),
    "c1_bare_key_reply_id": lambda mp, _root: _enforced(mp, _reply(reply_id=BARE_KEY)),
    "c1_prose_provider": lambda mp, _root: _enforced(mp, _reply(provider=PROSE)),
    "c1_registry_provider": lambda mp, _root: _enforced(mp, _reply(provider="openai")),
    "c1_prose_finish": lambda mp, _root: _enforced(mp, _reply(finish=PROSE)),
    "c1_prose_binding_request_id": lambda mp, _root: _enforced(mp, _reply(), request_id=PROSE),
    "c1_legacy_unsupported_model": lambda mp, _root: _legacy(mp, None, model=PROSE),
    "c2_settlement_write_failure": lambda _mp, root: _guarded_pair(root, lambda disk: _Arming(disk, ok=0)),
    "c2_failed_halt_after_halt": lambda _mp, root: _guarded_pair(root, lambda disk: _Arming(disk, ok=1, attempts=[_uncertain()])),
    "c9_transport_then_ok": lambda mp, _root: _legacy(
        mp, Wire(connect=ConnectionRefusedError(10061, PROSE), connect_failures=1, reply=http_reply(200, ok_completion_body()))
    ),
    "c9_503_then_ok": lambda mp, _root: _legacy(mp, Wire(replies=[http_reply(503, b"{}"), http_reply(200, ok_completion_body())])),
    "c9_timeout_then_ok": lambda mp, _root: _legacy(mp, Wire(replies=[TimeoutError(110, PROSE), http_reply(200, ok_completion_body())])),
    "c9_invalid_utf8": lambda mp, _root: _legacy(mp, Wire(reply=http_reply(200, b"\xff\xfe not utf-8"))),
    "c9_invalid_json": lambda mp, _root: _legacy(mp, Wire(reply=http_reply(200, b"{not json"))),
    "c9_schema": lambda mp, _root: _legacy(mp, Wire(reply=http_reply(200, b'{"choices": []}'))),
}


def run_all(root: Path) -> dict[str, Any]:
    """Every scenario's complete response bodies, each with fresh deterministic ids and no sleeping."""
    bodies: dict[str, Any] = {}
    for name, scenario in SCENARIOS.items():
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(gateway_responses, "uuid", _Ids())
            mp.setattr(gateway_responses, "_sleep", lambda _seconds: None)
            (root / name).mkdir(parents=True)
            bodies[name] = scenario(mp, root / name)
    return bodies
