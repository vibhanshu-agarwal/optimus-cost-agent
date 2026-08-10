"""R9 orthogonality characterization for durable signing-key custody.

Task 0 gate: custody may change key *provenance* only. Issuer/validator signatures,
token claim set (except random ``token_id``), ``eh1.`` framing, and HMAC construction
must remain unchanged through the custody increment.

Clarification (operator 2026-08-10): literal byte-identical token bodies are
unachievable because ``CredentialIssuer.issue`` mints ``token_id`` via
``secrets.token_urlsafe(16)`` with no injection seam. Criterion 3 is enforced as
exact claim-key-set equality plus value equality for every claim except
``token_id``, plus well-formed ``token_id`` and framing/HMAC checks. Do not
monkeypatch ``secrets.token_urlsafe``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import inspect
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

_EXPECTED_CLAIM_KEYS = frozenset(
    {
        "principal_id",
        "agent_id",
        "caller_role",
        "issuer",
        "audience",
        "scope",
        "expires_at",
        "token_id",
        "instance_id",
    }
)
_TOKEN_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_TOKEN_PREFIX = "eh1."


def _enrollment():
    from evidence_handoff_runtime.auth import Enrollment

    return Enrollment(
        principal_id="principal-reviewer",
        agent_id="reviewer-1",
        caller_role="reviewer",
        scopes=frozenset({"ledger.write", "ledger.read"}),
        instance_id="ledger-inst-1",
    )


def _issuer(*, signing_key: bytes):
    from evidence_handoff_runtime.auth import CredentialIssuer

    enrollment = _enrollment()
    return CredentialIssuer(
        signing_key=signing_key,
        issuer="evidence-handoff-runtime",
        audience="evidence-handoff",
        enrollments={("ledger-inst-1", enrollment.principal_id): enrollment},
        now=lambda: datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
        default_ttl=timedelta(minutes=5),
    )


def _decode_token_parts(token: str) -> tuple[str, dict[str, object], bytes]:
    assert token.startswith(_TOKEN_PREFIX)
    remainder = token[len(_TOKEN_PREFIX) :]
    body_b64, signature_b64 = remainder.split(".", 1)
    padded_body = body_b64 + "=" * (-len(body_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded_body.encode("ascii")).decode("utf-8"))
    assert isinstance(payload, dict)
    padded_sig = signature_b64 + "=" * (-len(signature_b64) % 4)
    signature = base64.urlsafe_b64decode(padded_sig.encode("ascii"))
    return body_b64, payload, signature


def test_r9_credential_issuer_issue_signature_unchanged() -> None:
    from evidence_handoff_runtime.auth import CredentialIssuer

    sig = inspect.signature(CredentialIssuer.issue)
    assert list(sig.parameters) == ["self", "instance_id", "enrollment"]
    assert sig.parameters["instance_id"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["enrollment"].kind is inspect.Parameter.KEYWORD_ONLY
    assert (
        str(sig) == "(self, *, instance_id: 'str', enrollment: 'Enrollment') -> 'str'"
    )


def test_r9_credential_validator_validate_signature_unchanged() -> None:
    from evidence_handoff_runtime.auth import CredentialValidator

    sig = inspect.signature(CredentialValidator.validate)
    assert list(sig.parameters) == ["self", "header", "request"]
    assert sig.parameters["header"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert sig.parameters["request"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert (
        str(sig)
        == "(self, header: 'str', request: 'Mapping[str, Any]') -> 'AuthenticatedPrincipal'"
    )


def test_r9_token_claim_set_stable_excluding_random_token_id() -> None:
    """Same logical inputs + stubbed time → identical claims except random token_id."""
    signing_key = b"unit-signing-key-32-bytes-xxxxxx"
    issuer = _issuer(signing_key=signing_key)
    enrollment = _enrollment()

    token_a = issuer.issue(instance_id="ledger-inst-1", enrollment=enrollment)
    token_b = issuer.issue(instance_id="ledger-inst-1", enrollment=enrollment)

    _, payload_a, _ = _decode_token_parts(token_a)
    _, payload_b, _ = _decode_token_parts(token_b)

    assert set(payload_a) == _EXPECTED_CLAIM_KEYS
    assert set(payload_b) == _EXPECTED_CLAIM_KEYS
    assert "kid" not in payload_a
    assert "kid" not in payload_b

    stable_a = {k: v for k, v in payload_a.items() if k != "token_id"}
    stable_b = {k: v for k, v in payload_b.items() if k != "token_id"}
    assert stable_a == stable_b
    assert stable_a == {
        "principal_id": "principal-reviewer",
        "agent_id": "reviewer-1",
        "caller_role": "reviewer",
        "issuer": "evidence-handoff-runtime",
        "audience": "evidence-handoff",
        "scope": ["ledger.read", "ledger.write"],
        "expires_at": "2026-08-08T12:05:00+00:00",
        "instance_id": "ledger-inst-1",
    }

    for payload in (payload_a, payload_b):
        token_id = payload["token_id"]
        assert isinstance(token_id, str)
        assert token_id
        assert _TOKEN_ID_RE.fullmatch(token_id)
        assert len(token_id) >= 16
    assert payload_a["token_id"] != payload_b["token_id"]


def test_r9_distinct_provenance_paths_preserve_claim_set_and_hmac_construction(
    tmp_path: Path,
) -> None:
    """Mint-via-resolve and load-via-keyring are distinct provenance paths with identical bytes.

    Custody may change how bytes are obtained; issuer framing/HMAC/claim rules stay fixed.
    """
    from evidence_handoff_runtime.signing_key_custody import load_signing_key, resolve_signing_key

    class _FakeKeyring:
        def __init__(self) -> None:
            self._store: dict[tuple[str, str], str] = {}

        def get_password(self, service: str, key: str) -> str | None:
            return self._store.get((service, key))

        def set_password(self, service: str, key: str, value: str) -> None:
            self._store[(service, key)] = value

    control_root = tmp_path / "control"
    control_root.mkdir()
    keyring = _FakeKeyring()

    key_from_lifecycle_resolution = resolve_signing_key(
        control_root=control_root,
        keyring_backend=keyring,
        instance_record_present=False,
        store_instance_present=False,
    )
    key_from_keyring_load = load_signing_key(control_root=control_root, keyring_backend=keyring)
    assert key_from_lifecycle_resolution == key_from_keyring_load
    assert len(key_from_lifecycle_resolution) == 32

    issuer_a = _issuer(signing_key=key_from_lifecycle_resolution)
    issuer_b = _issuer(signing_key=key_from_keyring_load)
    enrollment = _enrollment()

    token_a = issuer_a.issue(instance_id="ledger-inst-1", enrollment=enrollment)
    token_b = issuer_b.issue(instance_id="ledger-inst-1", enrollment=enrollment)

    body_a, payload_a, sig_a = _decode_token_parts(token_a)
    body_b, payload_b, sig_b = _decode_token_parts(token_b)

    assert token_a.startswith(_TOKEN_PREFIX)
    assert token_b.startswith(_TOKEN_PREFIX)
    assert token_a.count(".") == 2
    assert token_b.count(".") == 2

    stable_a = {k: v for k, v in payload_a.items() if k != "token_id"}
    stable_b = {k: v for k, v in payload_b.items() if k != "token_id"}
    assert set(payload_a) == _EXPECTED_CLAIM_KEYS
    assert set(payload_b) == _EXPECTED_CLAIM_KEYS
    assert stable_a == stable_b

    expected_a = hmac.new(key_from_lifecycle_resolution, body_a.encode("ascii"), hashlib.sha256).digest()
    expected_b = hmac.new(key_from_keyring_load, body_b.encode("ascii"), hashlib.sha256).digest()
    assert hmac.compare_digest(expected_a, sig_a)
    assert hmac.compare_digest(expected_b, sig_b)


def test_r9_eh1_framing_and_hmac_sha256_construction() -> None:
    from evidence_handoff_runtime.auth import CredentialValidator

    signing_key = b"unit-signing-key-32-bytes-xxxxxx"
    issuer = _issuer(signing_key=signing_key)
    token = issuer.issue(instance_id="ledger-inst-1", enrollment=_enrollment())

    assert token.startswith(_TOKEN_PREFIX)
    parts = token[len(_TOKEN_PREFIX) :].split(".")
    assert len(parts) == 2
    body_b64, signature_b64 = parts

    expected = hmac.new(signing_key, body_b64.encode("ascii"), hashlib.sha256).digest()
    padded = signature_b64 + "=" * (-len(signature_b64) % 4)
    provided = base64.urlsafe_b64decode(padded.encode("ascii"))
    assert hmac.compare_digest(expected, provided)

    # Body is compact sorted JSON over the expected claim keys only.
    padded_body = body_b64 + "=" * (-len(body_b64) % 4)
    raw_body = base64.urlsafe_b64decode(padded_body.encode("ascii"))
    assert raw_body == json.dumps(
        json.loads(raw_body.decode("utf-8")),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    payload = json.loads(raw_body.decode("utf-8"))
    assert set(payload) == _EXPECTED_CLAIM_KEYS

    validator = CredentialValidator(
        signing_key=signing_key,
        expected_issuer="evidence-handoff-runtime",
        expected_audience="evidence-handoff",
        enrollments={("ledger-inst-1", "principal-reviewer"): _enrollment()},
        now=lambda: datetime(2026, 8, 8, 12, 0, 30, tzinfo=UTC),
        revoked_token_ids=frozenset(),
        consumed_jti=set(),
    )
    principal = validator.validate(
        f"Bearer {token}",
        {"ledger_instance_id": "ledger-inst-1"},
    )
    assert principal.token_id == payload["token_id"]
