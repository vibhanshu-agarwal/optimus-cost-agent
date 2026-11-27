"""#685: `raise_preserving_failure` re-raises the original failure object with its original cause and context, for every
exception type its callers can pass, including the frozen dataclass exceptions in `src` whose `__setattr__` refuses the
restoring assignment. The Gateway readiness path is driven for real: a stub child, and a stub listener on an ephemeral
loopback port that does not confirm its identity. Nothing real starts; synthetic values only."""

from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from optimus.acp import local_infra
from optimus.acp.bootstrap import StartupConfigurationError
from optimus.acp.errors import AcpOutboundError
from optimus.acp.launch_policy import LaunchPolicyError
from optimus.acp.local_gateway_secrets import CredentialLayer, CredentialProvenance, ProviderCredentialResolution, ProviderSecrets
from optimus.acp.local_infra import LocalInfrastructureError
from optimus.acp.preflight import PreflightFailure
from optimus.acp.process_lifecycle import raise_preserving_failure
from optimus.acp.request_ids import DuplicateRequestId
from optimus.acp.subprocess_env import SubprocessEnvConfigurationError
from optimus.runtime.mutation import MutationForbidden
from optimus_model_policy.binding import trusted_approval_literal
from tests.unit.acp.test_gateway_attach_wiring import _API_KEY, _KEY, _SECRET

# One instance per exception type in `src` that is a frozen dataclass (the #685 class sweep), plus the plain kinds the
# callers also pass: an ordinary exception, an OSError from a stop, and the BaseException kinds cleanup selects first.
FAILURES = {
    "LocalInfrastructureError": lambda: LocalInfrastructureError(code="SYNTHETIC", user_message="synthetic refusal"),
    "PreflightFailure": lambda: PreflightFailure(exit_code=2, user_message="synthetic preflight"),
    "StartupConfigurationError": lambda: StartupConfigurationError(exit_code=2, user_message="synthetic startup"),
    "SubprocessEnvConfigurationError": lambda: SubprocessEnvConfigurationError(message="synthetic env"),
    "LaunchPolicyError": lambda: LaunchPolicyError(code="SYNTHETIC"),
    "AcpOutboundError": lambda: AcpOutboundError(code=-32600, message="synthetic outbound"),
    "DuplicateRequestId": lambda: DuplicateRequestId(request_id=7),
    "MutationForbidden": lambda: MutationForbidden(message="synthetic mutation"),
    "RuntimeError": lambda: RuntimeError("synthetic"),
    "OSError": lambda: OSError("synthetic stop"),
    "CancelledError": asyncio.CancelledError,
    "KeyboardInterrupt": KeyboardInterrupt,
}


def _raise_while_handling(failure: BaseException) -> None:
    try:
        raise ValueError("unrelated, being handled when the failure is re-raised")
    except ValueError:
        raise_preserving_failure(failure)  # Python would set this as the failure's context; the helper undoes that


@pytest.mark.parametrize("chain", ["explicit-cause", "implicit-context", "none"])
@pytest.mark.parametrize("kind", sorted(FAILURES))
def test_the_original_failure_reaches_the_caller_with_its_own_cause_and_context(kind: str, chain: str) -> None:
    failure = FAILURES[kind]()
    cause, context = LookupError("synthetic cause"), TypeError("synthetic context")
    if chain == "explicit-cause":
        object.__setattr__(failure, "__cause__", cause)  # what `raise failure from cause` leaves
    if chain in ("explicit-cause", "implicit-context"):
        object.__setattr__(failure, "__context__", context)
    expected = (failure.__cause__, failure.__context__, failure.__suppress_context__)

    with pytest.raises(BaseException) as raised:  # noqa: PT011 - the assertion is identity, below
        _raise_while_handling(failure)

    assert raised.value is failure
    assert (raised.value.__cause__, raised.value.__context__, raised.value.__suppress_context__) == expected


class _Unconfirming(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - the http.server hook name
        self.send_response(404)  # not a Gateway: it cannot confirm its identity
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        return


def test_an_unconfirmed_listener_after_a_failed_stop_ends_in_the_value_free_refusal(monkeypatch, tmp_path: Path) -> None:
    provenance = CredentialProvenance(CredentialLayer.ENVIRONMENT, "test")
    credentials = ProviderCredentialResolution(
        secrets=ProviderSecrets(provider="openrouter", model_provider_api_key=_API_KEY, base_url="https://gw-synthetic.example/v1"),
        provider_provenance=provenance, api_key_provenance=provenance, base_url_provenance=provenance,
    )
    listener = ThreadingHTTPServer(("127.0.0.1", 0), _Unconfirming, bind_and_activate=False)
    listener.server_bind()  # the port is reserved but refuses connections until the "child" starts
    port = listener.server_address[1]
    serving = threading.Thread(target=listener.serve_forever, daemon=True)

    class Child:
        pid = 1
        returncode = None

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            raise OSError("synthetic: the stub child refuses to stop")

    def popen(_args: list[str], **_kwargs: Any) -> Child:
        listener.server_activate()  # the port answers only once the "child" is started, as a real Gateway's would
        serving.start()
        return Child()

    monkeypatch.setattr(local_infra.subprocess, "Popen", popen)
    try:
        with pytest.raises(LocalInfrastructureError) as raised:
            local_infra.ensure_local_gateway(
                gateway_url=f"http://127.0.0.1:{port}", provider_credentials=credentials, shared_secret=_SECRET,
                manifest_hmac_key=_KEY, workspace_digest="a" * 64, security_snapshot_digest="b" * 64,
                policy_version="P9.99-v1", runtime_root=tmp_path / "runtime", model_registry=trusted_approval_literal(),
            )
    finally:
        if serving.is_alive():
            listener.shutdown()
        listener.server_close()

    assert raised.value.code == "GATEWAY_IDENTITY_UNCONFIRMED"
    assert raised.value.user_message.startswith(f"Something is listening at http://127.0.0.1:{port}, but it did not confirm")
    # `raise unconfirmed from None` after the 404 reads as a malformed reply: that exact chain reaches the caller.
    assert raised.value.__cause__ is None and raised.value.__suppress_context__ is True
    assert isinstance(raised.value.__context__, local_infra.ReportTransportError)
    assert raised.value.__dict__["_optimus_cleanup_stages"] == ("gateway",)
