"""RED tests for fail-closed StructuredIngress over ledger EntryDraft (Task 7).

Covers populated canaries, deterministic sanitize, final-scan rejection, malformed
input, empty inventory, and no disk staging of unredacted drafts.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from evidence_handoff.ledger.models import (
    ArtifactRef,
    EntryDraft,
    EntryKind,
    EntryMessage,
    MessagePart,
    SanitizedDraft,
)


def _abs(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _inputs(
    tmp_path: Path,
    *,
    secrets: tuple[str, ...] = (),
    pii: tuple[str, ...] = (),
    path_root: Path | None = None,
):
    from evidence_handoff.redaction.ingress import RequestRedactionInputs
    from evidence_handoff.redaction.models import RedactionRuntimeInputs
    from optimus_security.sanitization import PathAliasRule
    from optimus_security.sensitive_values import SensitiveValueInventory, SensitiveValueSourceClass

    capture = _abs(tmp_path, "capture")
    staging = _abs(tmp_path, "staging")
    quarantine = _abs(tmp_path, "quarantine")
    forbidden = _abs(tmp_path, "forbidden")
    inventory = SensitiveValueInventory()
    for secret in secrets:
        inventory.add_secret(secret, source_class=SensitiveValueSourceClass.CONFIG_FILE)
    for value in pii:
        inventory.add_pii(value, source_class=SensitiveValueSourceClass.INJECTED_PII)
    alias_root = path_root or capture
    return RequestRedactionInputs(
        runtime=RedactionRuntimeInputs(
            sensitive_values=inventory,
            path_aliases=(PathAliasRule(source_root=str(alias_root), alias="<temp>"),),
            temporary_capture_root=capture,
            staging_root=staging,
            quarantine_root=quarantine,
            forbidden_persistence_roots=(forbidden,),
        )
    )


def _draft(
    *,
    text: str | None = None,
    parts: tuple[MessagePart, ...] | None = None,
    artifacts: tuple[ArtifactRef, ...] = (),
    context_id: str = "ctx-ingress-1",
    recipients: tuple[str, ...] = ("implementer-1",),
    task_id: str | None = None,
    in_reply_to: str | None = None,
) -> EntryDraft:
    message_parts = parts
    if message_parts is None:
        message_parts = (MessagePart(kind="text", text=text or "harmless ruling"),)
    return EntryDraft(
        kind=EntryKind.REVIEW_RULING,
        schema_id="review-ruling.v1",
        context_id=context_id,
        recipient_agent_ids=recipients,
        message=EntryMessage(parts=message_parts),
        artifacts=artifacts,
        task_id=task_id,
        in_reply_to=in_reply_to,
    )


def _file_tree_text(root: Path) -> str:
    chunks: list[str] = []
    for path in root.rglob("*"):
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def test_sanitize_accepts_only_entry_draft_not_text_stub(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import IngressRejection, StructuredIngress

    secret = "exact-secret-canary-alpha-7f2c"
    inputs = _inputs(tmp_path, secrets=(secret,), pii=("operator@example.test",))
    result = StructuredIngress().sanitize(
        _draft(text=f"ruling mentions {secret}"),
        inputs,
    )
    assert not isinstance(result, type("x", (), {}))  # placate type checkers
    assert isinstance(result, SanitizedDraft) or (
        isinstance(result, IngressRejection) and result.reason_code != "invalid_entry_draft"
    )
    # Narrow Task 1 stub must no longer be the accepted sanitize input.
    from evidence_handoff.redaction.ingress import IngressTextDraft

    rejected = StructuredIngress().sanitize(
        IngressTextDraft(kind="review-ruling", message_text="legacy"),  # type: ignore[arg-type]
        inputs,
    )
    assert getattr(rejected, "ok", True) is False
    assert getattr(rejected, "reason_code", "") == "invalid_entry_draft"


def test_exact_secret_and_request_credential_are_sanitized(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import StructuredIngress

    secret = "exact-secret-canary-alpha-7f2c"
    request_credential = "request-credential-canary-value"
    inputs = _inputs(tmp_path, secrets=(secret, request_credential), pii=("operator@example.test",))
    result = StructuredIngress().sanitize(
        _draft(text=f"body {secret} and {request_credential}"),
        inputs,
    )
    assert isinstance(result, SanitizedDraft)
    serialized = json.dumps(result.to_mapping(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    assert secret not in serialized
    assert request_credential not in serialized
    assert result.rule_counts
    assert secret not in repr(result)
    assert request_credential not in repr(result)


def test_pii_and_path_alias_are_sanitized(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import StructuredIngress

    pii = "operator@example.test"
    capture = _abs(tmp_path, "capture")
    leak_path = str(capture / "nested" / "secret.txt")
    inputs = _inputs(tmp_path, secrets=("svc-secret-alpha",), pii=(pii,), path_root=capture)
    result = StructuredIngress().sanitize(
        _draft(text=f"contact {pii} at path {leak_path}"),
        inputs,
    )
    assert isinstance(result, SanitizedDraft)
    blob = json.dumps(result.to_mapping())
    assert pii not in blob
    assert leak_path not in blob
    assert "<temp>" in blob or "path_alias" in str(result.rule_counts)


def test_split_secret_across_message_parts_hits_final_scan_or_is_sanitized(
    tmp_path: Path,
) -> None:
    from evidence_handoff.redaction.ingress import IngressRejection, StructuredIngress

    secret = "split-secret-canary-Q7mV2xN9pR4tY8kL"
    mid = len(secret) // 2
    left, right = secret[:mid], secret[mid:]
    inputs = _inputs(tmp_path, secrets=(secret,), pii=("operator@example.test",))
    result = StructuredIngress().sanitize(
        _draft(
            parts=(
                MessagePart(kind="text", text=f"prefix-{left}"),
                MessagePart(kind="text", text=f"{right}-suffix"),
            )
        ),
        inputs,
    )
    if isinstance(result, IngressRejection):
        assert result.reason_code == "final_scan_hit"
        assert secret not in repr(result)
        return
    assert isinstance(result, SanitizedDraft)
    blob = json.dumps(result.to_mapping())
    assert secret not in blob
    assert left + right not in blob.replace('","', "")


def test_base64_encoded_secret_fails_final_scan(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import IngressRejection, StructuredIngress

    secret = "encoded-secret-canary-9f3a21bb"
    encoded = base64.b64encode(secret.encode("utf-8")).decode("ascii")
    inputs = _inputs(tmp_path, secrets=(secret,), pii=("operator@example.test",))
    result = StructuredIngress().sanitize(
        _draft(text=f"token={encoded}"),
        inputs,
    )
    assert isinstance(result, IngressRejection)
    assert result.reason_code == "final_scan_hit"
    assert secret not in repr(result)
    assert encoded not in repr(result) or result.reason_code == "final_scan_hit"


def test_entropy_candidate_is_redacted(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import StructuredIngress

    # High-entropy unlabeled token (>=24 chars, mixed classes) under evidence policy.
    entropy_token = "Q7mV2xN9pR4tY8kL3cD6wF1hJ5sB0zUa"
    inputs = _inputs(tmp_path, secrets=("svc-secret-alpha",), pii=("operator@example.test",))
    result = StructuredIngress().sanitize(
        _draft(text=f"candidate {entropy_token} trailing"),
        inputs,
    )
    assert isinstance(result, SanitizedDraft)
    blob = json.dumps(result.to_mapping())
    assert entropy_token not in blob
    assert int(result.rule_counts.get("entropy_redaction", 0)) >= 1


def test_deterministic_sanitize_output(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import StructuredIngress

    secret = "det-secret-canary-alpha"
    inputs = _inputs(tmp_path, secrets=(secret,), pii=("operator@example.test",))
    draft = _draft(text=f"stable body with {secret}")
    first = StructuredIngress().sanitize(draft, inputs)
    second = StructuredIngress().sanitize(draft, inputs)
    assert isinstance(first, SanitizedDraft)
    assert isinstance(second, SanitizedDraft)
    assert first.to_mapping() == second.to_mapping()
    assert first.rule_counts == second.rule_counts
    payload = json.dumps(first.to_mapping(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert len(digest) == 64


def test_empty_inventory_rejects_without_leaking(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import IngressRejection, StructuredIngress

    inputs = _inputs(tmp_path, secrets=(), pii=())
    result = StructuredIngress().sanitize(_draft(text="harmless"), inputs)
    assert isinstance(result, IngressRejection)
    assert result.reason_code == "empty_runtime_inventory"


def test_malformed_draft_type_rejected(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import IngressRejection, StructuredIngress

    inputs = _inputs(tmp_path, secrets=("svc-secret-alpha",), pii=("operator@example.test",))
    result = StructuredIngress().sanitize({"kind": "review-ruling"}, inputs)  # type: ignore[arg-type]
    assert isinstance(result, IngressRejection)
    assert result.reason_code == "invalid_entry_draft"


def test_artifact_metadata_with_secret_fails_final_scan(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import IngressRejection, StructuredIngress

    secret = "artifact-name-secret-canary"
    digest = hashlib.sha256(b"blob").hexdigest()
    inputs = _inputs(tmp_path, secrets=(secret,), pii=("operator@example.test",))
    result = StructuredIngress().sanitize(
        _draft(
            text="clean ruling text",
            artifacts=(
                ArtifactRef(
                    name=f"note-{secret}",
                    content_sha256=digest,
                    uri=f"file:///tmp/{secret}.bin",
                ),
            ),
        ),
        inputs,
    )
    assert isinstance(result, IngressRejection)
    assert result.reason_code in {"final_scan_hit", "artifact_metadata_rejected"}
    assert secret not in repr(result)


def test_sanitize_does_not_stage_draft_on_disk(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import StructuredIngress

    secret = "disk-staging-secret-canary"
    inputs = _inputs(tmp_path, secrets=(secret,), pii=("operator@example.test",))
    forbidden = inputs.runtime.forbidden_persistence_roots[0]
    staging = inputs.runtime.staging_root
    result = StructuredIngress().sanitize(_draft(text=f"body {secret}"), inputs)
    # Must accept EntryDraft and sanitize in memory — rejection here is not a pass.
    assert isinstance(result, SanitizedDraft)
    assert secret not in json.dumps(result.to_mapping())
    assert secret not in _file_tree_text(forbidden)
    assert secret not in _file_tree_text(staging)


def test_data_part_structured_values_are_sanitized(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import StructuredIngress

    secret = "data-part-secret-canary"
    inputs = _inputs(tmp_path, secrets=(secret,), pii=("operator@example.test",))
    result = StructuredIngress().sanitize(
        _draft(
            parts=(
                MessagePart(kind="text", text="ruling"),
                MessagePart(kind="data", data={"detail": f"contains {secret}"}),
            )
        ),
        inputs,
    )
    assert isinstance(result, SanitizedDraft)
    blob = json.dumps(result.to_mapping())
    assert secret not in blob


def test_entropy_canary_in_context_id_is_rejected(tmp_path: Path) -> None:
    """Residual entropy rewrite must reject — not return a leaky SanitizedDraft."""
    from evidence_handoff.redaction.ingress import IngressRejection, StructuredIngress

    entropy_token = "Q7mV2xN9pR4tY8kL3cD6wF1hJ5sB0zUa"
    inputs = _inputs(tmp_path, secrets=("svc-secret-alpha",), pii=("operator@example.test",))
    result = StructuredIngress().sanitize(
        _draft(text="clean ruling body", context_id=f"ctx-{entropy_token}"),
        inputs,
    )
    assert isinstance(result, IngressRejection)
    assert result.reason_code == "final_scan_hit"
    assert entropy_token not in repr(result)


def test_entropy_canary_in_task_id_is_rejected(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import IngressRejection, StructuredIngress

    entropy_token = "Q7mV2xN9pR4tY8kL3cD6wF1hJ5sB0zUa"
    inputs = _inputs(tmp_path, secrets=("svc-secret-alpha",), pii=("operator@example.test",))
    result = StructuredIngress().sanitize(
        _draft(text="clean ruling body", task_id=f"task-{entropy_token}"),
        inputs,
    )
    assert isinstance(result, IngressRejection)
    assert result.reason_code == "final_scan_hit"
    assert entropy_token not in repr(result)


def test_entropy_canary_in_in_reply_to_is_rejected(tmp_path: Path) -> None:
    from evidence_handoff.redaction.ingress import IngressRejection, StructuredIngress

    entropy_token = "Q7mV2xN9pR4tY8kL3cD6wF1hJ5sB0zUa"
    inputs = _inputs(tmp_path, secrets=("svc-secret-alpha",), pii=("operator@example.test",))
    result = StructuredIngress().sanitize(
        _draft(text="clean ruling body", in_reply_to=f"entry-{entropy_token}"),
        inputs,
    )
    assert isinstance(result, IngressRejection)
    assert result.reason_code == "final_scan_hit"
    assert entropy_token not in repr(result)
