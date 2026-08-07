"""P11-FU-9 Task 9: closure evidence must name every required claim and custody link."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CLOSURE_EVIDENCE = REPO_ROOT / "reports" / "p11-fu-9-client-mcp-closure-evidence.md"
DESIGN_SPEC = (
    REPO_ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-design.md"
)
APPROVED_DESIGN_DIGEST = "66606036b37ddc59cf9f2f4c8a713156a1f839fb771679a16937a5263c9ca4a2"
TERRAFORM_IMAGE_DIGEST = (
    "sha256:bd095e2b442a2cb61255fe4db52f9e824f35d307a2044784c95d37a93f18d324"
)
CONTEXT7_NEGOTIATED_VERSION = "2025-11-25"

REQUIRED_DEFERRAL_HEADERS = (
    "Durable client-MCP descriptor-surface pinning and named tool allowlists",
    "Client-MCP durable HTTP/SSE trust relaxation",
    "Authenticated client-owned MCP upstream evidence",
)
PLAN_118_FLAKE_HEADER = "Plan 11.8 Windows `WinError 10053` MCP test flake"
SESSION_LOAD_OWNER = "P11-FEAT-ZED-RESUME"


def _design_body_digest() -> str:
    text = DESIGN_SPEC.read_text(encoding="utf-8").replace("\r\n", "\n")
    idx = text.find("**Frozen design-body SHA-256:**")
    assert idx >= 0, "design spec missing frozen digest header"
    end = text.find("\n", idx)
    body = text[:idx] + text[end + 1 :]
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _closure_text() -> str:
    assert CLOSURE_EVIDENCE.is_file(), f"missing closure evidence: {CLOSURE_EVIDENCE}"
    return CLOSURE_EVIDENCE.read_text(encoding="utf-8")


def test_approved_design_digest_still_matches_frozen_body() -> None:
    assert _design_body_digest() == APPROVED_DESIGN_DIGEST


def test_closure_evidence_names_approved_design_digest() -> None:
    text = _closure_text()
    assert APPROVED_DESIGN_DIGEST in text


def test_closure_evidence_names_real_dependency_artifacts() -> None:
    text = _closure_text()
    assert TERRAFORM_IMAGE_DIGEST in text
    assert CONTEXT7_NEGOTIATED_VERSION in text
    assert "mcp" in text.lower()
    assert re.search(r"httpx2\.AsyncClient|injected.*httpx2", text, re.I)
    assert re.search(r"byte[- ]budget|REMOTE_BYTE_OVERFLOW", text, re.I)


def test_closure_evidence_names_scanner_credential_and_surface_boundaries() -> None:
    text = _closure_text()
    assert re.search(r"scanner|ConfigTrustScanner|PreToolGuard", text, re.I)
    assert re.search(r"credential", text, re.I)
    assert re.search(r"transport", text, re.I)
    assert re.search(r"generic[- ]tool", text, re.I)


def test_closure_evidence_names_session_new_allow_once_timeout_and_shutdown() -> None:
    text = _closure_text()
    assert re.search(r"session/new", text)
    assert re.search(r"allow[_ -]?once", text, re.I)
    assert re.search(r"timeout", text, re.I)
    assert re.search(r"shutdown|teardown", text, re.I)


def test_closure_evidence_names_classifier_distributions() -> None:
    text = _closure_text()
    assert re.search(r"Terraform", text)
    assert re.search(r"Context7", text)
    assert re.search(r"tokenized", text, re.I)
    assert re.search(r"legacy", text, re.I)
    assert "read=9" in text or '"read": 9' in text or "read: 9" in text
    assert "read=2" in text or '"read": 2' in text or "read: 2" in text


def test_closure_evidence_names_acpx_empty_array_and_transport_evidence() -> None:
    text = _closure_text()
    assert re.search(r"acpx", text, re.I)
    assert re.search(r"empty[- ]array|mcpServers.*\[\]|empty mcpServers", text, re.I)
    assert re.search(r"stdio|HTTP|SSE", text)


def test_closure_evidence_names_session_load_exclusion_owner() -> None:
    text = _closure_text()
    assert "session/load" in text
    assert SESSION_LOAD_OWNER in text


def test_closure_evidence_names_three_p11_fu_9_deferrals_by_exact_header() -> None:
    text = _closure_text()
    for header in REQUIRED_DEFERRAL_HEADERS:
        assert header in text, f"missing deferral header: {header}"


def test_closure_evidence_names_plan_118_winerror_flake_by_exact_header() -> None:
    text = _closure_text()
    assert PLAN_118_FLAKE_HEADER in text


def test_closure_evidence_distinguishes_client_supplied_from_gateway_brokered_mcp() -> None:
    text = _closure_text()
    assert re.search(r"client_supplied_acp|client-supplied", text, re.I)
    assert re.search(r"Gateway|gateway_brokered|Gateway-brokered", text, re.I)
